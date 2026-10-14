"""YouTube channels and their “Tarzım” (style) kit.

Every project belongs to a channel. A channel carries its language, default
AI33 voice, target duration, niche and a style kit (palette, fonts, motion
rules, sound effects, subtitle style). The kit is used by motion templates,
subtitles and thumbnails. Avatars are only reserved (no generation).
"""
from contextlib import closing
import json
import re
import sqlite3
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.languages import validate_language
from app.projects import ProjectError, linked, now

HEX = r'^#[0-9A-Fa-f]{6}$'
# Bundled OFL fonts (app/static/fonts, licences next to them) + Arial, which
# keeps the subtitle look of projects made before channels existed.
FONTS = {'inter': ('Inter', 'Inter.ttf'), 'montserrat': ('Montserrat', 'Montserrat.ttf'),
         'oswald': ('Oswald', 'Oswald.ttf'), 'bebas': ('Bebas Neue', 'BebasNeue-Regular.ttf'),
         'lora': ('Lora', 'Lora.ttf'), 'arial': ('Arial', None)}
FONT_LABELS = {'inter': 'Inter — sade, modern', 'montserrat': 'Montserrat — güçlü, geniş', 'oswald': 'Oswald — dar, başlık',
               'bebas': 'Bebas Neue — büyük harf, etkili başlık', 'lora': 'Lora — klasik, ciddi (serif)', 'arial': 'Arial — sistem fontu'}
EASINGS = {'smooth': 'Yumuşak', 'snappy': 'Çevik', 'bounce': 'Sekmeli', 'linear': 'Düz'}
SFX_NAMES = ('click', 'rise', 'hit')
SFX_LABELS = {'click': 'Tık', 'rise': 'Yükseliş', 'hit': 'Darbe'}
SFX_TYPES = {'.wav': (b'RIFF', 'audio/wav'), '.mp3': (None, 'audio/mpeg'), '.ogg': (b'OggS', 'audio/ogg')}
FEELINGS = ('ciddi', 'gizemli', 'enerjik', 'sakin', 'eğlenceli', 'bilimsel')


class Palette(BaseModel):
    model_config = ConfigDict(extra='forbid')
    background: str = Field(default='#101823', pattern=HEX)
    primary: str = Field(default='#F5F7FA', pattern=HEX)
    accent: str = Field(default='#F2B23E', pattern=HEX)
    text: str = Field(default='#FFFFFF', pattern=HEX)


class SubtitleStyle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    font: Literal['inter', 'montserrat', 'oswald', 'bebas', 'lora', 'arial'] = 'arial'
    color: str = Field(default='#FFFFFF', pattern=HEX)
    outline: str = Field(default='#101010', pattern=HEX)
    position: Literal['bottom', 'middle', 'top'] = 'bottom'
    size: int = Field(default=48, ge=32, le=96)
    word_highlight: bool = False  # the word being read gets a coloured box (accent colour)


class StyleKit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    palette: Palette = Field(default_factory=Palette)
    heading_font: Literal['inter', 'montserrat', 'oswald', 'bebas', 'lora', 'arial'] = 'montserrat'
    body_font: Literal['inter', 'montserrat', 'oswald', 'bebas', 'lora', 'arial'] = 'inter'
    motion_duration: float = Field(default=.6, ge=.2, le=2.0)
    easing: Literal['smooth', 'snappy', 'bounce', 'linear'] = 'smooth'
    sfx: dict[str, str] = Field(default_factory=lambda: {name: 'default:' + name for name in SFX_NAMES})
    sfx_volume: float = Field(default=.18, ge=0, le=.5)
    subtitle: SubtitleStyle = Field(default_factory=SubtitleStyle)
    feeling: str = Field(default='', max_length=40)
    map_style: Literal['relief', 'dark', 'satellite'] = 'dark'
    map_style_chosen: bool = False  # the owner picked it (older kits stored 'relief' without choosing: they get the dark default)  # “Harita stili”: colour relief or the dark flat documentary map

    @field_validator('sfx')
    @classmethod
    def sounds(cls, value):
        if set(value) != set(SFX_NAMES):
            raise ValueError('sfx')
        for name, source in value.items():
            if not re.fullmatch(r'default:(click|rise|hit)|none|upload:[a-f0-9]{32}\.(wav|mp3|ogg)', source):
                raise ValueError('sfx')
        return value


DEFAULT_STYLE = StyleKit().model_dump()


def map_style(style):
    """'dark' (default) or 'relief' — relief only when the owner chose it."""
    style = style or {}
    return style.get('map_style', 'dark') if style.get('map_style_chosen') else 'dark'


class ChannelInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=80)
    language: str = 'de'
    _language = field_validator('language')(validate_language)
    niche: str = Field(default='', max_length=600)
    target_duration_minutes: float = Field(default=5, ge=1, le=180)
    voice_provider: str = Field(default='', max_length=40)
    voice_id: str = Field(default='', max_length=150)
    voice_name: str = Field(default='', max_length=150)
    voice_speed: float = Field(default=1.0, ge=.5, le=1.5)

    @field_validator('name', 'niche', 'voice_id', 'voice_name')
    @classmethod
    def clean(cls, value):
        if any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError('text')
        return value.strip()


PRESETS = {  # deterministic suggestions when no AI engine is configured
    'ciddi': {'palette': {'background': '#0F1720', 'primary': '#E8EDF2', 'accent': '#C9A227', 'text': '#FFFFFF'}, 'heading_font': 'lora', 'body_font': 'inter', 'motion_duration': .7, 'easing': 'smooth'},
    'gizemli': {'palette': {'background': '#0B0F1A', 'primary': '#D7E3F4', 'accent': '#5FD3C6', 'text': '#F2F6FA'}, 'heading_font': 'oswald', 'body_font': 'inter', 'motion_duration': .8, 'easing': 'smooth'},
    'enerjik': {'palette': {'background': '#14121C', 'primary': '#FFFFFF', 'accent': '#FF5A36', 'text': '#FFFFFF'}, 'heading_font': 'bebas', 'body_font': 'montserrat', 'motion_duration': .4, 'easing': 'snappy'},
    'sakin': {'palette': {'background': '#1E2A2F', 'primary': '#EEF3F1', 'accent': '#8FC1A9', 'text': '#FFFFFF'}, 'heading_font': 'lora', 'body_font': 'inter', 'motion_duration': .9, 'easing': 'smooth'},
    'eğlenceli': {'palette': {'background': '#1B1340', 'primary': '#FFFFFF', 'accent': '#FFD23F', 'text': '#FFFFFF'}, 'heading_font': 'montserrat', 'body_font': 'inter', 'motion_duration': .5, 'easing': 'bounce'},
    'bilimsel': {'palette': {'background': '#0E1A2B', 'primary': '#E6F0FF', 'accent': '#3FA9F5', 'text': '#FFFFFF'}, 'heading_font': 'inter', 'body_font': 'inter', 'motion_duration': .6, 'easing': 'snappy'},
    'koyu_harita': {'palette': {'background': '#0B1426', 'primary': '#E8EEF7', 'accent': '#3D9BFF', 'text': '#FFFFFF'}, 'heading_font': 'montserrat', 'body_font': 'inter', 'motion_duration': .6, 'easing': 'smooth',
                    'map_style': 'dark', 'word_highlight': True}
}
# One-click “Video görünümü” (Video screen) — the same presets, no wizard.
LOOKS = {'ciddi': 'Belgesel (ciddi, altın vurgu)', 'gizemli': 'Gizem (koyu, turkuaz vurgu)', 'enerjik': 'Enerjik (hızlı, turuncu vurgu)',
         'sakin': 'Sakin (yumuşak, yeşil vurgu)', 'eğlenceli': 'Eğlenceli (mor, sarı vurgu)', 'bilimsel': 'Bilim (mavi, keskin)',
         'koyu_harita': 'Koyu harita belgeseli (lacivert, parlak mavi, koyu harita)'}
SUGGEST_SCHEMA = {'type': 'object', 'additionalProperties': False,
                  'required': ['background', 'primary', 'accent', 'text', 'heading_font', 'body_font', 'motion_duration', 'easing', 'subtitle_font', 'subtitle_position', 'reason'],
                  'properties': {**{k: {'type': 'string'} for k in ('background', 'primary', 'accent', 'text', 'heading_font', 'body_font', 'easing', 'subtitle_font', 'subtitle_position', 'reason')},
                                 'motion_duration': {'type': 'number'}}}


def contrast(a, b):
    def lum(hexcolor):
        rgb = [int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        rgb = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + .05) / (y + .05)


def validate_style(value):
    try:
        kit = StyleKit.model_validate(value).model_dump()
    except ValidationError:
        raise ProjectError('Tarzım ayarlarını kontrol edin: renkler #RRGGBB biçiminde, animasyon süresi 0,2–2 sn, ses düzeyi 0–0,5 olmalı.') from None
    if contrast(kit['palette']['background'], kit['palette']['text']) < 4.5:
        raise ProjectError('Yazı rengi arka planla yeterince ayrışmıyor; okunabilirlik için daha açık/koyu bir renk seçin.')
    return kit


class ChannelService:
    def __init__(self, projects, settings=None):
        self.projects, self.settings = projects, settings

    def _connection(self):
        return self.projects._connection()

    @staticmethod
    def _public(row, counts=None):
        item = dict(row)
        voice = json.loads(item.pop('voice_json') or '{}')
        item.update(voice_provider=voice.get('voice_provider', ''), voice_id=voice.get('voice_id', ''),
                    voice_name=voice.get('voice_name', ''), voice_speed=voice.get('speed', 1.0))
        item['style'] = {**DEFAULT_STYLE, **json.loads(item.pop('style_json') or '{}')}
        item['avatar'] = json.loads(item.pop('avatar_json') or '{}')
        item['is_default'] = bool(item['is_default'])
        if counts is not None: item['project_count'] = counts.get(item['id'], 0)
        return item

    def options(self):
        return {'fonts': [{'id': k, 'label': FONT_LABELS[k], 'family': v[0], 'file': v[1]} for k, v in FONTS.items()],
                'easings': [{'id': k, 'label': v} for k, v in EASINGS.items()], 'feelings': list(FEELINGS),
                'sfx': [{'id': k, 'label': SFX_LABELS[k], 'default_url': f'/static/sfx/{k}.wav'} for k in SFX_NAMES]}

    def list(self):
        with closing(self._connection()) as c:
            counts = dict(c.execute('SELECT channel_id, COUNT(*) FROM projects GROUP BY channel_id').fetchall())
            return [self._public(r, counts) for r in c.execute('SELECT * FROM channels ORDER BY is_default DESC, created_at')]

    def _row(self, c, channel_id):
        if not isinstance(channel_id, str) or not re.fullmatch(r'[0-9a-f]{32}', channel_id):
            raise ProjectError('Kanal bulunamadı.', 404)
        row = c.execute('SELECT * FROM channels WHERE id=?', (channel_id,)).fetchone()
        if row is None:
            raise ProjectError('Kanal bulunamadı.', 404)
        return row

    def get(self, channel_id):
        with closing(self._connection()) as c:
            return self._public(self._row(c, channel_id))

    def default_id(self):
        with closing(self._connection()) as c:
            return c.execute('SELECT id FROM channels WHERE is_default=1').fetchone()[0]

    def for_project(self, project_id):
        with closing(self._connection()) as c:
            row = c.execute('SELECT c.* FROM channels c JOIN projects p ON p.channel_id=c.id WHERE p.id=?', (project_id,)).fetchone()
            row = row or c.execute('SELECT * FROM channels WHERE is_default=1').fetchone()
            return self._public(row)

    def look(self, project_id):
        style = self.for_project(project_id)['style']
        return {'look': style.get('feeling') if style.get('feeling') in LOOKS else '', 'looks': [{'id': k, 'label': v, 'accent': PRESETS[k]['palette']['accent']} for k, v in LOOKS.items()],
                'map_style': map_style(style), 'word_highlight': bool((style.get('subtitle') or {}).get('word_highlight')),
                'map_styles': [{'id': 'relief', 'label': 'Renkli kabartma'}, {'id': 'dark', 'label': 'Koyu harita belgeseli (düz vektör)'}]}

    def set_look(self, project_id, name, *, map_style=None, word_highlight=None):
        """A look preset and/or the “Harita stili” and word-highlight switches of the project's channel."""
        if name is not None and name not in LOOKS:
            raise ProjectError('Listeden bir görünüm seçin.')
        if map_style is not None and map_style not in ('relief', 'dark', 'satellite'):
            raise ProjectError('Harita stili: kabartma veya koyu harita seçin.')
        channel = self.for_project(project_id)
        style = {}
        if name is not None:
            preset = PRESETS[name]
            style.update({k: v for k, v in preset.items() if k not in ('map_style', 'word_highlight')}, palette=preset['palette'], feeling=name)
            if 'map_style' in preset and not channel['style'].get('map_style_chosen'): style['map_style'] = preset['map_style']  # a map style the owner picked stays
            if preset.get('word_highlight'): word_highlight = True if word_highlight is None else word_highlight
        if map_style is not None: style.update(map_style=map_style, map_style_chosen=True)
        if word_highlight is not None: style['subtitle'] = {**channel['style']['subtitle'], 'word_highlight': bool(word_highlight)}
        if not style: raise ProjectError('Değiştirilecek bir görünüm ayarı seçin.')
        self.update(channel['id'], {'style': style})
        return self.look(project_id)

    def _input(self, payload, partial=None):
        data = {**(partial or {}), **payload}
        try:
            model = ChannelInput.model_validate(data)
        except ValidationError:
            raise ProjectError('Kanal bilgilerini kontrol edin: ad 1–80 karakter, süre 1–180 dakika, konuşma hızı 0,5–1,5.') from None
        values = model.model_dump()
        voice = {'voice_provider': values.pop('voice_provider'), 'voice_id': values.pop('voice_id'),
                 'voice_name': values.pop('voice_name'), 'speed': values.pop('voice_speed')}
        return values, voice

    def create(self, payload):
        if not isinstance(payload, dict) or set(payload) - set(ChannelInput.model_fields) - {'style'}:
            raise ProjectError('Kanal bilgilerini kontrol edin.')
        style = validate_style(payload.get('style', DEFAULT_STYLE))
        values, voice = self._input({k: v for k, v in payload.items() if k != 'style'})
        stamp, channel_id = now(), uuid4().hex
        with self.projects.lock, closing(self._connection()) as c, c:
            c.execute('INSERT INTO channels (id,name,language,voice_json,target_duration_minutes,niche,style_json,avatar_json,is_default,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,0,?,?)',
                      (channel_id, values['name'], values['language'], json.dumps(voice), values['target_duration_minutes'], values['niche'],
                       json.dumps(style), json.dumps(AVATAR_SLOT), stamp, stamp))
        return self.get(channel_id)

    def update(self, channel_id, payload):
        if not isinstance(payload, dict) or not payload or set(payload) - set(ChannelInput.model_fields) - {'style', 'avatar'}:
            raise ProjectError('Kanal bilgilerini kontrol edin.')
        current = self.get(channel_id)
        base = {k: current[k] for k in ('name', 'language', 'niche', 'target_duration_minutes', 'voice_provider', 'voice_id', 'voice_name', 'voice_speed')}
        values, voice = self._input({k: v for k, v in payload.items() if k not in ('style', 'avatar')}, base)
        style = validate_style({**current['style'], **payload['style']}) if 'style' in payload else current['style']
        avatar = current['avatar']
        if 'avatar' in payload:  # reserved only: notes and position, no generation
            if not isinstance(payload['avatar'], dict) or set(payload['avatar']) - {'note', 'position'}:
                raise ProjectError('Avatar alanı şimdilik yalnızca not ve konum içerir.')
            avatar = {**avatar, **{k: str(v)[:300] for k, v in payload['avatar'].items()}}
        with self.projects.lock, closing(self._connection()) as c, c:
            self._row(c, channel_id)
            c.execute('UPDATE channels SET name=?,language=?,voice_json=?,target_duration_minutes=?,niche=?,style_json=?,avatar_json=?,updated_at=? WHERE id=?',
                      (values['name'], values['language'], json.dumps(voice), values['target_duration_minutes'], values['niche'],
                       json.dumps(style), json.dumps(avatar), now(), channel_id))
        return self.get(channel_id)

    def delete(self, channel_id):
        with self.projects.lock, closing(self._connection()) as c, c:
            row = self._row(c, channel_id)
            if row['is_default']:
                raise ProjectError('Varsayılan kanal silinemez.', 409)
            if c.execute('SELECT 1 FROM projects WHERE channel_id=?', (channel_id,)).fetchone():
                raise ProjectError('Bu kanala bağlı projeler var. Önce projeleri başka kanala taşıyın.', 409)
            c.execute('DELETE FROM channels WHERE id=?', (channel_id,))
        return {'message': 'Kanal silindi.'}

    # ---- sound effects ---------------------------------------------------
    def _sfx_dir(self, channel_id):
        root = self.projects.root.parent / 'channels'
        folder = root / channel_id / 'sfx'
        for path in (root, root / channel_id, folder):
            if linked(path): raise ProjectError('Kanal klasörü dış konuma bağlı; işlem durduruldu.', 409)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def upload_sfx(self, channel_id, name, filename, data):
        self.get(channel_id)
        if name not in SFX_NAMES:
            raise ProjectError('Geçerli bir ses efekti türü seçin (Tık, Yükseliş, Darbe).')
        suffix = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if suffix not in SFX_TYPES:
            raise ProjectError('Ses efekti WAV, MP3 veya OGG olmalı.')
        if not data or len(data) > 5_000_000:
            raise ProjectError('Ses efekti dosyası boş veya 5 MB’dan büyük.')
        magic = SFX_TYPES[suffix][0]
        ok = data.startswith(magic) if magic else (data.startswith(b'ID3') or data[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'))
        if not ok:
            raise ProjectError('Dosya içeriği seçilen ses biçimiyle eşleşmiyor.')
        stored = uuid4().hex + suffix
        (self._sfx_dir(channel_id) / stored).write_bytes(data)
        channel = self.get(channel_id)
        return self.update(channel_id, {'style': {'sfx': {**channel['style']['sfx'], name: 'upload:' + stored}}})

    def sfx_path(self, channel_id, source):
        """Local file for a kit sound source, or None for 'none'."""
        from pathlib import Path
        if source == 'none': return None
        if source.startswith('default:'):
            return Path(__file__).resolve().parent / 'static' / 'sfx' / (source.split(':', 1)[1] + '.wav')
        if source.startswith('upload:'):
            path = self._sfx_dir(channel_id) / source.split(':', 1)[1]
            return path if path.is_file() and not linked(path) else None
        return None

    # ---- “Tarzımı oluştur” -----------------------------------------------
    def suggest(self, channel_id, answers):
        channel = self.get(channel_id)
        if not isinstance(answers, dict) or set(answers) - {'topic', 'audience', 'feeling', 'notes'}:
            raise ProjectError('Sihirbaz cevaplarını kontrol edin.')
        answers = {k: ' '.join(str(answers.get(k, '')).split())[:400] for k in ('topic', 'audience', 'feeling', 'notes')}
        feeling = answers['feeling'].casefold()
        preset = next((PRESETS[k] for k in PRESETS if k in feeling), PRESETS['ciddi'])
        base = {**DEFAULT_STYLE, **preset, 'palette': preset['palette'], 'feeling': answers['feeling'][:40]}
        engine = self.settings.ai_engine() if self.settings else None
        if not engine:
            kit = validate_style(base)
            return {'style': kit, 'source': 'preset', 'reason': 'Seçtiğiniz hisse uygun hazır öneri (yapay zekâ ayarlı değil).'}
        try:
            from app.providers.factory import make_script_provider
            ai = make_script_provider(engine, self.settings)
            prompt = ('Design a consistent visual style kit for a YouTube channel.\n'
                      f'Channel: {channel["name"]}. Niche: {channel["niche"] or answers["topic"]}. Topic: {answers["topic"]}. '
                      f'Audience: {answers["audience"]}. Feeling: {answers["feeling"]}. Notes: {answers["notes"]}.\n'
                      'Return colours as #RRGGBB (dark background with readable light text, one strong accent). '
                      f'heading_font and body_font and subtitle_font must each be one of {list(FONTS)}. easing one of {list(EASINGS)}. '
                      'motion_duration in seconds between 0.3 and 1.2. subtitle_position one of bottom/middle/top. '
                      'reason: one short Turkish sentence for the owner.')
            data = ai.complete_json('style_kit', prompt, SUGGEST_SCHEMA, effort='low', max_tokens=800)
            proposal = {**base, 'palette': {k: data[k] for k in ('background', 'primary', 'accent', 'text')},
                        'heading_font': data['heading_font'], 'body_font': data['body_font'],
                        'motion_duration': round(float(data['motion_duration']), 2), 'easing': data['easing'],
                        'subtitle': {**base['subtitle'], 'font': data['subtitle_font'], 'position': data['subtitle_position']}}
            kit = validate_style(proposal)
            return {'style': kit, 'source': engine, 'reason': ' '.join(str(data.get('reason', '')).split())[:300]}
        except Exception:
            # An unusable AI answer never blocks the wizard: fall back to the preset.
            kit = validate_style(base)
            return {'style': kit, 'source': 'preset', 'reason': 'Yapay zekâ önerisi kullanılamadı; seçtiğiniz hisse uygun hazır öneri gösteriliyor.'}


AVATAR_SLOT = {'enabled': False, 'note': '', 'position': 'bottom_right', 'status': 'Yer ayrıldı — avatar üretimi henüz yok.'}


def migrate(connection):
    """Schema 12: channels table, projects.channel_id, a default channel that
    owns every existing project. Additive; no project data changes."""
    connection.execute('''CREATE TABLE IF NOT EXISTS channels (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL, voice_json TEXT NOT NULL DEFAULT '{}',
        target_duration_minutes REAL NOT NULL, niche TEXT NOT NULL DEFAULT '', style_json TEXT NOT NULL,
        avatar_json TEXT NOT NULL DEFAULT '{}', is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    columns = [r[1] for r in connection.execute('PRAGMA table_info(projects)')]
    if 'channel_id' not in columns:
        connection.execute("ALTER TABLE projects ADD COLUMN channel_id TEXT NOT NULL DEFAULT ''")
    row = connection.execute('SELECT id FROM channels WHERE is_default=1').fetchone()
    if row is None:
        stamp, channel_id = now(), uuid4().hex
        connection.execute("INSERT INTO channels VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                           (channel_id, 'Varsayılan kanal', 'de', '{}', 5, '', json.dumps(DEFAULT_STYLE), json.dumps(AVATAR_SLOT), stamp, stamp))
    else:
        channel_id = row[0]
    connection.execute("UPDATE projects SET channel_id=? WHERE channel_id=''", (channel_id,))
