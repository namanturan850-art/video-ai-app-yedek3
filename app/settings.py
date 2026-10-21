"""Part 2 configuration only; no content or project generation."""
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from app.secret_store import SettingsStore, SettingsStorageError
from app.providers.gemini import normalize_model, MODEL_UNAVAILABLE_MESSAGE
from app.languages import validate_language
from app.narration.models import OFFICIAL_BASE


class SettingsInputError(Exception):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GeneralSettings(StrictModel):
    content_language: str = 'de'
    appearance_theme: Literal['premiere','turquoise','purple','blue','orange','light'] = 'premiere'
    accent_color: str = '#8065E8'
    # AI script writing (Senaryo oluştur, AI Yönetmen purpose/script, source
    # analysis) is kept in the code but OFF: the owner pastes their own text.
    script_generation: bool = False
    # The AI (Gemini) looks at stock candidates the local image model (CLIP)
    # is unsure about. OFF by default: Medyayı Tamamla then sends no Gemini
    # request at all. Stored as 'gemini_visual_check' (an older stored
    # 'ai_visual_check' value — default on — is ignored).
    ai_visual_check: bool = False
    # Channel moments are OFF by default: the video starts with the first scene and
    # ends with the last one; [GİRİŞ]/[KAPANIŞ] markers or “abone ol” sentences add nothing.
    intro_card: bool = False      # opening card (title + channel name)
    outro_card: bool = False      # “Abone ol” button + bell
    end_screen: bool = False      # 20 s YouTube end screen after the narration
    # “Video dönemi”: the period/look filter of Medyayı Tamamla. auto = read from the text (weighted, modern when
    # unsure); modern = no period filter at all; historic = the period found in the text, strict.
    era_mode: Literal['auto', 'modern', 'historic'] = 'auto'
    _language = field_validator('content_language')(validate_language)

    @field_validator('accent_color')
    @classmethod
    def colour(cls,value):
        import re
        value=value.upper()
        if not re.fullmatch(r'#[0-9A-F]{6}',value): raise ValueError('Vurgu rengi #24D3C5 biçiminde olmalıdır.')
        return value


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


class CustomMapboxStyle(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    uri: str
    name: str = Field(min_length=1, max_length=80)

    @field_validator('uri')
    @classmethod
    def style_uri(cls, value):
        from app.providers.mapbox_styles import validate_uri
        return validate_uri(value)


class MapboxSettings(KeySettings):
    selected_style: str = ''  # empty preserves the user's existing URL overrides
    custom_styles: list[CustomMapboxStyle] = Field(default_factory=list, max_length=20)

    @field_validator('selected_style')
    @classmethod
    def selected(cls, value):
        from app.providers.mapbox_styles import validate_uri
        return validate_uri(value) if value else value

    @field_validator('custom_styles')
    @classmethod
    def unique_styles(cls, value):
        from app.providers.mapbox_styles import BUILTINS
        identities = [s.uri for s in value]
        if len(set(identities)) != len(identities) or any(uri in {'mapbox://styles/mapbox/' + i for i, _ in BUILTINS} for uri in identities):
            raise ValueError('Bu stil zaten listede.')
        return value
    # Satellite map tiles (Harita stili → Uydu görüntüsü). The key is stored like every other
    # key (never in .env or source files). The URL template is the documented Raster Tiles API
    # pattern (MAPBOX_INTEGRATION_NOTES.md); it is a setting so it can be corrected without code.
    tile_url: str = Field(default='https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90', max_length=300)

    # Static Images API (one picture per scene, with bearing/pitch) for “Eğik görünüm”.
    static_url: str = Field(default='https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom},{bearing},{pitch}/{width}x{height}@2x', max_length=300)
    oblique: bool = True  # Eğik görünüm (3B his); off: the flat (pitch 0) tile map
    # Monthly safety limits (requests sent; downloaded pictures reused from the cache are not counted).
    monthly_tile_limit: int = Field(default=600_000, ge=0, le=100_000_000)
    monthly_static_limit: int = Field(default=40_000, ge=0, le=10_000_000)
    # Forward geocoding for map-marker places the offline lists lack (MAPBOX_INTEGRATION_NOTES.md).
    geocode_url: str = Field(default='https://api.mapbox.com/search/geocode/v6/forward', max_length=300)

    @field_validator('geocode_url')
    @classmethod
    def geocode_template(cls, value):
        value = value.strip()
        if not value.startswith('https://api.mapbox.com/') or '?' in value:
            raise ValueError('Yer arama adresi https://api.mapbox.com/ ile başlamalı (anahtar adrese yazılmaz).')
        return value

    @field_validator('static_url')
    @classmethod
    def static_template(cls, value):
        value = value.strip()
        if not value.startswith('https://api.mapbox.com/') or not all('{%s}' % p in value for p in ('lon', 'lat', 'zoom', 'bearing', 'pitch', 'width', 'height')) or '?' in value:
            raise ValueError('Eğik görünüm adresi https://api.mapbox.com/ ile başlamalı ve {lon}, {lat}, {zoom}, {bearing}, {pitch}, {width}, {height} içermeli (anahtar adrese yazılmaz).')
        return value

    @field_validator('tile_url')
    @classmethod
    def template(cls, value):
        value = value.strip()
        if not value.startswith('https://api.mapbox.com/') or not all(p in value for p in ('{z}', '{x}', '{y}')) or '?' in value:
            raise ValueError('Karo adresi https://api.mapbox.com/ ile başlamalı ve {z}, {x}, {y} içermeli (anahtar adrese yazılmaz).')
        return value


class OpenAISettings(KeySettings):
    enabled: bool = False
    model: str = Field(default="", max_length=150)

    @field_validator('model')
    @classmethod
    def model_name(cls, value):
        value = value.strip()
        if any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError('Model adını boşluksuz girin.')
        return value

    @field_validator('api_key')
    @classmethod
    def header_key(cls, value):
        if value is not None and not value.get_secret_value().isascii():
            raise ValueError('API anahtarını olduğu gibi girin.')
        return value


class GeminiSettings(KeySettings):
    model: str = Field(default="", max_length=157)
    # Backup chain order chosen by the owner; None = automatic from the model list.
    fallback_models: list[str] | None = Field(default=None, max_length=20)

    @field_validator("model")
    @classmethod
    def model_name(cls, value):
        return normalize_model(value)

    @field_validator("fallback_models")
    @classmethod
    def chain_names(cls, value):
        return None if value is None else [normalize_model(v) for v in value if isinstance(v, str) and v.strip()]

    @field_validator("api_key")
    @classmethod
    def header_key(cls, value):
        if value is not None and not value.get_secret_value().isascii():
            raise ValueError("API anahtarını olduğu gibi, boşluksuz girin.")
        return value


CLAUDE_MODELS = {'claude-opus-5-5': 'Claude Opus 5.5 — en iyi kalite (önerilen)',
                 'claude-sonnet-5-5': 'Claude Sonnet 5.5 — daha ucuz, hızlı',
                 'claude-haiku-5-5': 'Claude Haiku 5.5 — en ucuz, basit işler'}


class ClaudeSettings(KeySettings):
    model: Literal['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'] = 'claude-opus-5-5'
    # Claude becomes the script/scene "director" for every project when ready.
    default_engine: bool = False  # Gemini (free tier) unless the owner opts in

    @field_validator('api_key')
    @classmethod
    def header_key(cls, value):
        if value is not None and not value.get_secret_value().isascii():
            raise ValueError('API anahtarını olduğu gibi, boşluksuz girin.')
        return value


class AI33Settings(KeySettings):
    base_url: str = Field(default=OFFICIAL_BASE, max_length=500)
    voice_id: str = Field(default="", max_length=150)
    model: str = Field(default="", max_length=150)
    voice_provider: Literal['elevenlabs','minimax','clone','edge','vbee','fishaudio'] = 'elevenlabs'
    speed: float = Field(default=1.0,ge=.5,le=1.5,allow_inf_nan=False)

    @field_validator('api_key')
    @classmethod
    def ascii_key(cls,value):
        if value is not None and not value.get_secret_value().isascii():
            raise ValueError('API anahtarını olduğu gibi, boşluksuz girin.')
        return value

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        return web_url(value)


class OpenSourceSettings(BaseModel):
    """A source that needs no key (Wikimedia Commons, NASA, Internet Archive): only an on/off switch for
    Medyayı Tamamla (a switched-off source saves search time) and a connection test."""
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True


MODELS = {"general": GeneralSettings, "ollama": OllamaSettings, "openai": OpenAISettings,
          "gemini": GeminiSettings, "pexels": KeySettings, "pixabay": KeySettings, "europeana": KeySettings, "ai33": AI33Settings,
          "claude": ClaudeSettings, "youtube": KeySettings, "wikimedia": OpenSourceSettings, "nasa": OpenSourceSettings, "archive": OpenSourceSettings, "mapbox": MapboxSettings}
PROVIDERS = ("ollama", "openai", "gemini", "pexels", "pixabay", "ai33", "claude", "youtube", "wikimedia", "nasa", "archive", "mapbox", "europeana")


def stored_secrets(values):
    return tuple(value.get('api_key') for value in values.values()
                 if isinstance(value, dict) and isinstance(value.get('api_key'), str) and value['api_key'])


def mask_secret(value: str) -> str:
    if not value:
        return ""
    # Very short historical/corrupted keys never reveal their complete value.
    return "••••••••••" + (value[-4:] if len(value) >= 8 else "")


def ffmpeg_status() -> dict:
    from app.rendering import tools
    from app.rendering.models import RenderError
    try:
        detected=tools.discover()
        message=detected['message']
        path=detected.get('ffmpeg') or detected.get('executable')
        warning=tools.compat_warning(path) if detected.get('found') and path else ''
        return {'status':'Uyumsuz sürüm' if warning else detected['status'],'found':detected['found'],
                'executable_path':'','message':(message+' '+warning).strip() if warning else message}
    except RenderError as error:
        return {'status':'Hata','found':False,'executable_path':'','message':str(error)}


class SettingsService:
    def __init__(self, store: SettingsStore):
        self.store = store
        # One-way credential retirement. Other settings remain byte-for-byte values.
        with self.store.lock:
            try:
                values = self.store.read()
            except SettingsStorageError:
                # Keep health/diagnostics available. Requests that use settings still
                # raise the safe 503 handler; never replace or rewrite a damaged vault.
                return
            if 'magnific' in values:
                values.pop('magnific', None)
                self.store.write(values)

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
            from app.scripts.engine import SecretGuard
            secrets = stored_secrets(values)
            guard = SecretGuard(secrets)
            result = {"general": {"content_language": values["general"]["content_language"],
                                  "appearance_theme": values["general"].get("appearance_theme", "premiere"),
                                  "accent_color": values["general"].get("accent_color", "#8065E8"),
                                  "ai_visual_check": bool(values["general"].get("gemini_visual_check", False)),
                                  **{k: bool(values["general"].get(k, False)) for k in ('intro_card', 'outro_card', 'end_screen')}}}
            for name in PROVIDERS:
                config = values[name]
                public_fields = MODELS[name]().model_dump(exclude={"api_key"})
                public = {key: config[key] for key in public_fields}
                public = guard.clean(public)
                key = config.get("api_key", "")
                if name in ('gemini', 'openai') and any(secret in config['model'] for secret in secrets):
                    public["model"] = ""  # Never echo even a damaged vault's key-as-model value.
                configured = bool(config["model"]) if name == "ollama" else bool(key)
                if name == "gemini":
                    public['models'] = [model for model in self._gemini_models(config) if not any(secret in model for secret in secrets)]
                    public['model_verified'] = bool(key and public['model'] in public['models'])
                    configured = public['model_verified']
                    from app.providers.gemini_chain import chain_models, eligible, short
                    chain = chain_models({**config, 'available_models': public['models']}) if public['model_verified'] else []
                    used_up = self._active_exhausted(config)
                    public['fallback_chain'] = [{'model': m, 'label': short(m), 'exhausted_until': used_up.get(m)} for m in chain]
                    public['fallback_candidates'] = [{'model': m, 'label': short(m)} for m in public['models'] if eligible(m) and m not in chain]
                    public['fallback_custom'] = isinstance(config.get('fallback_models'), list)
                if name == "openai":
                    configured = configured and config['enabled'] and bool(public['model'])
                if name in ('wikimedia', 'nasa', 'archive'):
                    configured = True  # no key needed
                if name == 'pexels':
                    from app.stock.providers import PEXELS_ENABLED
                    public['disabled'] = not PEXELS_ENABLED
                if name == "claude":
                    public['models'] = [{'id': key, 'label': label} for key, label in CLAUDE_MODELS.items()]
                status = "Hazır" if configured else "Yapılandırılmadı"
                message = "Bilgiler kaydedildi; bağlantı henüz doğrulanmadı." if configured else "İsteğe bağlı. Bu hizmeti kullanmadan devam edebilirsiniz."
                if name == 'wikimedia':
                    message = 'Anahtar gerekmez; Medyayı Tamamla Wikimedia Commons’u kendiliğinden kullanır. İsterseniz Bağlantıyı Test Et ile kontrol edin.'
                if name == 'nasa':
                    message = 'Anahtar gerekmez; Medyayı Tamamla NASA Görsel Kütüphanesi’ni kendiliğinden kullanır (yalnız görsel). İsterseniz Bağlantıyı Test Et ile kontrol edin.'
                if name == 'archive':
                    message = 'Anahtar gerekmez; Medyayı Tamamla Internet Archive film arşivini kendiliğinden kullanır (yalnız video, yalnız Public Domain / CC0 / CC BY / CC BY-SA). İsterseniz Bağlantıyı Test Et ile kontrol edin.'
                if name == 'pexels' and public.get('disabled'):
                    status, message = 'Kullanılmıyor', 'Pexels şu an yeni anahtar vermediği için kapalı; medya Pixabay ve Wikimedia Commons’tan aranır. Anahtar alanı ileride kullanmak için duruyor.'
                if name == "ai33":
                    from app.narration.provider import OpenSpeakerProvider
                    public.update(official_base_url=OFFICIAL_BASE,
                                  voices=guard.clean(config.get('available_voices',[])),
                                  voice_name=guard.clean(config.get('voice_name','')),
                                  contract_ready=OpenSpeakerProvider.contract_ready,
                                  documentation_message='Canlı AI33 TTS görev yapısı doğrulandı.' if OpenSpeakerProvider.contract_ready else 'Ses listesi kullanılabilir. Tamamlanan TTS görevindeki ses çıktı alanı henüz doğrulanmadı; ücretli seslendirme ve üretim önizlemesi kapalıdır.')
                    message = 'Anahtar kaydedildi. Bağlantı testi yalnız kredi erişimini kontrol eder; ses üretmez.' if key else message
                test = config.get("last_test")
                if name=='ai33' and test and test.get('status')=='API belgeleri gerekli':test=None
                if test:
                    status = test["status"] if configured or test["status"] == "Hata" else status
                    message = test["message"]
                if name == 'gemini' and key and public['model'] and not public['model_verified']:
                    if public['models'] and (not test or test['status'] != 'Hata'):
                        status, message = 'Hata', MODEL_UNAVAILABLE_MESSAGE
                    elif not test:
                        status, message = 'Yapılandırılmadı', 'Model henüz doğrulanmadı. Modelleri Getir düğmesine basıp listeden bir model seçin ve Kaydet deyin.'
                if name == 'mapbox':
                    from app.providers.satellite import usage_text
                    message = f'{message} · {usage_text()}'
                if name in ('wikimedia', 'nasa', 'archive') and not config.get('enabled', True):
                    status, message = 'Kapalı', 'Bu kaynak kapalı: Medyayı Tamamla burada aramaz (zaman kazandırır). Açmak için kutuyu işaretleyip Kaydet deyin.'
                message = guard.clean(message)
                public.update(has_api_key=bool(key), masked_api_key=mask_secret(key), status=status,
                              message=message, connection_test_available=(name in ("ollama", "gemini", 'openai','pexels','pixabay','ai33','claude','youtube','wikimedia','nasa','archive','europeana')))
                result[name] = public
            result["ffmpeg"] = ffmpeg_status()
            result['images'] = self.image_view()
            return result

    def save(self, section: str, payload: dict) -> dict:
        if section == 'images':
            self.save_images(payload)
            return self.safe_view()
        if section not in MODELS:
            raise SettingsInputError("Bu ayar bölümü kullanılamıyor.")
        try:
            model = MODELS[section].model_validate(payload)
        except ValidationError as error:
            # Never return Pydantic's `input`, which can contain a complete secret.
            hints = []
            for item in error.errors(include_input=False, include_context=False):
                field = str(item["loc"][0]) if item["loc"] else "alan"
                labels = {"api_key": "API anahtarı", "base_url": "Adres", "model": "Model", "default_engine": "Varsayılan motor",
                          "voice_id": "Ses kimliği", "voice_provider":"Ses sağlayıcısı", "speed":"Hız", "enabled": "OpenAI seçimi", "content_language": "Dil"}
                hints.append(labels.get(field, "Ayar alanı"))
            detail = 'API anahtarını eksiksiz, boşluksuz ve maskesiz girin (en az 8 karakter).' if 'API anahtarı' in hints else 'Hız 0,5–1,5 arasında olmalı.' if 'Hız' in hints else 'Model adını boşluksuz girin.' if 'Model' in hints else 'Adres http:// veya https:// ile başlamalı; anahtar veya parola içermemeli.' if 'Adres' in hints else 'Seçimi ekrandaki seçeneklerle yapın; yalnızca bu bölümün alanlarını kaydedin.'
            raise SettingsInputError('Geçersiz bilgi: ' + ', '.join(dict.fromkeys(hints)) + '. ' + detail) from None
        with self.store.lock:
            values = self._values()
            proposed_fields = model.model_dump(exclude={'api_key'})
            secrets = list(self.secret_values())
            if isinstance(model, KeySettings) and model.api_key:
                secrets.append(model.api_key.get_secret_value())
            if any(secret in str(value) for value in proposed_fields.values() for secret in secrets):
                raise SettingsInputError('API anahtarını yalnızca anahtar alanına girin; diğer alanları düzeltin.')
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
                    values[section]['fallback_models'] = None
                    values[section].pop('exhausted', None)
                if 'fallback_models' in model.model_fields_set and model.fallback_models is not None:
                    unknown = [m for m in model.fallback_models if m not in self._gemini_models(values[section])]
                    if unknown:
                        raise SettingsInputError('Yedek model sırasında listede olmayan model var. Modelleri Getir deyip yeniden düzenleyin.')
            updated = model.model_dump(exclude_unset=True, exclude={"api_key"})
            if section == 'general' and 'ai_visual_check' in updated:
                updated['gemini_visual_check'] = updated.pop('ai_visual_check')
            if section=='ai33':
                config=values[section]
                if 'voice_id' in updated and updated['voice_id']:
                    voices=config.get('available_voices',[])
                    chosen=next((v for v in voices if v['voice_id']==updated['voice_id'] and v['provider']==updated.get('voice_provider',config['voice_provider'])),None)
                    if chosen:config['voice_name']=chosen['display_name']
                    elif updated['voice_id']!=config['voice_id']:raise SettingsInputError('Önce Sesleri Getir düğmesiyle doğrulanmış listeden ses seçin.')
                if 'voice_provider' in updated and updated['voice_provider']!=config['voice_provider']:
                    if not updated.get('voice_id') or updated['voice_id']==config['voice_id']:updated['voice_id']=''
                    config['available_voices']=[];config['voice_name']=''
            if section == 'mapbox':
                from app.providers.mapbox_styles import selection_valid
                if not selection_valid({**values[section], **updated}):
                    raise SettingsInputError('Önce stili listeye ekleyin. Seçili stili kaldırmak için önce başka stil seçin.')
            values[section].update(updated)
            if isinstance(model, KeySettings) and model.api_key is not None:
                if section=='ai33' and values[section].get('api_key')!=model.api_key.get_secret_value():
                    values[section]['available_voices']=[]
                values[section]["api_key"] = model.api_key.get_secret_value()
            values[section].pop("last_test", None)
            self.store.write(values)
            return self.safe_view()

    def clear(self, section: str) -> dict:
        if section == 'images':
            with self.store.lock:
                values = self._values(); values.pop('images', None); self.store.write(values)
            return self.safe_view()
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

    @staticmethod
    def _active_exhausted(config) -> dict:
        from datetime import datetime
        from app.providers.gemini_chain import now_utc
        marks = config.get('exhausted') if isinstance(config.get('exhausted'), dict) else {}
        active = {}
        for model, until in marks.items():
            try:
                if datetime.fromisoformat(until) > now_utc(): active[model] = until
            except (TypeError, ValueError):
                continue
        return active

    def gemini_exhausted(self) -> dict:
        """{model: reset time} for models whose daily quota is used up today."""
        with self.store.lock:
            return self._active_exhausted(self._values()['gemini'])

    def mark_gemini_exhausted(self, model: str, until: str) -> None:
        with self.store.lock:
            values = self._values()
            values['gemini']['exhausted'] = {**self._active_exhausted(values['gemini']), model: until}
            self.store.write(values)

    def clear_gemini_exhausted(self) -> dict:
        with self.store.lock:
            values = self._values(); values['gemini'].pop('exhausted', None); self.store.write(values)
        return self.safe_view()

    def gemini_config(self) -> dict:
        """Backend-only credentials; this snapshot is never an HTTP response."""
        with self.store.lock:
            return self._values()["gemini"].copy()

    def script_config(self, provider: str) -> dict:
        """Private backend credentials, never returned by a route."""
        if provider not in ('gemini', 'ollama', 'openai', 'claude'):
            raise SettingsInputError('Geçerli bir senaryo motoru seçin.')
        with self.store.lock:
            return self._values()[provider].copy()

    def secret_values(self) -> tuple[str, ...]:
        with self.store.lock:
            return stored_secrets(self._values())

    def moments(self):
        """{'intro_card', 'outro_card', 'end_screen'}: the owner's switches (all off by default)."""
        with self.store.lock:
            general = self._values()['general']
            return {k: bool(general.get(k, False)) for k in ('intro_card', 'outro_card', 'end_screen')}

    def era_mode(self):
        with self.store.lock:
            value = self._values()['general'].get('era_mode', 'auto')
        return value if value in ('auto', 'modern', 'historic') else 'auto'

    def ai_visual_check(self):
        with self.store.lock:
            return bool(self._values()['general'].get('gemini_visual_check', False))

    def script_generation(self):
        """Owner flag (default off). AVS_SCRIPT_GENERATION=1 also turns it on."""
        import os
        if os.environ.get('AVS_SCRIPT_GENERATION') == '1':
            return True
        with self.store.lock:
            return bool(self._values()['general'].get('script_generation', False))

    def youtube_key(self):
        """Private YouTube Data API key ('' when not saved); never returned by a route."""
        with self.store.lock:
            return self._values()['youtube'].get('api_key', '')

    def stock_config(self, provider):
        if provider not in ('pexels','pixabay','youtube','wikimedia','nasa','archive','europeana'):
            raise SettingsInputError('Bu stok sağlayıcısı kullanılamıyor.')
        with self.store.lock:
            return dict(self._values()[provider])

    def mapbox_config(self):
        """{'api_key', 'tile_url'} for the satellite map ('' key = not set)."""
        with self.store.lock:
            config = dict(self._values()['mapbox'])
        default = MapboxSettings()
        selected = config.get('selected_style', '')
        from app.providers.mapbox_styles import static_template
        return {'api_key': config.get('api_key') or '', 'tile_url': config.get('tile_url') or default.tile_url,
                'legacy_static_url': config.get('static_url') or default.static_url,
                'selected_style': selected, 'custom_styles': config.get('custom_styles', []),
                'monthly_tile_limit': int(config.get('monthly_tile_limit', default.monthly_tile_limit)),
                'monthly_static_limit': int(config.get('monthly_static_limit', default.monthly_static_limit)),
                'static_url': static_template(selected) if selected else config.get('static_url') or default.static_url, 'geocode_url': config.get('geocode_url') or default.geocode_url, 'oblique': config.get('oblique', default.oblique) is not False}

    def tts_config(self):
        """Private key and legacy values; outbound URL is always the official API."""
        with self.store.lock:return dict(self._values()['ai33'])

    def record_tts_test(self,tested,outcome):
        with self.store.lock:
            values=self._values()
            if values['ai33'].get('api_key','')!=tested.get('api_key',''):
                raise SettingsInputError('AI33 anahtarı test sırasında değişti. Yeniden test edin.')
            from app.scripts.engine import SecretGuard
            values['ai33']['last_test']=SecretGuard(stored_secrets(values)).clean(outcome)
            self.store.write(values)
        return self.safe_view()

    def record_tts_voices(self,tested,voices):
        from app.narration.models import Voice
        from app.scripts.engine import SecretGuard
        with self.store.lock:
            values=self._values();config=values['ai33']
            if any(config.get(k,'')!=tested.get(k,'') for k in ('api_key','voice_provider')):
                raise SettingsInputError('AI33 ayarları arama sırasında değişti. Sesleri yeniden getirin.')
            try:voices=[Voice.model_validate(v).model_dump() for v in voices]
            except (ValidationError,TypeError):raise SettingsInputError('Doğrulanmış ses listesi okunamadı.') from None
            SecretGuard(stored_secrets(values)).validate(voices)
            if any(v['provider']!=config['voice_provider'] for v in voices):
                raise SettingsInputError('Ses sağlayıcısı arama sırasında değişti. Yeniden deneyin.')
            combined={(v['provider'],v['voice_id']):v for v in config.get('available_voices',[])}
            combined.update({(v['provider'],v['voice_id']):v for v in voices})
            config['available_voices']=list(combined.values())[-1000:]
            self.store.write(values)
        return self.safe_view()

    def record_stock_test(self, provider, tested, outcome):
        with self.store.lock:
            values = self._values()
            if values[provider].get('api_key','') != tested.get('api_key',''):
                raise SettingsInputError('Anahtar test sırasında değişti. Yeniden test edin.')
            from app.scripts.engine import SecretGuard
            values[provider]['last_test'] = SecretGuard(stored_secrets(values)).clean(outcome)
            self.store.write(values)
        return self.safe_view()

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

    def record_openai_test(self, tested: dict, outcome: dict) -> dict:
        with self.store.lock:
            values = self._values()
            if any(values['openai'].get(key) != tested.get(key) for key in ('api_key', 'model', 'enabled')):
                raise SettingsInputError('OpenAI ayarları test sırasında değişti. Yeniden test edin.')
            values['openai']['last_test'] = {key: outcome[key] for key in ('status', 'message')}
            self.store.write(values)
            return self.safe_view()

    def record_claude_test(self, tested: dict, outcome: dict) -> dict:
        with self.store.lock:
            values = self._values()
            if any(values['claude'].get(key) != tested.get(key) for key in ('api_key', 'model')):
                raise SettingsInputError('Claude ayarları test sırasında değişti. Yeniden test edin.')
            values['claude']['last_test'] = {key: outcome[key] for key in ('status', 'message')}
            self.store.write(values)
            return self.safe_view()

    def claude_director(self) -> bool:
        """True when Claude is configured and chosen as the default director."""
        with self.store.lock:
            config = self._values()['claude']
        return bool(config.get('api_key')) and bool(config.get('default_engine'))

    def ai_engine(self):
        """Engine for the director and media selection. Gemini's free tier by
        default; Claude (paid API) only when the owner explicitly chose it.
        None = nothing usable is configured yet."""
        if self.claude_director():
            return 'claude'
        view = self.safe_view()
        return 'gemini' if view['gemini']['model_verified'] else None

    def image_config(self):
        from app.production_settings import ImageSettings
        with self.store.lock:
            config = self._values().get('images', {})
            return {key: config.get(key, value) for key, value in ImageSettings().model_dump().items()}

    def image_view(self):
        from app.scripts.engine import SecretGuard
        with self.store.lock:
            values = self._values()
            result = self.image_config()
            metadata = values.get('images', {})
            result.update(gemini_models=metadata.get('gemini_models', []), local_models=metadata.get('local_models', []), status='Daha sonraki çalıştırma için hazırlandı', message='Ayarlar ve bağlantı kontrolleri çalışır. Model erişimi görsel çıkışı veya lisans uygunluğunu garanti etmez; otomatik görsel çalıştırma/render henüz bağlı değildir.')
            return SecretGuard(self.secret_values()).clean(result)

    def save_images(self, payload):
        from app.production_settings import ImageSettings
        from app.scripts.engine import SecretGuard
        with self.store.lock:
            values = self._values()
            try:
                config = ImageSettings.model_validate({**self.image_config(), **payload}).model_dump()
            except (ValidationError, TypeError):
                raise SettingsInputError('Görsel ayarlarını kontrol edin. Yerel adres, 16:9 çözünürlük ve geçerli motor/ücret seçimi gerekli.') from None
            SecretGuard(self.secret_values()).validate(config)
            try: config['gemini_model'] = normalize_model(config['gemini_model'])
            except ValueError: raise SettingsInputError('Geçerli bir Gemini görsel modeli seçin.') from None
            metadata = values.get('images', {})
            if config['gemini_model'] and config['gemini_model'] not in metadata.get('gemini_models', []):
                raise SettingsInputError('Görsel ayarlarında Gemini modellerini getirip listeden model seçin. Her model görsel çıkışı desteklemez.')
            values['images'] = {**metadata, **config}
            self.store.write(values)

    def record_image_models(self, provider, models, tested):
        if provider not in ('local', 'gemini'): raise SettingsInputError('Bu model keşfi kullanılamıyor.')
        from app.scripts.engine import SecretGuard
        with self.store.lock:
            if provider == 'gemini' and self.gemini_config().get('api_key') != tested.get('api_key') or provider == 'local' and self.image_config()['local_url'] != tested.get('local_url'):
                raise SettingsInputError('Ayarlar değişti; modelleri yeniden getirin.')
            if not isinstance(models, list) or any(not isinstance(x, str) for x in models): raise SettingsInputError('Model listesi okunamadı.')
            SecretGuard(self.secret_values()).validate(models)
            values = self._values(); config = values.setdefault('images', {})
            config[provider + '_models'] = models
            self.store.write(values)
            return self.image_view()
