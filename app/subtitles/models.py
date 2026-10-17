import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from app.scripts.models import ScriptError

TIMING_SOURCE = 'approximate_audio_duration'
TIMING_LABEL = 'Ses süresine göre yaklaşık zamanlama'
# Future alignment adapters can return exact_provider, but none is implemented here.
TimingSource = Literal['approximate_audio_duration', 'exact_provider']

class SubtitleError(ScriptError):
    def __init__(self, category, message, status_code=422):
        super().__init__(message, status_code)
        self.category = category


def valid_duration(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value < 86400


class CueInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=5000)

    @field_validator('text')
    @classmethod
    def safe_text(cls, value):
        if any(ord(c) < 32 and c not in '\n\r\t' for c in value) or '\x7f' in value:
            raise ValueError()
        value = '\n'.join(' '.join(line.split()) for line in value.splitlines() if line.strip())
        if not value: raise ValueError()
        return value


def validate_cues(payload, duration, *, allow_empty=False):
    if not isinstance(payload, list) or not (0 if allow_empty else 1) <= len(payload) <= 20000:
        raise SubtitleError('invalid_cues', 'En az bir altyazı gerekli; en fazla 20.000 altyazı kaydedilebilir.')
    result = []
    previous = 0.0
    for index, item in enumerate(payload, 1):
        try: cue = CueInput.model_validate(item).model_dump()
        except ValidationError:
            raise SubtitleError('invalid_cues', f'{index}. altyazı: Başlangıç negatif olamaz; zamanlar geçerli sayı, metin dolu olmalı.') from None
        if cue['end'] <= cue['start']:
            raise SubtitleError('invalid_cues', f'{index}. altyazı: Bitiş başlangıçtan sonra olmalı.')
        if cue['start'] < previous:
            raise SubtitleError('invalid_cues', f'{index}. altyazı: Zamanlar sıralı olmalı ve altyazılar örtüşmemeli.')
        if cue['end'] > duration + .001:
            raise SubtitleError('invalid_cues', f'{index}. altyazı: Bitiş ses süresini aşamaz.')
        # Millisecond precision is shared by the editor, database and exported files.
        cue.update(start=round(cue['start'], 3), end=round(min(cue['end'], duration), 3), index=index)
        if cue['end'] <= cue['start']:
            raise SubtitleError('invalid_cues', f'{index}. altyazı: En az bir milisaniye süre gerekli.')
        previous = cue['end']
        result.append(cue)
    return result
