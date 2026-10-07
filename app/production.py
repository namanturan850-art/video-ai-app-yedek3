"""Visual/edit planning and truthful pre-render checks; no rendering or upload."""
import re
from functools import wraps
from contextlib import closing
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.projects import now
from app.scripts.models import ScriptError, word_count
from app.scripts.storage import dumps

MEDIA_PRIORITY = ['pexels', 'pixabay', 'local', 'cloud_with_permission']


def editable(method):
    @wraps(method)
    def wrapped(self, project_id, *args, **kwargs):
        with self.projects.lock, closing(self.projects._connection()) as connection:
            self.repo._idle(connection, project_id)
            return method(self, project_id, *args, **kwargs)
    return wrapped


class VisualBlock(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    narration: str = Field(min_length=1, max_length=12000)
    purpose: str = Field(min_length=1, max_length=1000)
    mood: str = Field(min_length=1, max_length=100)
    visual_intent: str = Field(min_length=1, max_length=1500)
    stock_query: str = Field(min_length=3, max_length=300)
    alternative_stock_queries: list[str] = Field(min_length=1, max_length=5)
    media_type: Literal['stock_video', 'stock_image', 'ai_image', 'motion_graphic', 'user_media']
    overlay_text: str = Field(default='', max_length=150)
    transition: Literal['hard_cut', 'crossfade', 'fade', 'none']
    motion: Literal['none', 'slow_zoom', 'pan', 'ken_burns', 'overlay', 'emphasis_text']
    composition: Literal['wide', 'medium', 'close', 'detail', 'person', 'object', 'environment', 'movement', 'graphic']
    importance: int = Field(ge=0, le=100)

    @model_validator(mode='after')
    def semantic_queries(self):
        if len(self.stock_query.split()) < 2 or any(not 2 <= len(query.split()) <= 25 for query in self.alternative_stock_queries):
            raise ValueError('Anlamsal stok sorgusu birden fazla anlamlı kelime içermeli.')
        return self


class NarrationTiming(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=12000)
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode='after')
    def range(self):
        if self.end <= self.start: raise ValueError('Zaman aralığı geçersiz.')
        return self


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip()


def visual_blocks(raw, source, language, words_per_minute, start=0):
    try:
        if set(raw) != {'blocks'} or not isinstance(raw['blocks'], list) or not 1 <= len(raw['blocks']) <= 40:
            raise ValueError()
        blocks = [VisualBlock.model_validate(block).model_dump() for block in raw['blocks']]
        if normalize(' '.join(block['narration'] for block in blocks)) != normalize(source):
            raise ValueError()
    except (ValueError, TypeError):
        raise ScriptError('Görsel plan senaryo metniyle eşleşmiyor veya beklenen biçimde değil. Tekrar deneyin.') from None
    for block in blocks:
        duration = word_count(block['narration']) / words_per_minute * 60
        block.update(id=uuid4().hex, language=language, overlay_language=language, stock_query_language='en', timing_source='estimated', start=round(start, 3), end=round(start+duration, 3), media=None, image_status='prepared')
        start += duration
    return blocks


def production_checks(plan, current, project):
    warnings = []
    if not current or current['status'] != 'approved': warnings.append('Geçerli senaryo onaylanmamış.')
    if current:
        from app.scripts.engine import repetition_warnings
        warnings.extend(repetition_warnings(current.get('text', '')))
    if not plan: return warnings + ['Görsel plan henüz oluşturulmadı.', 'Seslendirme ve render sonraki çalıştırma aşaması için hazırlanıyor.']
    if not current or plan['version_id'] != current['id']: warnings.append('Görsel plan eski senaryo sürümüne ait. Yeniden planlayın.')
    blocks = plan['blocks']
    ids, image_run = set(), 0
    for index, block in enumerate(blocks):
        prefix = f'Görsel blok {index+1}: '
        if not block['narration'].strip(): warnings.append(prefix + 'anlatım boş.')
        if not block.get('media'): warnings.append(prefix + 'medya henüz atanmadı.')
        else:
            media = block['media']; identity = (media['provider'], media['media_id'])
            if identity in ids: warnings.append(prefix + 'aynı medya tekrar kullanılıyor.')
            ids.add(identity)
            if (media.get('width'), media.get('height')) != (plan['width'], plan['height']): warnings.append(prefix + 'çözünürlük hedefle eşleşmiyor; uyarlama gerekli.')
            if not media.get('available', False): warnings.append(prefix + 'medya dosyası henüz doğrulanmadı.')
        if block['end'] - block['start'] > 20: warnings.append(prefix + 'görsel uzun sürüyor; cümle sonlarında çeşitlendirin.')
        if block['language'] != plan['language'] or block['overlay_language'] != plan['language']: warnings.append(prefix + 'dil eşleşmiyor.')
        if block.get('image_status') == 'error': warnings.append(prefix + 'görsel üretimi başarısız.')
        image_run = image_run+1 if block['media_type'] in ('stock_image', 'ai_image') else 0
        if image_run == 4: warnings.append('Arka arkaya çok fazla sabit görsel var; ilgili video veya hareket önerilerini inceleyin.')
        if index >= 2 and len({item['composition'] for item in blocks[index-2:index+1]}) == 1: warnings.append(prefix + 'benzer kompozisyon arka arkaya geliyor.')
    if not plan.get('voice'): warnings.append('Seslendirme dosyası eksik; TTS çalıştırması daha sonra.')
    if project['subtitles_enabled'] and not plan.get('subtitles'): warnings.append('Altyazı/timing henüz yok; üretim daha sonra.')
    if project['subtitles_enabled'] and plan.get('subtitles') and plan['subtitles'].get('language') != plan['language']: warnings.append('Altyazı dili hedef dille eşleşmiyor.')
    music = plan['music']
    if music['enabled'] and not music['local_file_label']: warnings.append('Müzik açık ancak lisanslı yerel müzik seçilmedi.')
    if music['enabled']: warnings.append('Müzik dosyası henüz içe aktarılmadı veya doğrulanmadı; dosya işleme daha sonra.')
    if music['enabled'] and not music['license_confirmed']: warnings.append('Müzik kullanım lisansı onaylanmamış.')
    if music['enabled'] and music['volume'] > .3: warnings.append('Müzik seslendirmeyi bastırabilir; ses seviyesini azaltın.')
    return list(dict.fromkeys(warnings))


class ProductionService:
    def __init__(self, scripts):
        self.scripts, self.repo, self.projects = scripts, scripts.repository, scripts.projects

    def view(self, project_id):
        project = self.projects.get(project_id)
        current = self.repo.view(project_id)['current']
        with closing(self.projects._connection()) as connection:
            row = connection.execute('SELECT * FROM project_production WHERE project_id=?', (project_id,)).fetchone()
        import json
        plan = json.loads(row['plan_json']) if row else None
        return {'state': 'Plan hazır — çalıştırma daha sonra' if plan else 'Plan henüz hazırlanmadı', 'plan': plan, 'warnings': production_checks(plan, current, project),
                'media_priority': MEDIA_PRIORITY, 'render_available': False, 'upload_available': False}

    def save_generated(self, project_id, version_id, language, blocks, confirmed=False):
        existing = self.view(project_id)['plan']
        if existing and not confirmed: raise ScriptError('Mevcut görsel plan korunuyor. Yenisiyle değiştirmek için açık onay verin.', 409)
        image_config = self.scripts.settings.image_config()
        plan = {'version_id': version_id, 'language': language, 'width': image_config['width'], 'height': image_config['height'], 'blocks': blocks,
                'media_priority': MEDIA_PRIORITY, 'timing_source': 'estimated', 'voice': None, 'subtitles': None,
                'music': {'enabled': self.projects.get(project_id)['background_music_enabled'], 'mood': 'neutral', 'local_file_label': '', 'license_confirmed': False, 'volume': .15, 'fade_in': 2., 'fade_out': 3., 'ducking': True, 'section_changes': []}}
        self._save(project_id, plan)
        return plan

    def _save(self, project_id, plan):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute('INSERT INTO project_production VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET version_id=excluded.version_id,plan_json=excluded.plan_json,updated_at=excluded.updated_at', (project_id, plan['version_id'], dumps(plan), now()))
        self.repo._file(project_id, 'visual_plan.json', dumps(plan))

    @editable
    def update(self, project_id, payload):
        plan = self.view(project_id)['plan']
        if not plan: raise ScriptError('Önce onaylı senaryodan görsel plan hazırlayın.')
        if set(payload) != {'music'} or not isinstance(payload['music'], dict): raise ScriptError('Müzik tercihlerini kontrol edin.')
        from app.production_settings import MusicSettings
        try: music = MusicSettings.model_validate(payload['music']).model_dump()
        except ValueError: raise ScriptError('Müzik ses seviyesi 0–1, geçiş süreleri 0–30 saniye olmalı. Lisans onayını kontrol edin.') from None
        from app.scripts.engine import SecretGuard
        SecretGuard(self.scripts.settings.secret_values()).validate(music)
        plan['music'] = music
        self._save(project_id, plan)
        return self.view(project_id)

    @editable
    def attach_media(self, project_id, block_id, media):
        from app.production_settings import MediaSelection
        try: media = MediaSelection.model_validate(media).model_dump()
        except ValueError: raise ScriptError('Medya seçimi bilgileri geçersiz.') from None
        from app.scripts.engine import SecretGuard
        SecretGuard(self.scripts.settings.secret_values()).validate(media)
        plan = self.view(project_id)['plan']
        if not plan: raise ScriptError('Görsel plan bulunamadı.', 404)
        if any(block.get('media') and (block['media']['provider'], block['media']['media_id']) == (media['provider'], media['media_id']) and block['id'] != block_id for block in plan['blocks']):
            raise ScriptError('Bu medya başka bir blokta seçilmiş. İlgili farklı bir görsel seçin.', 409)
        block = next((block for block in plan['blocks'] if block['id'] == block_id), None)
        if not block: raise ScriptError('Görsel blok bulunamadı.', 404)
        block['media'] = {**media, 'available': False}  # Metadata is never proof that a file exists.
        self._save(project_id, plan)
        return self.view(project_id)

    @editable
    def attach_timing(self, project_id, payload):
        plan = self.view(project_id)['plan']
        if not plan or not isinstance(payload, dict) or set(payload) != {'timings'} or not isinstance(payload['timings'], list) or len(payload['timings']) != len(plan['blocks']):
            raise ScriptError('Her görsel blok için gerçek anlatım zamanlaması gerekli.')
        try:
            timings = [NarrationTiming.model_validate(item) for item in payload['timings']]
            previous = 0
            for block, timing in zip(plan['blocks'], timings):
                if normalize(block['narration']) != normalize(timing.text) or timing.start < previous: raise ValueError()
                previous = timing.end
        except ValueError: raise ScriptError('Zamanlamalar sıralı ve blok metniyle aynı olmalıdır.') from None
        for block, timing in zip(plan['blocks'], timings): block.update(start=timing.start, end=timing.end, timing_source='tts')
        plan['timing_source'] = 'tts'
        self._save(project_id, plan)
        return self.view(project_id)
