from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.scripts.models import ScriptError

ACTIVE=('queued','preparing','rendering','validating')
LABELS={'queued':'Sırada','preparing':'Hazırlanıyor','rendering':'Render ediliyor','validating':'Video doğrulanıyor',
        'completed':'Tamamlandı','error':'Hata','cancelled':'İptal edildi'}
SOURCE_MESSAGE='Video kaynakları birbiriyle eşleşmiyor. Güncel seslendirme, altyazı ve medya planını kontrol edin.'


class RenderError(ScriptError):
    def __init__(self,category,message,status_code=409,*,diagnostic=None):
        from app.rendering.diagnostics import safe_diagnostic
        super().__init__(message,status_code);self.category=category
        self.diagnostic=safe_diagnostic(diagnostic)


class RenderOptions(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    encoder: Literal['auto','nvenc','cpu']='auto'
    montage_engine: Literal['native','openmontage']='native'
    editing_style: Literal['basic','balanced','dynamic','adaptive']='adaptive'
    edit_variation_seed: str | None=Field(default=None,min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    subtitle_display: Literal['full','emphasis','none'] | None=None
    subtitle_burned: bool=True
    music_enabled: bool=False
    music_volume: float=Field(default=.12,ge=0,le=.3)
    music_fade_in: float=Field(default=2,ge=0,le=30)
    music_fade_out: float=Field(default=3,ge=0,le=30)
    music_ducking: bool=True


def options(payload):
    try:
        result=RenderOptions.model_validate(payload).model_dump()
        if 'subtitle_burned' in payload and 'subtitle_display' not in payload:result['subtitle_display']='full' if payload['subtitle_burned'] else 'emphasis'
        if result['subtitle_display'] is not None:result['subtitle_burned']=result['subtitle_display']=='full'
        return result
    except ValidationError:
        raise RenderError('input_invalid','Render ayarlarını kontrol edin. Encoder ve kurgu stili listeden seçilmeli; müzik seviyesi 0–0,30 arasında olmalı.',422) from None


def encoder_label(value):return 'NVIDIA NVENC' if value=='h264_nvenc' else 'CPU / libx264' if value=='libx264' else 'Henüz seçilmedi'
