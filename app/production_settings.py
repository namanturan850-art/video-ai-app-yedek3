"""Preparatory preferences; no unknown models, automatic installs or cloud spend."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.settings import OllamaSettings


class ImageSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    engine: Literal['auto', 'local', 'gemini', 'openai', 'off'] = 'auto'
    paid_usage: Literal['off', 'ask', 'allow_fallback'] = 'off'
    local_enabled: bool = False
    local_url: str = 'http://127.0.0.1:8188'
    local_model: str = Field(default='', max_length=200)
    workflow: str = Field(default='', max_length=150)
    license_confirmed: bool = False
    width: int = Field(default=1920, ge=256, le=3840)
    height: int = Field(default=1080, ge=144, le=2160)
    gemini_model: str = Field(default='', max_length=157)
    openai_model: str = Field(default='', max_length=150)
    # YouTube thumbnail: optional Gemini background (quota/cost), off by default.
    thumbnail_ai: bool = False

    @field_validator('local_url')
    @classmethod
    def local_address(cls, value):
        return OllamaSettings.local_address(value)

    @model_validator(mode='after')
    def aspect(self):
        if self.width * 9 != self.height * 16:
            raise ValueError('YouTube görselleri 16:9 olmalıdır.')
        return self


class MusicSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool = False
    mood: str = Field(default='neutral', min_length=1, max_length=100)
    local_file_label: str = Field(default='', max_length=200)
    license_confirmed: bool = False
    volume: float = Field(default=.15, ge=0, le=1)
    fade_in: float = Field(default=2., ge=0, le=30)
    fade_out: float = Field(default=3., ge=0, le=30)
    ducking: bool = True
    section_changes: list[str] = Field(default_factory=list, max_length=80)


class MediaSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    provider: Literal['pexels', 'pixabay', 'local', 'gemini', 'openai', 'user']
    media_id: str = Field(min_length=1, max_length=200)
    width: int = Field(ge=1, le=16384)
    height: int = Field(ge=1, le=16384)
