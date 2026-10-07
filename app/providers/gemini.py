"""Google Gemini Developer API only. Official contract: docs/GEMINI.md."""
import re
import time
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.providers.base import ScriptProviderError

API_ROOT = 'https://generativelanguage.googleapis.com/v1beta'
ORIGINALITY_INSTRUCTION = (
    'Write an original script in the requested language. Reference material may inform only '
    'abstract genre, audience, pacing and structure. Create new characters, wording, scenes, '
    'events, conflicts and ending. Do not reproduce, translate or lightly paraphrase an existing '
    'video or full script. Return only the finished script, never private reasoning or credentials.'
)


def normalize_model(value: str) -> str:
    value = value.strip()
    if value.startswith('models/'):
        value = value[7:]
    if value and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,149}', value):
        raise ValueError('Geçerli bir Gemini model adı girin veya model listesinden seçin.')
    return value


class GeminiScriptProvider:
    def __init__(self, api_key: str, model: str = '', *, transport=None):
        if not api_key:
            raise ScriptProviderError('Önce Ayarlar → Gemini bölümünde API anahtarını kaydedin. Gemini kullanmak zorunda değilsiniz.', 422)
        if not api_key.isascii() or len(api_key) < 8 or any(char.isspace() or ord(char) < 32 for char in api_key):
            raise ScriptProviderError('Gemini API anahtarını eksiksiz ve boşluksuz girin.', 422)
        self._key = SecretStr(api_key)
        try:
            self.model = normalize_model(model)
        except ValueError:
            raise ScriptProviderError('Geçerli bir Gemini modeli seçip kaydedin.', 422) from None
        if api_key in self.model:
            raise ScriptProviderError('API anahtarını yalnızca anahtar alanına girin; model alanını düzeltin.', 422)
        self._transport = transport

    def _contains_key(self, value: str) -> bool:
        key = self._key.get_secret_value()
        return key in value or quote(key, safe='') in value

    def _redact(self, value: str) -> str:
        key = self._key.get_secret_value()
        return value.replace(quote(key, safe=''), '[gizlendi]').replace(key, '[gizlendi]')

    def _client(self, timeout: float):
        # HTTPS/TLS verification remains enabled. Keep platform proxy support.
        # Never put the key into a URL or follow redirects to another origin.
        try:
            return httpx.Client(timeout=timeout, follow_redirects=False, transport=self._transport,
                                headers={'x-goog-api-key': self._key.get_secret_value()})
        except (httpx.HTTPError, ValueError):
            raise ScriptProviderError('Gemini bağlantısı hazırlanamadı. İnternet ve API ayarlarını kontrol edin.', 503) from None

    def _request(self, client, method: str, path: str, **kwargs) -> dict:
        try:
            response = client.request(method, API_ROOT + path, **kwargs)
            status = response.status_code
            if status != 200:
                if status in (400, 401, 403):
                    raise ScriptProviderError('Gemini anahtarı veya erişim izni kabul edilmedi. Google AI Studio API anahtarını ve API kısıtlamalarını kontrol edin.', status)
                if status == 404:
                    raise ScriptProviderError('Gemini modeli bulunamadı. Model listesini yenileyip bir model seçin.', 404)
                if status == 429:
                    raise ScriptProviderError('Gemini kullanım sınırına ulaşıldı. Bir süre bekleyip Google AI Studio kotasını kontrol edin.', 429)
                raise ScriptProviderError('Gemini şu anda yanıt veremiyor. İnternet bağlantınızı kontrol edip daha sonra tekrar deneyin.', 503)
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except httpx.TimeoutException:
            raise ScriptProviderError('Gemini zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.', 503) from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise ScriptProviderError('Gemini yanıtı alınamadı. İnternet bağlantınızı ve API ayarlarını kontrol edip tekrar deneyin.', 502) from None

    def list_models(self) -> list[str]:
        models = set()
        page_token = ''
        visited = set()
        deadline = time.monotonic() + 15
        with self._client(8) as client:
            for _ in range(5):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ScriptProviderError('Gemini model listesi zamanında alınamadı. Daha sonra tekrar deneyin.', 503)
                params = {'pageSize': 1000}
                if page_token:
                    params['pageToken'] = page_token
                data = self._request(client, 'GET', '/models', params=params, timeout=min(8, remaining))
                items = data.get('models', [])
                if not isinstance(items, list):
                    raise ScriptProviderError('Gemini model listesi okunamadı. Daha sonra tekrar deneyin.')
                for item in items:
                    if not isinstance(item, dict):
                        raise ScriptProviderError('Gemini model listesi okunamadı. Daha sonra tekrar deneyin.')
                    methods = item.get('supportedGenerationMethods', [])
                    if not isinstance(methods, list):
                        raise ScriptProviderError('Gemini model bilgileri okunamadı. Daha sonra tekrar deneyin.')
                    if 'generateContent' not in methods:
                        continue
                    name = item.get('name', '')
                    if not isinstance(name, str) or not name.startswith('models/') or self._contains_key(name):
                        continue
                    try:
                        model = normalize_model(name)
                    except ValueError:
                        continue
                    if model:
                        models.add(model)
                next_token = data.get('nextPageToken', '')
                if not next_token:
                    if not models:
                        raise ScriptProviderError('Bu anahtarla kullanılabilir metin modeli bulunamadı. Google AI Studio API erişiminizi kontrol edin.', 422)
                    return sorted(models)
                if not isinstance(next_token, str) or next_token in visited or self._contains_key(next_token):
                    raise ScriptProviderError('Gemini model listesi tamamlanamadı. Daha sonra tekrar deneyin.')
                visited.add(next_token)
                page_token = next_token
        raise ScriptProviderError('Gemini model listesi çok uzun veya tamamlanamadı. Daha sonra tekrar deneyin.')

    def test_connection(self) -> dict:
        models = self.list_models()  # No generated content, subscription or website interaction.
        if self.model and self.model not in models:
            raise ScriptProviderError('Seçilen model bu anahtarla kullanılamıyor. Model listesini yenileyip bir model seçin.', 422)
        return {'status': 'Hazır', 'message': 'Gemini API bağlantısı başarılı.' if self.model else 'Gemini API bağlantısı başarılı. Listeden bir model seçip kaydedin.', 'models': models}

    def generate_script(self, prompt: str) -> str:
        if not self.model:
            raise ScriptProviderError('Önce Ayarlar → Gemini bölümünde bir model seçip kaydedin.', 422)
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100000:
            raise ScriptProviderError('Senaryo isteği boş veya çok uzun. Konuyu kontrol edin.', 422)
        if self._contains_key(prompt):
            raise ScriptProviderError('Senaryo isteğine API anahtarı eklemeyin.', 422)
        with self._client(60) as client:
            data = self._request(client, 'POST', f'/models/{self.model}:generateContent',
                                 json={'systemInstruction': {'parts': [{'text': ORIGINALITY_INSTRUCTION}]},
                                       'contents': [{'role': 'user', 'parts': [{'text': prompt}]}]})
        try:
            feedback = data.get('promptFeedback', {})
            if not isinstance(feedback, dict) or feedback.get('blockReason') not in (None, '', 'BLOCK_REASON_UNSPECIFIED'):
                raise ValueError()
            candidate = data['candidates'][0]
            if candidate.get('finishReason') != 'STOP':
                raise ValueError()
            parts = candidate['content']['parts']
            if not isinstance(parts, list) or any(not isinstance(part, dict) for part in parts):
                raise ValueError()
            text = '\n'.join(part['text'] for part in parts if isinstance(part.get('text'), str) and not part.get('thought')).strip()
            if not text:
                raise ValueError()
            return self._redact(text)
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise ScriptProviderError('Gemini tamamlanmış bir senaryo döndürmedi. İsteği gözden geçirip tekrar deneyin; eksik çıktı kaydedilmedi.') from None
