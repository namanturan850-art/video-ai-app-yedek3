import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from app.languages import validate_language


class ScriptError(Exception):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


class ScriptOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    provider: Literal['gemini', 'ollama', 'openai'] = 'gemini'
    mode: Literal['original', 'translate_owned'] = 'original'
    language: str = 'de'
    _language = field_validator('language')(validate_language)
    content_type: str = Field(default='', max_length=150)
    tone: str = Field(default='Otomatik', max_length=150)
    audience: str = Field(default='', max_length=500)
    instructions: str = Field(default='', max_length=4000)
    reference_notes: str = Field(default='', max_length=8000)
    reference_text: str = Field(default='', max_length=30000)
    owned_text: str = Field(default='', max_length=100000)
    owns_text: bool = False
    words_per_minute_min: int = Field(default=125, ge=80, le=220)
    words_per_minute_max: int = Field(default=145, ge=80, le=220)
    confirm_replace_approved: bool = False

    @model_validator(mode='after')
    def valid(self):
        if self.words_per_minute_min > self.words_per_minute_max:
            raise ValueError('Minimum konuşma hızı maksimumdan büyük olamaz.')
        if self.mode == 'translate_owned':
            if not self.owns_text or not self.owned_text.strip():
                raise ValueError('Çeviri için kendi metninizi girin ve metnin size ait olduğunu onaylayın.')
            if self.reference_text or self.reference_notes:
                raise ValueError('Çeviri modunda üçüncü taraf referansı kullanmayın; yalnızca kendi metninizi girin.')
        elif self.owned_text or self.owns_text:
            raise ValueError('Kendi metninizi çevirmek için ayrı çeviri modunu seçin.')
        return self


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra='allow')
    content_type: str = Field(min_length=1, max_length=150)
    core_topic: str = Field(min_length=1, max_length=1000)
    target_audience: str = Field(default='', max_length=1000)
    main_hook: str = Field(min_length=1, max_length=1500)
    viewer_promise: str = Field(min_length=1, max_length=1500)
    tone: str = Field(default='', max_length=500)
    pacing: str = Field(default='', max_length=1000)
    section_strategy: str = Field(min_length=1, max_length=2000)
    retention_strategy: str = Field(default='', max_length=2000)
    information_density: str = Field(default='', max_length=1000)
    visual_opportunities: list[str] = Field(default_factory=list, max_length=30)
    key_topics: list[str] = Field(min_length=1, max_length=50)
    cta_style: str = Field(default='', max_length=500)


class ScriptSection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1500)
    key_points: list[str] = Field(default_factory=list, max_length=30)
    target_words: int = Field(ge=20, le=900)
    transition: str = Field(default='', max_length=1000)


class ScriptPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sections: list[ScriptSection] = Field(min_length=1, max_length=80)


def word_count(text):
    return len(re.findall(r"[^\W_]+(?:['’\-][^\W_]+)*", text, re.UNICODE))


def duration_metrics(text, minutes, options):
    count = word_count(text)
    low, high = options['words_per_minute_min'], options['words_per_minute_max']
    return {'word_count': count, 'target_minutes': minutes,
            'target_word_min': math.ceil(minutes * low), 'target_word_max': math.floor(minutes * high),
            'estimated_minutes': round(count / ((low + high) / 2), 2),
            'estimated_min_minutes': round(count / high, 2), 'estimated_max_minutes': round(count / low, 2)}
