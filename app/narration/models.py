"""Internal records: these names do not imply a remote API response schema."""
import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.scripts.models import ScriptError

OFFICIAL_BASE = 'https://api.ai33.pro'
VOICE_PROVIDERS = ('elevenlabs','minimax','clone','edge','vbee','fishaudio')
VOICE_ID_PREFIXES = ('elevenlabs_', 'minimax_', 'clone_', 'edge_', 'kokoro_', 'vbee_', 'fishaudio_')
SCHEMA_MESSAGE = 'AI33 görev yanıtı bu sürümün beklediği biçimden farklı.'


class NarrationError(ScriptError):
    def __init__(self,category,message,status_code=503,diagnostic=None,remote_task_id=None):
        super().__init__(message,status_code)
        self.category,self.diagnostic=category,diagnostic
        # Backend-only checkpoint hint, never a provider payload or download URL.
        self.remote_task_id=remote_task_id


class Voice(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    provider: Literal['elevenlabs','minimax','clone','edge','vbee','fishaudio']
    voice_id: str = Field(min_length=1,max_length=150)
    display_name: str = Field(default='',max_length=300)
    language: str = Field(default='',max_length=100)
    gender: str = Field(default='',max_length=100)
    preview_url: str = Field(default='',max_length=2000)


class NarrationInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    source_script_version_id: str
    voice_provider: Literal['elevenlabs','minimax','clone','edge','vbee','fishaudio']
    voice_id: str = Field(min_length=1,max_length=150)
    speed: float = Field(default=1.0,ge=.5,le=1.5)
    cost_confirmed: bool = False
    kind: Literal['narration','preview'] = 'narration'
    regenerate_confirmed: bool = False


def validate_input(payload):
    try:return NarrationInput.model_validate(payload)
    except ValidationError:
        raise NarrationError('invalid_request','Ses sağlayıcısını ve ses seçimini kontrol edin. Hız 0,5–1,5 arasında olmalı.',422) from None


def script_fingerprint(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def safe_task_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,150}',value):
        raise NarrationError('unexpected_task_schema',SCHEMA_MESSAGE,502)
    return value


PREVIEW_TEXT = {
    'de':'Dies ist eine kurze Sprachprobe. Willkommen zu diesem Video.',
    'es':'Esta es una breve prueba de voz. Bienvenidos a este vídeo.',
    'en':'This is a short voice sample. Welcome to this video.',
    'fr':'Ceci est un court essai de voix. Bienvenue dans cette vidéo.',
    'tr':'Bu kısa bir ses denemesidir. Bu videoya hoş geldiniz.'}
