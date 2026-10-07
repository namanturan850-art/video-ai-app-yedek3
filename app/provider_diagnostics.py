"""Small, independent live checks. No project, script or credential reset."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
from threading import RLock
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.providers.base import ScriptProviderError
from app.providers.factory import make_script_provider
from app.scripts.engine import SecretGuard, YouTubeScriptEngine
from app.scripts.models import ScriptError, word_count
from app.secret_store import SettingsStorageError, SettingsStore
from app.settings import SettingsInputError, mask_secret

PROVIDERS = ('gemini', 'ollama', 'openai')
TESTS = ('settings', 'connection', 'simple_generation', 'json', 'script_pipeline')
LOG = logging.getLogger('uvicorn.error.ai_diagnostics')
MESSAGES = {
    'settings_required': 'Önce 1 — Ayarlar testini çalıştırın. API çağrısı yapılmadı.',
    'settings_changed': 'Ayarlar test sırasında veya sonrasında değişti. Önce 1 — Ayarlar testini yeniden çalıştırın.',
    'settings_reopen_mismatch': 'Şifreli ayarlar yeniden açıldığında aynı bilgiler okunamadı. Mevcut dosyaları silmeyin.',
    'key_decrypt_failed': 'Şifreli ayarlar açılamadı. Kaydettiğiniz Windows hesabını kullanın; mevcut dosyaları silmeyin.',
    'folder_permission': 'Ayar klasörüne erişilemiyor. Klasörün yazma iznini kontrol edin; dosyaları silmeyin.',
    'temp_file_failed': 'Ayarlar için geçici dosya yazılamadı. İzinleri ve boş disk alanını kontrol edin.',
    'atomic_replace_failed': 'Ayar dosyası güncellenemedi. Dosyayı kullanan programları kapatıp tekrar deneyin; önceki ayarlar korundu.',
    'encryption_failed': 'Ayarlar şifrelenemedi. Aynı Windows hesabında tekrar deneyin; dosyaları silmeyin.',
    'storage_locked': 'Ayar dosyası başka program tarafından kullanılıyor. Bekleyip tekrar deneyin; önceki ayarlar korundu.',
    'provider_disabled': 'OpenAI kapalı. Ayarlar → OpenAI bölümünde Etkinleştir seçimini açıp Kaydet deyin.',
    'missing_key': 'API anahtarı kayıtlı değil. Ayarlar ekranından kaydedin; anahtarı paylaşmayın.',
    'missing_model': 'Model kayıtlı değil. Ayarlar ekranında kurulu veya erişilebilir bir model seçip kaydedin.',
    'invalid_settings': 'Kayıtlı model veya adres geçersiz. Ayarlar ekranında düzeltip yeniden kaydedin.',
    'key_rejected': 'API anahtarı veya erişim izni kabul edilmedi. Anahtarı ve API erişim kısıtlamalarını kontrol edin.',
    'free_quota_exhausted': 'Gemini ücretsiz API kotası tükendi veya bu model için ücretsiz kota yok. Google AI Studio kullanım sınırlarını kontrol edin. Bu bir entegrasyon arızası değildir.',
    'quota_limit': 'API kota veya kullanım sınırına ulaşıldı. Yanıt kota türünü kesin ayırmıyor; sağlayıcı hesabındaki limitleri kontrol edin. Bu bir entegrasyon arızası değildir.',
    'rate_limit': 'API istek hız sınırına ulaşıldı. Bekleyip tekrar deneyin. Bu bir entegrasyon arızası değildir.',
    'billing_quota': 'OpenAI API bakiye veya kullanım kotası yetersiz. API hesabındaki faturalandırma ve limitleri kontrol edin.',
    'model_unavailable': 'Seçilen model bulunamadı veya erişilemiyor. Ayarlar ekranında erişilebilir model seçip kaydedin.',
    'invalid_model': 'Seçilen model bu API isteğiyle uyumlu değil. Metin üretimini destekleyen model seçin.',
    'invalid_request': 'Sağlayıcı isteği kabul etmedi. Modelin bu metin API’sini desteklediğini kontrol edin. Anahtar hatası olduğu varsayılmadı.',
    'thinking_unsupported': 'Bu Ollama modeli mevcut ayarlarla reasoning modunu kapatamıyor.',
    'reasoning_in_response': 'Sağlayıcı son yanıta reasoning içeriği ekledi. İçerik senaryoya alınmadı.',
    'empty_response': 'API yanıt verdi ancak son metin alanı boş. Reasoning alanı son yanıt yerine kullanılmadı.',
    'incomplete_response': 'API yanıtı tamamlanmadı. Kesilmiş metin başarılı sayılmadı.',
    'invalid_response': 'API yanıtının beklenen son metin alanı veya yanıt yapısı okunamadı. Ham yanıt gösterilmedi.',
    'invalid_json': 'Yanıt tek ve geçerli bir JSON nesnesi değil. Eksik JSON veya alanlar tamamlanmadı.',
    'schema_invalid': 'JSON okunabildi ancak gerekli alanlar veya alan türleri geçersiz. Eksik alanlar tamamlanmadı.',
    'simple_response_mismatch': 'API metin üretti ancak son yanıt yalnızca TEST_OK değildi. Bu bir yanıt biçimi sorunudur.',
    'pipeline_output_invalid': 'Tek bölüm isteği kullanılabilir kısa anlatım döndürmedi. Tam senaryo motoru çalıştırılmadı.',
    'gemini_timeout': 'Gemini API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.',
    'generation_timeout': 'Sağlayıcı zamanında yanıt vermedi. Ollama kullanıyorsanız model yükleme/donanım durumunu; bulut için interneti kontrol edin.',
    'no_internet': 'Dış API bağlantısı kurulamadı. İnternet, güvenlik duvarı ve proxy ayarlarını kontrol edin.',
    'local_connection': 'Yerel Ollama sunucusuna ulaşılamadı. Ollama uygulamasını açıp yerel adresi kontrol edin.',
    'network_error': 'API HTTP bağlantısı tamamlanamadı. Ağ, proxy, güvenlik duvarı ve sağlayıcı durumunu kontrol edin. Bu bir JSON ayrıştırma hatası değildir.',
    'upstream_error': 'Sağlayıcı API’si isteği tamamlayamadı. Daha sonra tekrar deneyin.',
    'unexpected_backend': 'Yerel tanılama işlemi beklenmeyen bir hatayla durdu. Dosyaları silmeden yeniden deneyin; güvenli kategori günlüğe yazıldı.',
}
STORAGE_ERRORS = {'settings_reopen_mismatch', 'key_decrypt_failed', 'folder_permission', 'temp_file_failed',
                  'atomic_replace_failed', 'encryption_failed', 'storage_locked'}


class DiagnosticInputError(Exception):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


class JSONProbe(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['ok']


class DiagnosticScriptProvider:
    """Check observed reasoning before JSON/format validation can hide its cause."""
    def __init__(self, provider, backend):
        self.provider, self.backend = provider, backend

    def generate_script(self, prompt):
        text = self.backend.generate_script(prompt)
        if self.provider == 'ollama' and getattr(self.backend, 'thinking_returned', False):
            raise ScriptProviderError(MESSAGES['thinking_unsupported'], category='thinking_unsupported')
        return text

    def test_connection(self):
        return self.backend.test_connection()


def result_status(category):
    if category == 'none': return 'Başarılı'
    if category in STORAGE_ERRORS: return 'Ayar kaydetme hatası'
    if category in ('free_quota_exhausted', 'quota_limit', 'rate_limit', 'billing_quota'): return 'Kota sınırı'
    if category in ('model_unavailable', 'invalid_model', 'thinking_unsupported'): return 'Model uyumsuz'
    if category in ('invalid_response', 'empty_response', 'incomplete_response', 'reasoning_in_response',
                    'invalid_json', 'schema_invalid', 'simple_response_mismatch', 'pipeline_output_invalid'): return 'Yanıt biçimi hatası'
    if category in ('no_internet', 'local_connection', 'network_error', 'gemini_timeout', 'generation_timeout'): return 'Bağlantı hatası'
    return 'Hata'


class ProviderDiagnostics:
    def __init__(self, settings):
        self.settings = settings
        self.provider_factory = make_script_provider
        self.lock = RLock()
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='ai-diagnostics')
        self.futures = {}
        self.fingerprints = {}
        self.retry_at = {}
        self.closed = False
        self.states = {name: self._blank(name) for name in PROVIDERS}

    @staticmethod
    def _blank(provider):
        return {'provider': provider, **{test + '_status': 'Bekliyor' for test in TESTS},
                'safe_error_category': 'none', 'safe_message': 'Bu oturumda henüz canlı test çalıştırılmadı.',
                'elapsed_ms': 0, 'running_test': None,
                'tests': {test: {'status': 'Bekliyor', 'safe_error_category': 'none',
                                 'safe_message': 'Henüz test edilmedi.', 'elapsed_ms': 0} for test in TESTS}}

    def view(self):
        with self.lock:
            return {'providers': deepcopy(list(self.states.values())), 'live_test_notice': 'Live provider test must be run by owner on Windows.'}

    def _config_fingerprint(self, provider):
        config = self.settings.script_config(provider)
        fields = ('base_url', 'model') if provider == 'ollama' else ('api_key', 'model', 'enabled') if provider == 'openai' else ('api_key', 'model')
        return hashlib.sha256(json.dumps({key: config.get(key) for key in fields}, sort_keys=True).encode()).digest()

    def start(self, provider, test, payload):
        if provider not in PROVIDERS or test not in TESTS:
            raise DiagnosticInputError('Ekrandaki sağlayıcı ve testlerden birini seçin.')
        if not isinstance(payload, dict) or set(payload) - {'cost_confirmed'} or type(payload.get('cost_confirmed', False)) is not bool:
            raise DiagnosticInputError('Tanılama isteği okunamadı. Ekrandaki test düğmesini kullanın.')
        if provider != 'ollama' and test in ('simple_generation', 'json', 'script_pipeline') and not payload.get('cost_confirmed', False):
            raise DiagnosticInputError('Bu kısa canlı API testi kota veya ücret kullanabilir. Devam etmek için ekrandaki maliyet onayını verin.')
        with self.lock:
            if self.closed: raise DiagnosticInputError('Uygulama kapanıyor. Yeniden açıp test edin.', 503)
            state = self.states[provider]
            if state['running_test']:
                raise DiagnosticInputError('Bu sağlayıcının testi sürüyor. Sonucu bekleyin.', 409)
            state['running_test'] = test
            state[test + '_status'] = 'Test ediliyor'
            state['tests'][test] = {'status': 'Test ediliyor', 'safe_error_category': 'none', 'safe_message': 'Test sürüyor…', 'elapsed_ms': 0}
            self.futures[provider] = self.executor.submit(self._run, provider, test)
        return self.view()

    def _verify_storage(self, provider):
        # Same atomic encrypted writer, then a NEW reader (not a cached safe view).
        # Hold the store lock across both operations so concurrent Settings save cannot
        # be overwritten. No defaults/metadata/other provider credentials are changed.
        with self.settings.store.lock:
            before = self.settings.store.read()
            self.settings.store.write(before)
            reopened = SettingsStore(self.settings.store.directory).read()
            if reopened != before:
                raise ScriptProviderError(MESSAGES['settings_reopen_mismatch'], category='settings_reopen_mismatch')
            config = self.settings.script_config(provider)
            secrets = self.settings.secret_values()
            guard = SecretGuard(secrets)
            guard.validate({key: value for key, value in config.items() if key in ('model', 'base_url')})
            key = config.get('api_key', '')
            metadata = {'model': config.get('model', ''), 'has_api_key': bool(key), 'masked_api_key': mask_secret(key)}
            if provider == 'openai': metadata['enabled'] = config['enabled']
            fingerprint = self._config_fingerprint(provider)
        with self.lock:
            if self.fingerprints.get(provider) != fingerprint:
                self.states[provider] = self._blank(provider)
                self.states[provider]['running_test'] = 'settings'
                self.retry_at.pop(provider, None)
            self.fingerprints[provider] = fingerprint
        return metadata

    def _network_test(self, provider, test):
        with self.settings.store.lock:
            fingerprint = self._config_fingerprint(provider)
            with self.lock:
                saved = self.fingerprints.get(provider)
                storage_ok = self.states[provider]['settings_status'] == 'Başarılı'
                retry = self.retry_at.get(provider)
            if not storage_ok or saved is None:
                raise ScriptProviderError(MESSAGES['settings_required'], category='settings_required')
            if fingerprint != saved:
                raise ScriptProviderError(MESSAGES['settings_changed'], category='settings_changed')
            if retry and retry[0] > time.monotonic():
                raise ScriptProviderError(MESSAGES[retry[1]], category=retry[1], retry_after=max(1, int(retry[0] - time.monotonic())), upstream_status=429)
            backend = DiagnosticScriptProvider(provider, self.provider_factory(provider, self.settings))
            guard = SecretGuard(self.settings.secret_values())
        if test == 'connection':
            outcome = backend.test_connection()
            if not isinstance(outcome, dict):
                raise ScriptProviderError(MESSAGES['invalid_response'], category='invalid_response')
            if outcome.get('status') != 'Hazır':
                category = outcome.get('category', 'upstream_error')
                raise ScriptProviderError(MESSAGES.get(category, MESSAGES['unexpected_backend']), category=category)
            message = 'API bağlantısı ve seçilen model erişimi doğrulandı. Bu sonuç üretim kotasını veya modelin üretim uyumluluğunu garanti etmez.'
        else:
            engine = YouTubeScriptEngine(backend, guard)
            if test == 'simple_generation':
                text = backend.generate_script('Return only TEST_OK. Do not include explanations, Markdown or reasoning.')
                if text != 'TEST_OK':
                    raise ScriptProviderError(MESSAGES['simple_response_mismatch'], category='simple_response_mismatch')
                message = 'Son metin alanında yalnızca TEST_OK alındı. Tam senaryo motoru çalıştırılmadı.'
            elif test == 'json':
                engine.structured('diagnostic_json', {}, 'Return exactly {"status":"ok"}. No other fields or reasoning.', JSONProbe)
                message = 'JSON ayrıştırıldı ve status=ok alanı doğrulandı. Eksik alanlar eklenmedi.'
            else:
                blueprint = {'content_type': 'Kısa açıklama', 'core_topic': 'Bir çalışma masasını düzenlemek', 'main_hook': 'Düzenli çalışma alanı', 'viewer_promise': 'Basit bir öneri', 'section_strategy': 'Tek kısa açıklama', 'key_topics': ['Düzen']}
                plan = {'sections': [{'title': 'Kısa tanılama', 'purpose': 'Yalnızca 20–40 kelimelik tek anlatım bölümü', 'key_points': ['Masadaki gereksiz eşyaları kaldırmak'], 'target_words': 30, 'transition': ''}]}
                text = engine.section(blueprint, plan, 0, '', {'language': 'tr', 'instructions': 'Yalnızca 20–40 kelimelik tek kısa bölüm yaz. Bu bir tanılama testidir.'})
                if not 5 <= word_count(text) <= 100 or text.startswith(('{', '[', '```')):
                    raise ScriptProviderError(MESSAGES['pipeline_output_invalid'], category='pipeline_output_invalid')
                message = 'YouTubeScriptEngine.section ile yalnızca bir kısa bölüm üretildi. Analiz, plan, devamlılık veya tam senaryo çalıştırılmadı; metin projeye kaydedilmedi.'
        if self._config_fingerprint(provider) != fingerprint:
            raise ScriptProviderError(MESSAGES['settings_changed'], category='settings_changed')
        return message

    def _run(self, provider, test):
        started, category, message, metadata = time.monotonic(), 'none', '', {}
        upstream_status, retry_after = None, 0
        try:
            if test == 'settings':
                metadata = self._verify_storage(provider)
                message = 'Ayarlar şifreli kaydedildi, yeni okuyucuyla yeniden açıldı ve aynı bilgiler doğrulandı. Bu test API erişimini kontrol etmez.'
                if provider == 'openai':
                    message += ' OpenAI etkin.' if metadata['enabled'] else ' OpenAI kapalı; API testinden önce Etkinleştir ve Kaydet deyin.'
                if not metadata['model']: message += ' Henüz model kaydedilmemiş.'
                if provider != 'ollama' and not metadata['has_api_key']: message += ' Henüz API anahtarı kaydedilmemiş.'
            else:
                message = self._network_test(provider, test)
        except SettingsStorageError as error:
            category = error.category if error.category in STORAGE_ERRORS else 'unexpected_backend'
        except ScriptProviderError as error:
            category = error.category if error.category in MESSAGES else 'unexpected_backend'
            upstream_status, retry_after = error.upstream_status, error.retry_after
        except (SettingsInputError, ScriptError) as error:
            category = error.category if isinstance(error, ScriptError) and error.category in MESSAGES else 'invalid_settings'
        except Exception:
            category = 'unexpected_backend'
        elapsed = round((time.monotonic() - started) * 1000)
        if type(upstream_status) is not int or not 100 <= upstream_status <= 599: upstream_status = None
        if category != 'none': message = MESSAGES[category]
        result = {'status': result_status(category), 'safe_error_category': category, 'safe_message': message,
                  'elapsed_ms': elapsed, 'checked_at': datetime.now(timezone.utc).isoformat(),
                  'upstream_http_status': upstream_status, 'retry_after_seconds': retry_after, **metadata}
        with self.lock:
            state = self.states[provider]
            state[test + '_status'] = result['status']
            state['tests'][test] = result
            state.update(safe_error_category=category, safe_message=message, elapsed_ms=elapsed, running_test=None)
            if category == 'settings_changed' or test == 'settings' and category != 'none':
                self.fingerprints.pop(provider, None)
                state['settings_status'] = 'Hata' if category == 'settings_changed' else result['status']
                if category == 'settings_changed': state['tests']['settings'] = {**result, 'status': 'Hata'}
            if retry_after and category in ('quota_limit', 'free_quota_exhausted', 'rate_limit', 'billing_quota'):
                self.retry_at[provider] = (time.monotonic() + retry_after, category)
        LOG.info('provider=%s operation=%s result=%s category=%s elapsed_ms=%d', provider, test,
                 'success' if category == 'none' else 'quota' if result['status'] == 'Kota sınırı' else 'failure', category, elapsed)

    def close(self):
        with self.lock: self.closed = True
        self.executor.shutdown(wait=True, cancel_futures=True)
