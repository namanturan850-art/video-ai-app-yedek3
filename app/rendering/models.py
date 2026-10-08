from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.scripts.models import ScriptError

ACTIVE=('queued','preparing','rendering','validating')
LABELS={'queued':'Sırada','preparing':'Hazırlanıyor','rendering':'Render ediliyor','validating':'Video doğrulanıyor',
        'completed':'Tamamlandı','error':'Hata','cancelled':'İptal edildi'}
SOURCE_MESSAGE='Video kaynakları birbiriyle eşleşmiyor. Güncel seslendirme, altyazı ve medya planını kontrol edin.'


class RenderError(ScriptError):
    def __init__(self,category,message,status_code=409):
        super().__init__(message,status_code);self.category=category


class RenderOptions(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    encoder: Literal['auto','nvenc','cpu']='auto'
    subtitle_burned: bool=True
    music_enabled: bool=False
    music_volume: float=Field(default=.12,ge=0,le=.3)
    music_fade_in: float=Field(default=2,ge=0,le=30)
    music_fade_out: float=Field(default=3,ge=0,le=30)
    music_ducking: bool=True


def options(payload):
    try:return RenderOptions.model_validate(payload).model_dump()
    except ValidationError:
        raise RenderError('input_invalid','Render ayarlarını kontrol edin. Encoder listeden seçilmeli; müzik seviyesi 0–0,30 arasında olmalı.',422) from None


def encoder_label(value):return 'NVIDIA NVENC' if value=='h264_nvenc' else 'CPU / libx264' if value=='libx264' else 'Henüz seçilmedi'
