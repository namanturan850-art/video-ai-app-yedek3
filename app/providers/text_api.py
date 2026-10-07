"""Verified Ollama / OpenAI text contracts; official sources: docs/SCRIPT_ENGINE.md."""
from urllib.parse import quote, urlsplit

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
        try:
            with httpx.Client(timeout=120, trust_env=self.name != 'Ollama', follow_redirects=False,
                              transport=self._transport) as client:
                response = client.post(self.url, headers={'Authorization': 'Bearer ' + key} if key else {},
                                       json=self._body(prompt))
            if response.status_code != 200:
                category = {401: 'key_rejected', 403: 'key_rejected', 404: 'model_unavailable', 429: 'quota_limit'}.get(response.status_code, 'upstream_error')
                messages = {'key_rejected': 'API anahtarı kabul edilmedi. Ayarlar bölümünü kontrol edin.',
                            'model_unavailable': 'Seçilen model kullanılamıyor. Ayarlar bölümünde model adını kontrol edin.',
                            'quota_limit': 'Kullanım sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
                            'upstream_error': 'Sağlayıcı yanıt veremiyor. Daha sonra tekrar deneyin.'}
                raise ScriptProviderError(self.name + ': ' + messages[category], 502, category=category)
            text = self._text(response.json())
            if not isinstance(text, str) or not text.strip():
                raise ValueError()
            return self._redact(text.strip())
        except httpx.TimeoutException:
            raise ScriptProviderError(self.name + ' zamanında yanıt vermedi. Tekrar deneyin.', 504, category='generation_timeout') from None
        except httpx.ConnectError:
            raise ScriptProviderError(self.name + ' bağlantısı kurulamadı. Bağlantınızı ve Ayarlar bölümünü kontrol edin.', 503, category='no_internet') from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ScriptProviderError(self.name + ' tamamlanmış bir yanıt döndürmedi. Tekrar deneyin.', 502, category='invalid_response') from None


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
        # Settings tests remain unchanged; no paid generation used as a probe.
        raise ScriptProviderError('OpenAI üretimini Senaryo ekranından deneyebilirsiniz.', 422)
