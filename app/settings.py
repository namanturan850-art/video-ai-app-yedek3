"""Part 2 configuration only; no content or project generation."""
from typing import Literal
from urllib.parse import urlsplit
import shutil

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from app.secret_store import SettingsStore
from app.providers.gemini import normalize_model, MODEL_UNAVAILABLE_MESSAGE


class SettingsInputError(Exception):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GeneralSettings(StrictModel):
    content_language: Literal["de", "tr", "en"] = "de"


def web_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return value
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or any(char.isspace() or ord(char) < 32 for char in value)
                or "\\" in value or (port is not None and not 1 <= port <= 65535)):
            raise ValueError()
    except ValueError:
        raise ValueError("http:// veya https:// ile başlayan geçerli bir adres girin. Adrese anahtar, kullanıcı adı veya parola eklemeyin.") from None
    return value


class OllamaSettings(StrictModel):
    base_url: str = Field(default="http://127.0.0.1:11434", max_length=500)
    model: str = Field(default="", max_length=150)

    @field_validator("base_url")
    @classmethod
    def local_address(cls, value):
        value = web_url(value)
        if not value or urlsplit(value).hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Yerel Ollama adresini girin; örneğin http://127.0.0.1:11434.")
        if urlsplit(value).path not in ("", "/"):
            raise ValueError("Ollama adresine API yolu eklemeyin.")
        return value

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        if any(char.isspace() or ord(char) < 32 for char in value.strip()):
            raise ValueError("Model adında boşluk kullanmayın.")
        return value.strip()


class KeySettings(StrictModel):
    api_key: SecretStr | None = None

    @field_validator("api_key")
    @classmethod
    def key_valid(cls, value):
        if value is None or not value.get_secret_value():
            return None  # Empty input preserves an existing key; DELETE explicitly clears it.
        key = value.get_secret_value()
        if not 8 <= len(key) <= 4096 or any(char.isspace() or ord(char) < 32 for char in key) or "•" in key:
            raise ValueError("Anahtarı boşluksuz ve eksiksiz girin (en az 8 karakter). Maskelenmiş değeri yapıştırmayın.")
        return value


class OpenAISettings(KeySettings):
    enabled: bool = False
    model: str = Field(default="", max_length=150)


class GeminiSettings(KeySettings):
    model: str = Field(default="", max_length=157)

    @field_validator("model")
    @classmethod
    def model_name(cls, value):
        return normalize_model(value)

    @field_validator("api_key")
    @classmethod
    def header_key(cls, value):
        if value is not None and not value.get_secret_value().isascii():
            raise ValueError("API anahtarını olduğu gibi, boşluksuz girin.")
        return value


class AI33Settings(KeySettings):
    base_url: str = Field(default="", max_length=500)
    voice_id: str = Field(default="", max_length=150)
    model: str = Field(default="", max_length=150)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        return web_url(value)


MODELS = {"general": GeneralSettings, "ollama": OllamaSettings, "openai": OpenAISettings,
          "gemini": GeminiSettings, "pexels": KeySettings, "pixabay": KeySettings, "ai33": AI33Settings}
PROVIDERS = ("ollama", "openai", "gemini", "pexels", "pixabay", "ai33")


def mask_secret(value: str) -> str:
    if not value:
        return ""
    # Very short historical/corrupted keys never reveal their complete value.
    return "••••••••••" + (value[-4:] if len(value) >= 8 else "")


def ffmpeg_status() -> dict:
    executable = shutil.which("ffmpeg")
    return {"status": "Hazır" if executable else "Yapılandırılmadı", "found": bool(executable),
            "executable_path": executable or "",
            "message": "Bulundu" if executable else "Bulunamadı. Ayarlar ekranını kullanmak için FFmpeg gerekmez."}


class SettingsService:
    def __init__(self, store: SettingsStore):
        self.store = store

    def _values(self) -> dict:
        values = self.store.read()
        for name, model in MODELS.items():
            defaults = model().model_dump(exclude={"api_key"})
            saved = values.setdefault(name, {})
            if not isinstance(saved, dict):
                from app.secret_store import SettingsStorageError
                raise SettingsStorageError("Yerel ayarlar açılamadı. Dosyaları silmeden destek isteyin.")
            for key, value in defaults.items():
                saved.setdefault(key, value)
        return values

    @staticmethod
    def _gemini_models(config: dict) -> list[str]:
        key = config.get('api_key', '')
        models = config.get('available_models', [])
        if not isinstance(models, list):
            return []
        safe = []
        for value in models:
            if not isinstance(value, str) or (key and key in value):
                continue
            try:
                value = normalize_model(value)
            except ValueError:
                continue
            if value and value not in safe:
                safe.append(value)
        return safe

    def safe_view(self) -> dict:
        with self.store.lock:
            values = self._values()
            result = {"general": {"content_language": values["general"]["content_language"]}}
            for name in PROVIDERS:
                config = values[name]
                public_fields = MODELS[name]().model_dump(exclude={"api_key"})
                public = {key: config[key] for key in public_fields}
                key = config.get("api_key", "")
                if name == "gemini" and key and key in public["model"]:
                    public["model"] = ""  # Never echo even a damaged vault's key-as-model value.
                configured = bool(config["model"]) if name == "ollama" else bool(key)
                if name == "gemini":
                    public['models'] = self._gemini_models(config)
                    public['model_verified'] = bool(key and public['model'] in public['models'])
                    configured = public['model_verified']
                if name == "openai":
                    configured = configured and config["enabled"]
                status = "Hazır" if configured else "Yapılandırılmadı"
                message = "Bilgiler kaydedildi; bağlantı henüz doğrulanmadı." if configured else "İsteğe bağlı. Bu hizmeti kullanmadan devam edebilirsiniz."
                if name == "ai33":
                    status = "API belgeleri gerekli" if key else "Yapılandırılmadı"
                    message = "AI33 API belgeleri gerekli. Seslendirme ve gerçek bağlantı testi kapalıdır."
                test = config.get("last_test")
                if test:
                    status = test["status"] if configured or test["status"] == "Hata" else status
                    message = test["message"]
                if name == 'gemini' and key and public['model'] and not public['model_verified']:
                    if public['models'] and (not test or test['status'] != 'Hata'):
                        status, message = 'Hata', MODEL_UNAVAILABLE_MESSAGE
                    elif not test:
                        status, message = 'Yapılandırılmadı', 'Model henüz doğrulanmadı. Modelleri Getir düğmesine basıp listeden bir model seçin ve Kaydet deyin.'
                public.update(has_api_key=bool(key), masked_api_key=mask_secret(key), status=status,
                              message=message, connection_test_available=(name in ("ollama", "gemini")))
                result[name] = public
            result["ffmpeg"] = ffmpeg_status()
            result["youtube"] = {"status": "Daha sonra", "message": "YouTube bağlantısı bu aşamada kullanılamaz."}
            return result

    def save(self, section: str, payload: dict) -> dict:
        if section not in MODELS:
            raise SettingsInputError("Bu ayar bölümü kullanılamıyor.")
        try:
            model = MODELS[section].model_validate(payload)
        except ValidationError as error:
            # Never return Pydantic's `input`, which can contain a complete secret.
            hints = []
            for item in error.errors(include_input=False, include_context=False):
                field = str(item["loc"][0]) if item["loc"] else "alan"
                labels = {"api_key": "API anahtarı", "base_url": "Adres", "model": "Model",
                          "voice_id": "Ses kimliği", "enabled": "OpenAI seçimi", "content_language": "Dil"}
                hints.append(labels.get(field, "Ayar alanı"))
            raise SettingsInputError("Geçersiz bilgi: " + ", ".join(dict.fromkeys(hints)) + ". Adresi http:// veya https:// ile girin; anahtar en az 8 karakter olmalı ve boşluk içermemelidir.") from None
        with self.store.lock:
            values = self._values()
            if section == "gemini":
                secret = model.api_key.get_secret_value() if model.api_key is not None else values[section].get("api_key", "")
                proposed_model = model.model if "model" in model.model_fields_set else values[section]["model"]
                if secret and secret in proposed_model:
                    raise SettingsInputError("API anahtarını yalnızca anahtar alanına girin; model alanını düzeltin.")
                key_changed = secret != values[section].get('api_key', '')
                if 'model' in model.model_fields_set and proposed_model:
                    if key_changed or proposed_model not in self._gemini_models(values[section]):
                        raise SettingsInputError('Önce API anahtarını kaydedip Modelleri Getir düğmesine basın; listeden geçerli bir model seçin.')
                if key_changed:
                    values[section].pop('available_models', None)
                    values[section]['model'] = ''
            updated = model.model_dump(exclude_unset=True, exclude={"api_key"})
            values[section].update(updated)
            if isinstance(model, KeySettings) and model.api_key is not None:
                values[section]["api_key"] = model.api_key.get_secret_value()
            values[section].pop("last_test", None)
            self.store.write(values)
            return self.safe_view()

    def clear(self, section: str) -> dict:
        if section not in MODELS:
            raise SettingsInputError("Bu ayar bölümü kullanılamıyor.")
        with self.store.lock:
            values = self._values()
            values.pop(section, None)
            self.store.write(values)
            return self.safe_view()

    def ollama_config(self) -> dict:
        with self.store.lock:
            return self._values()["ollama"].copy()

    def gemini_config(self) -> dict:
        """Backend-only credentials; this snapshot is never an HTTP response."""
        with self.store.lock:
            return self._values()["gemini"].copy()

    def script_config(self, provider: str) -> dict:
        """Private backend credentials, never returned by a route."""
        if provider not in ('gemini', 'ollama', 'openai'):
            raise SettingsInputError('Geçerli bir senaryo motoru seçin.')
        with self.store.lock:
            return self._values()[provider].copy()

    def secret_values(self) -> tuple[str, ...]:
        with self.store.lock:
            return tuple(value.get('api_key') for value in self._values().values()
                         if isinstance(value, dict) and isinstance(value.get('api_key'), str) and value['api_key'])

    def record_gemini_models(self, tested: dict, models: list[str]) -> dict:
        with self.store.lock:
            values = self._values()
            config = values['gemini']
            if config.get('api_key', '') != tested.get('api_key', ''):
                raise SettingsInputError('Gemini anahtarı sorgu sırasında değişti. Modelleri yeniden getirin.')
            config['available_models'] = models
            if config['model'] and config['model'] not in self._gemini_models(config):
                config['last_test'] = {'status': 'Hata', 'message': MODEL_UNAVAILABLE_MESSAGE}
            else:
                config['last_test'] = {'status': 'Hazır', 'message': 'Gemini model listesi alındı. Listeden bir model seçip Kaydet deyin.'}
            self.store.write(values)
            return self.safe_view()

    def record_gemini_test(self, tested: dict, outcome: dict, models: list[str] | None = None) -> dict:
        with self.store.lock:
            values = self._values()
            if any(values["gemini"].get(key, "") != tested.get(key, "") for key in ("api_key", "model")):
                raise SettingsInputError("Gemini ayarları test sırasında değişti. Bağlantıyı yeniden test edin.")
            # Only fixed, safe status messages are stored; no Google response body.
            if models is not None:
                values['gemini']['available_models'] = models
            values["gemini"]["last_test"] = {"status": outcome["status"], "message": outcome["message"]}
            self.store.write(values)
            return self.safe_view()

    def record_ollama_test(self, tested: dict, outcome: dict) -> dict:
        with self.store.lock:
            values = self._values()
            if any(values["ollama"][key] != tested[key] for key in ("base_url", "model")):
                raise SettingsInputError("Ayarlar test sırasında değişti. Bağlantıyı yeniden test edin.")
            values["ollama"]["last_test"] = outcome
            self.store.write(values)
            return self.safe_view()
