"""Verified Ollama / OpenAI text contracts; official sources: docs/SCRIPT_ENGINE.md."""
from urllib.parse import quote, urlsplit
import logging
import time

import httpx
from pydantic import SecretStr

from app.providers.base import ScriptProviderError
from app.providers.gemini import ORIGINALITY_INSTRUCTION


class TextAPIProvider:
    name = ''

    def _redact(self, text):
        key = self._key.get_secret_value()
        return text.replace(quote(key, safe=''), '[gizlendi]').replace(key, '[gizlendi]') if key else text

    def generate_script(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100000:
            raise ScriptProviderError('Senaryo isteği boş veya çok uzun.', 422)
        key = self._key.get_secret_value()
        if key and (key in prompt or quote(key, safe='') in prompt):
            raise ScriptProviderError('Senaryo isteğine API anahtarı eklemeyin.', 422)
        data = self._call('POST', self.url, self._body(prompt), operation='generate')
        try:
            text = self._text(data)
            if not isinstance(text, str) or not text.strip():
                raise ValueError()
            return self._redact(text.strip())
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ScriptProviderError(self.name + ' tamamlanmış bir yanıt döndürmedi. Tekrar deneyin.', 502, category='invalid_response') from None

    def _call(self, method, url, body=None, *, operation):
        started, category = time.monotonic(), 'success'
        try:
            key = self._key.get_secret_value()
            with httpx.Client(timeout=50 if operation == 'test' else 120, trust_env=self.name != 'Ollama', follow_redirects=False,
                              transport=self._transport) as client:
                response = client.request(method, url, headers={'Authorization': 'Bearer ' + key} if key else {},
                                          **({'json': body} if body is not None else {}))
            if response.status_code != 200:
                category = {401: 'key_rejected', 403: 'key_rejected', 404: 'model_unavailable', 429: 'quota_limit'}.get(response.status_code, 'upstream_error')
                # Inspect only known public error codes; never log/return raw bodies.
                if self.name == 'OpenAI':
                    try:
                        code = response.json().get('error', {}).get('code')
                        if code in ('insufficient_quota', 'billing_hard_limit_reached'):
                            category = 'billing_quota'
                        elif code == 'rate_limit_exceeded':
                            category = 'rate_limit'
                        elif code == 'model_not_found':
                            category = 'model_unavailable'
                        elif response.status_code == 400:
                            category = 'invalid_model'
                    except (ValueError, TypeError, AttributeError):
                        pass
                messages = {'key_rejected': 'API anahtarı kabul edilmedi. Ayarlar bölümünü kontrol edin.',
                            'model_unavailable': 'Seçilen model kullanılamıyor. Ayarlar bölümünde model adını kontrol edin.',
                            'invalid_model': 'Model veya bu modelin desteklediği API isteği geçersiz. Chat Completions destekleyen bir model seçin.',
                            'billing_quota': 'OpenAI faturalandırma veya kota sınırına ulaşıldı. API hesabınızın bakiye ve kullanım sınırını kontrol edin.',
                            'rate_limit': 'OpenAI istek hız sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
                            'quota_limit': 'Kullanım sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
                            'upstream_error': 'Sağlayıcı yanıt veremiyor. Daha sonra tekrar deneyin.'}
                retry = response.headers.get('Retry-After', '')
                retry = min(120, int(retry)) if retry.isdigit() else 30 if response.status_code == 429 else 0
                raise ScriptProviderError(self.name + ': ' + messages[category], 502, category=category, retry_after=retry)
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except httpx.TimeoutException:
            category = 'generation_timeout'
            raise ScriptProviderError(self.name + ' zamanında yanıt vermedi. Tekrar deneyin.', 504, category='generation_timeout') from None
        except (httpx.ConnectError, httpx.ProxyError):
            category = 'no_internet'
            raise ScriptProviderError(self.name + ' bağlantısı kurulamadı. Bağlantınızı ve Ayarlar bölümünü kontrol edin.', 503, category='no_internet') from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            category = 'invalid_response'
            raise ScriptProviderError(self.name + ' tamamlanmış bir yanıt döndürmedi. Tekrar deneyin.', 502, category='invalid_response') from None
        except ScriptProviderError as error:
            category = error.category
            raise
        finally:
            logging.getLogger('uvicorn.error.providers').info('provider=%s operation=%s category=%s elapsed_ms=%.0f', self.name, operation, category, (time.monotonic() - started) * 1000)


class OllamaScriptProvider(TextAPIProvider):
    name = 'Ollama'

    def __init__(self, base_url, model, *, transport=None):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.path not in ('', '/') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ScriptProviderError('Ollama için yerel adresi Ayarlar bölümünden kaydedin.', 422)
        if not model:
            raise ScriptProviderError('Ollama modeli yapılandırılmamış. Ayarlar bölümünde kurulu modelin adını girin.', 422, category='missing_model')
        self.url, self.model = base_url.rstrip('/') + '/api/generate', model
        self._key, self._transport = SecretStr(''), transport

    def _body(self, prompt):
        return {'model': self.model, 'prompt': prompt, 'system': ORIGINALITY_INSTRUCTION, 'stream': False}

    def _text(self, data):
        if data.get('done') is not True or data.get('done_reason', 'stop') != 'stop':
            raise ValueError()
        return data['response']

    def test_connection(self):
        from app.provider_checks import check_ollama
        return check_ollama({'base_url': self.url.removesuffix('/api/generate'), 'model': self.model})


class OpenAIScriptProvider(TextAPIProvider):
    name = 'OpenAI'
    url = 'https://api.openai.com/v1/chat/completions'

    def __init__(self, api_key, model, *, transport=None):
        if not api_key:
            raise ScriptProviderError('OpenAI API anahtarı yapılandırılmamış. Ayarlar bölümünden kaydedin.', 422, category='missing_key')
        if not api_key.isascii() or any(char.isspace() or ord(char) < 32 for char in api_key):
            raise ScriptProviderError('OpenAI anahtarını Ayarlar bölümünde kontrol edin.', 422)
        if not model or any(char.isspace() or ord(char) < 32 for char in model) or api_key in model:
            raise ScriptProviderError('OpenAI modelini Ayarlar bölümünde kontrol edin.', 422, category='missing_model')
        self.model, self._key, self._transport = model, SecretStr(api_key), transport

    def _body(self, prompt):
        return {'model': self.model, 'messages': [{'role': 'system', 'content': ORIGINALITY_INSTRUCTION},
                                               {'role': 'user', 'content': prompt}], 'stream': False}

    def _text(self, data):
        choice = data['choices'][0]
        if choice['finish_reason'] != 'stop' or choice['message'].get('refusal'):
            raise ValueError()
        return choice['message']['content']

    def test_connection(self):
        data = self._call('GET', 'https://api.openai.com/v1/models/' + quote(self.model, safe=''), operation='test')
        if data.get('id') != self.model:
            raise ScriptProviderError('OpenAI model bilgisi doğrulanamadı.', 502, category='invalid_response')
        return {'status': 'Hazır', 'message': 'OpenAI anahtar ve model erişimi başarılı. Üretim kotası ve faturalandırma üretim sırasında ayrıca kontrol edilir.'}
