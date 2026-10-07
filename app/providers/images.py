"""Verified image adapters, not connected to automatic rendering or paid fallback."""
import base64
from typing import Protocol, runtime_checkable

import httpx

from app.providers.base import ScriptProviderError
from app.providers.gemini import GeminiScriptProvider
from app.providers.text_api import OpenAIScriptProvider
from app.production_settings import ImageSettings


@runtime_checkable
class ImageProvider(Protocol):
    def test_connection(self) -> dict: ...
    def generate_image(self, prompt: str, *, cost_confirmed: bool = False) -> dict: ...


@runtime_checkable
class StockProvider(Protocol):
    def search(self, query: str, media_type: str) -> list[dict]: ...


@runtime_checkable
class TTSProvider(Protocol):
    def synthesize(self, text: str, voice: str, options: dict) -> dict: ...


@runtime_checkable
class RenderProvider(Protocol):
    def render(self, plan: dict) -> dict: ...


def decoded_image(value):
    try:
        if not isinstance(value, str) or len(value) > 45000000: raise ValueError()
        data = base64.b64decode(value, validate=True)
        if data.startswith(b'\x89PNG\r\n\x1a\n'): mime = 'image/png'
        elif data.startswith(b'\xff\xd8\xff'): mime = 'image/jpeg'
        elif data.startswith(b'RIFF') and data[8:12] == b'WEBP': mime = 'image/webp'
        else: raise ValueError()
        return {'data': data, 'mime_type': mime}
    except (ValueError, TypeError): raise ScriptProviderError('Sağlayıcı geçerli görsel verisi döndürmedi.', category='invalid_response') from None


class LocalGPUImageProvider:
    def __init__(self, config, *, transport=None):
        self.config = ImageSettings.model_validate(config)
        self.transport = transport

    def test_connection(self):
        if not self.config.local_enabled: raise ScriptProviderError('Yerel GPU görsel sağlayıcısı kapalı.', 422, category='provider_disabled')
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False, transport=self.transport) as client:
                stats = client.get(self.config.local_url.rstrip('/') + '/system_stats')
                stats.raise_for_status()
                data = stats.json()
                if not isinstance(data.get('devices'), list): raise ValueError()
                gpu = any(device.get('type') == 'cuda' for device in data['devices'] if isinstance(device, dict))
            return {'status': 'Hazır', 'message': 'ComfyUI bağlantısı başarılı. ' + ('CUDA GPU algılandı.' if gpu else 'CUDA GPU bildirilmedi; yerel backend ayarlarını kontrol edin.') + ' Görsel çalıştırması için lisanslı model ve doğrulanmış API workflow eşlemesi gerekir.'}
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            raise ScriptProviderError('ComfyUI bağlantısı kurulamadı. Yerel uygulamayı açıp adresini kontrol edin.', 503, category='no_internet') from None

    def models(self):
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False, transport=self.transport) as client:
                response = client.get(self.config.local_url.rstrip('/') + '/object_info/CheckpointLoaderSimple')
                response.raise_for_status()
                models = response.json()['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0]
            if not isinstance(models, list) or any(not isinstance(model, str) or len(model) > 200 for model in models): raise ValueError()
            return models
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
            raise ScriptProviderError('Yerel kurulu model listesi alınamadı. ComfyUI ve model kurulumunu kontrol edin.', 503) from None

    def generate_image(self, prompt, *, cost_confirmed=False):
        raise ScriptProviderError('Yerel görsel çalıştırması daha sonraki aşama için hazırlandı. Lisanslı model ve doğrulanmış API workflow eşlemesi henüz bağlı değil.', 422, category='prepared_only')


class GeminiImageProvider:
    def __init__(self, key, model, *, transport=None):
        self.provider = GeminiScriptProvider(key, model, transport=transport)

    def test_connection(self): return self.provider.test_connection()
    def models(self): return self.provider.list_models()

    def generate_image(self, prompt, *, cost_confirmed=False):
        if not cost_confirmed: raise ScriptProviderError('Bulut görsel üretimi ücret veya kota kullanabilir. Açık onay gerekli.', 409, category='cost_confirmation')
        if not self.provider.model or not isinstance(prompt, str) or not 1 <= len(prompt) <= 8000 or self.provider._contains_key(prompt):
            raise ScriptProviderError('Görsel istemini ve API ile uyumlu model seçimini kontrol edin.', 422)
        with self.provider._client(120) as client:
            data = self.provider._request(client, 'POST', f'/models/{self.provider.model}:generateContent', json={'contents': [{'role': 'user', 'parts': [{'text': prompt}]}], 'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']}})
        try:
            candidate = data['candidates'][0]
            if candidate['finishReason'] != 'STOP': raise ValueError()
            for part in candidate['content']['parts']:
                if part.get('thought'): continue
                if 'inlineData' in part:
                    image = decoded_image(part['inlineData']['data'])
                    if image['mime_type'] != part['inlineData']['mimeType']: raise ValueError()
                    return image
            raise ValueError()
        except (ValueError, TypeError, KeyError, IndexError):
            raise ScriptProviderError('Bu Gemini modeli kullanılabilir görsel döndürmedi. Resmi belgelerde görsel çıkışı destekleyen modeli kontrol edin.', 502, category='invalid_response') from None


class OpenAIImageProvider:
    def __init__(self, key, model, *, transport=None):
        self.provider = OpenAIScriptProvider(key, model, transport=transport)

    def test_connection(self): return self.provider.test_connection()

    def generate_image(self, prompt, *, cost_confirmed=False):
        if not cost_confirmed: raise ScriptProviderError('Bulut görsel üretimi ücret kullanabilir. Açık onay gerekli.', 409, category='cost_confirmation')
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 8000: raise ScriptProviderError('Görsel istemini kontrol edin.', 422)
        key = self.provider._key.get_secret_value()
        if key in prompt: raise ScriptProviderError('Görsel istemine API anahtarı eklemeyin.', 422)
        data = self.provider._call('POST', 'https://api.openai.com/v1/images/generations', {'model': self.provider.model, 'prompt': prompt, 'n': 1}, operation='image_generate')
        try: return decoded_image(data['data'][0]['b64_json'])
        except (TypeError, KeyError, IndexError): raise ScriptProviderError('OpenAI görsel yanıtı okunamadı.', category='invalid_response') from None


def image_candidates(config, *, stock_found=False, cost_confirmed=False):
    """Planning selection only; this function cannot make a network request."""
    config = ImageSettings.model_validate(config)
    if stock_found: return ['stock']
    if config.engine == 'off': return []
    result = ['local'] if config.engine in ('auto', 'local') and config.local_enabled and config.license_confirmed and config.local_model and config.workflow else []
    if config.engine == 'local': return result
    allowed_cloud = config.paid_usage == 'allow_fallback' or config.paid_usage == 'ask' and cost_confirmed
    if allowed_cloud:
        for name in ('gemini', 'openai') if config.engine == 'auto' else (config.engine,):
            if getattr(config, name + '_model'): result.append(name)
    return result
