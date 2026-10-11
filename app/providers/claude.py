"""Claude (Anthropic API) through the official `anthropic` SDK.

Used as the script/scene "director" and as the vision judge for stock media.
Every call records its token usage and estimated cost (app.ai_usage). Keys are
passed explicitly from the encrypted settings vault, never read from the
environment, and never logged. Refused requests are re-run server-side on the
recommended fallback model (`fallbacks: "default"`); a refusal that survives
the fallback is reported as a refusal, never as an empty success.
"""
import json
import logging
import time

from pydantic import SecretStr

from app.providers.base import ScriptProviderError, normalize_text

LOG = logging.getLogger('uvicorn.error.providers')
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
DIRECTOR_SYSTEM = ('You are the director of an original YouTube documentary/explainer channel. '
                   'Write original material only: never copy, translate or lightly paraphrase another '
                   'creator\'s script. Never invent facts, quotes, statistics or sources; when unsure, '
                   'stay general. Follow the requested output format exactly.')
MESSAGES = {
    'key_rejected': 'Claude API anahtarı kabul edilmedi. Ayarlar → Claude bölümünde anahtarı kontrol edin.',
    'billing_quota': 'Anthropic hesabında kredi veya kullanım sınırı yetersiz. console.anthropic.com → Billing bölümünü kontrol edin.',
    'rate_limit': 'Claude istek sınırına ulaşıldı. Bir süre bekleyip Devam Et deyin.',
    'model_unavailable': 'Seçilen Claude modeli bu hesapta kullanılamıyor. Ayarlar → Claude bölümünden başka model seçin.',
    'upstream_error': 'Claude şu anda yanıt veremiyor (sunucu yoğun). Biraz sonra tekrar deneyin.',
    'no_internet': 'Claude bağlantısı kurulamadı. İnternet bağlantınızı kontrol edin.',
    'generation_timeout': 'Claude zamanında yanıt vermedi. Devam Et ile tekrar deneyin.',
    'invalid_request': 'Claude isteği kabul etmedi. Ayarlar → Claude modelini kontrol edin; sorun sürerse tanılama bilgisini paylaşın.',
    'refusal': 'Claude bu isteği güvenlik nedeniyle yanıtlamadı. Konuyu farklı ifade edin veya yedek motoru kullanın.',
    'incomplete_response': 'Claude yanıtı yarıda kaldı (çok uzun). Tekrar deneyin; tamamlanmamış metin kullanılmadı.',
    'invalid_response': 'Claude yanıtı beklenen biçimde değildi. Tekrar deneyin.'}
# Categories where offering the backup engine (with the owner's consent) makes sense.
BACKUP_WORTHY = {'key_rejected', 'billing_quota', 'rate_limit', 'model_unavailable', 'upstream_error',
                 'no_internet', 'generation_timeout', 'refusal', 'missing_key'}


def _client(api_key):
    import anthropic
    # Explicit key: never fall back to environment variables or CLI profiles.
    return anthropic.Anthropic(api_key=api_key, timeout=600.0, max_retries=2)


class ClaudeProvider:
    name = 'Claude'

    def __init__(self, api_key, model, *, client=None, ledger=None, effort='high'):
        if not api_key:
            raise ScriptProviderError('Claude API anahtarı kaydedilmemiş. Ayarlar → Claude bölümünden ekleyin.', 422, category='missing_key')
        if not api_key.isascii() or any(c.isspace() or ord(c) < 32 for c in api_key):
            raise ScriptProviderError('Claude API anahtarını Ayarlar bölümünde kontrol edin.', 422, category='missing_key')
        self.model, self._key, self.ledger, self.effort = model, SecretStr(api_key), ledger, effort
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = _client(self._key.get_secret_value())
        return self._client

    # ---- error mapping -------------------------------------------------
    def _fail(self, category, *, status=502, retry=0, upstream=None):
        raise ScriptProviderError(MESSAGES[category], status, category=category, retry_after=retry, upstream_status=upstream)

    def _call(self, purpose, **request):
        import anthropic
        started, category = time.monotonic(), 'success'
        try:
            request.setdefault('max_tokens', 16000)
            with self.client.beta.messages.stream(model=self.model, betas=[FALLBACK_BETA], fallbacks='default', **request) as stream:
                message = stream.get_final_message()
            self._record(purpose, message)
            if message.stop_reason == 'refusal':
                category = 'refusal';self._fail('refusal')
            if message.stop_reason == 'max_tokens':
                category = 'incomplete_response';self._fail('incomplete_response')
            return message
        except anthropic.AuthenticationError:
            category = 'key_rejected';self._fail(category, status=401)
        except anthropic.PermissionDeniedError:
            category = 'key_rejected';self._fail(category, status=403)
        except anthropic.NotFoundError:
            category = 'model_unavailable';self._fail(category, status=404)
        except anthropic.RateLimitError as error:
            retry = error.response.headers.get('retry-after', '') if getattr(error, 'response', None) is not None else ''
            category = 'rate_limit';self._fail(category, retry=min(120, int(retry)) if str(retry).isdigit() else 30, upstream=429)
        except anthropic.BadRequestError as error:
            # Billing problems arrive as 400s; classify by the public error text
            # without ever echoing it to the user or logs.
            text = str(getattr(error, 'message', '')).lower()
            category = 'billing_quota' if 'credit' in text or 'billing' in text else 'invalid_request'
            self._fail(category, status=400, upstream=400)
        except anthropic.APITimeoutError:
            category = 'generation_timeout';self._fail(category, status=504)
        except anthropic.APIConnectionError:
            category = 'no_internet';self._fail(category, status=503)
        except anthropic.APIStatusError as error:
            category = 'upstream_error';self._fail(category, upstream=getattr(error, 'status_code', None))
        except ScriptProviderError as error:
            category = error.category;raise
        finally:
            LOG.info('provider=claude operation=%s category=%s elapsed_ms=%.0f', purpose, category, (time.monotonic() - started) * 1000)

    def _record(self, purpose, message):
        usage = getattr(message, 'usage', None)
        if not self.ledger or usage is None:
            return
        self.ledger.record(provider='claude', model=getattr(message, 'model', None) or self.model, purpose=purpose,
                           input_tokens=getattr(usage, 'input_tokens', 0) or 0, output_tokens=getattr(usage, 'output_tokens', 0) or 0,
                           cache_read=getattr(usage, 'cache_read_input_tokens', 0) or 0,
                           cache_write=getattr(usage, 'cache_creation_input_tokens', 0) or 0)

    @staticmethod
    def _text(message):
        # Final text blocks only; thinking/fallback blocks are never content.
        parts = [block.text for block in message.content if getattr(block, 'type', '') == 'text']
        if not parts:
            raise ScriptProviderError(MESSAGES['invalid_response'], category='invalid_response')
        return ''.join(parts)

    # ---- public surface ------------------------------------------------
    def generate_script(self, prompt: str) -> str:
        """ScriptProvider contract used by the existing script/scene engine."""
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 200000:
            raise ScriptProviderError('Senaryo isteği boş veya çok uzun.', 422)
        if self._key.get_secret_value() in prompt:
            raise ScriptProviderError('Senaryo isteğine API anahtarı eklemeyin.', 422)
        message = self._call('script', system=DIRECTOR_SYSTEM, max_tokens=32000,
                             output_config={'effort': self.effort},
                             messages=[{'role': 'user', 'content': prompt}])
        return normalize_text(self._text(message))

    def complete_json(self, purpose, prompt, schema, *, images=(), effort=None, max_tokens=32000, system=DIRECTOR_SYSTEM):
        """Structured output validated by the API against `schema`."""
        content = [*images, {'type': 'text', 'text': prompt}] if images else prompt
        message = self._call(purpose, system=system, max_tokens=max_tokens,
                             output_config={'effort': effort or self.effort, 'format': {'type': 'json_schema', 'schema': schema}},
                             messages=[{'role': 'user', 'content': content}])
        try:
            data = json.loads(self._text(message))
        except ValueError:
            raise ScriptProviderError(MESSAGES['invalid_response'], category='invalid_response') from None
        if not isinstance(data, dict):
            raise ScriptProviderError(MESSAGES['invalid_response'], category='invalid_response')
        return data

    def test_connection(self):
        """Key + model check through the Models API: no tokens, no cost."""
        import anthropic
        try:
            info = self.client.models.retrieve(self.model)
        except anthropic.AuthenticationError:
            raise ScriptProviderError(MESSAGES['key_rejected'], 401, category='key_rejected') from None
        except anthropic.PermissionDeniedError:
            raise ScriptProviderError(MESSAGES['key_rejected'], 403, category='key_rejected') from None
        except anthropic.NotFoundError:
            raise ScriptProviderError(MESSAGES['model_unavailable'], 404, category='model_unavailable') from None
        except anthropic.APITimeoutError:
            raise ScriptProviderError(MESSAGES['generation_timeout'], 504, category='generation_timeout') from None
        except anthropic.APIConnectionError:
            raise ScriptProviderError(MESSAGES['no_internet'], 503, category='no_internet') from None
        except anthropic.APIStatusError:
            raise ScriptProviderError(MESSAGES['upstream_error'], 502, category='upstream_error') from None
        if getattr(info, 'id', None) != self.model:
            raise ScriptProviderError(MESSAGES['invalid_response'], category='invalid_response')
        return {'status': 'Hazır', 'message': f'Claude bağlantısı başarılı · Model: {self.model}. Bu test ücretsizdir (metin üretilmedi).'}
