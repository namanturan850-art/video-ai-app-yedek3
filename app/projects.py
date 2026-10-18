"""Part 3 project records and local folders. No production pipeline runs here."""
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
from threading import RLock
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from app.providers.factory import SCRIPT_ENGINE_LABELS
from app.languages import LANGUAGES, validate_language

FOLDERS = ('script', 'scenes', 'stock', 'voice', 'subtitles', 'music', 'render', 'logs')
STAGES = ('Konsept', 'Senaryo', 'Sahne Planı', 'Stok Medya', 'Seslendirme', 'Altyazı', 'Render', 'Metadata', 'Export')
STATUS_LABELS = {'draft': 'Taslak', 'ready': 'Hazır', 'processing': 'İşleniyor', 'completed': 'Tamamlandı', 'error': 'Hata'}
LANGUAGE_LABELS = LANGUAGES


class ProjectError(Exception):
    def __init__(self, message: str, status_code: int = 422, fields: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.fields = fields or {}


class NewProject(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(max_length=120)
    topic: str = Field(max_length=5000)
    reference_url: str = Field(default='', max_length=2000)
    language: str = 'de'
    _language = field_validator('language')(validate_language)
    script_engine: Literal['ollama', 'openai', 'gemini'] = 'gemini'  # free tier by default; Ollama stays the local backup
    target_duration_minutes: float = Field(default=5, ge=1, le=180)
    content_style: str = Field(default='Otomatik', max_length=120)
    min_scene_duration_seconds: float = Field(default=4, ge=1, le=120)
    max_scene_duration_seconds: float = Field(default=8, ge=1, le=120)
    subtitles_enabled: bool = True
    background_music_enabled: bool = False
    thumbnail_planning_enabled: bool = True
    channel_id: str = Field(default='', max_length=32)

    @field_validator('channel_id')
    @classmethod
    def channel_format(cls, value):
        if value and not re.fullmatch(r'[0-9a-f]{32}', value):
            raise ValueError('Geçerli bir kanal seçin.')
        return value

    @field_validator('name', 'topic', 'content_style')
    @classmethod
    def required_text(cls, value, info):
        value = value.strip()
        labels = {'name': 'Proje adı', 'topic': 'Konu', 'content_style': 'İçerik türü / stil'}
        if not value:
            raise ValueError(labels[info.field_name] + ' gerekli.')
        if any(ord(char) < 32 and char not in ('\n', '\t') for char in value):
            raise ValueError(labels[info.field_name] + ' alanında geçersiz karakter var.')
        return value

    @field_validator('reference_url')
    @classmethod
    def youtube_url(cls, value):
        value = value.strip()
        if not value:
            return ''
        try:
            parsed = urlsplit(value)
            if (parsed.scheme not in ('http', 'https') or parsed.username or parsed.password
                    or parsed.port not in (None, 80, 443)
                    or any(char.isspace() or ord(char) < 32 for char in value)
                    or '\\' in value):
                raise ValueError()
            host = parsed.hostname
            video_id = ''
            if host in ('youtu.be', 'www.youtu.be'):
                video_id = parsed.path.strip('/')
            elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
                if parsed.path == '/watch':
                    video_id = parse_qs(parsed.query).get('v', [''])[0]
                elif parsed.path.split('/')[1:2] in (['shorts'], ['live'], ['embed']):
                    video_id = parsed.path.strip('/').split('/')[-1]
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                raise ValueError()
        except ValueError:
            raise ValueError("Geçerli bir YouTube video URL'si girin; isterseniz alanı boş bırakın.") from None
        return value

    @model_validator(mode='after')
    def scene_range(self):
        if self.min_scene_duration_seconds > self.max_scene_duration_seconds:
            raise ValueError('Minimum sahne süresi maksimum süreden büyük olamaz.')
        if self.max_scene_duration_seconds > self.target_duration_minutes * 60:
            raise ValueError('Maksimum sahne süresi toplam video süresini aşamaz.')
        return self


def validate_project(payload: dict) -> NewProject:
    try:
        return NewProject.model_validate(payload)
    except ValidationError as error:
        messages = {}
        labels = {'name': 'Proje adı', 'topic': 'Konu', 'reference_url': 'Referans URL',
                  'language': 'Dil', 'script_engine': 'Senaryo motoru', 'target_duration_minutes': 'Video süresi', 'content_style': 'İçerik türü / stil',
                  'min_scene_duration_seconds': 'Minimum sahne süresi', 'max_scene_duration_seconds': 'Maksimum sahne süresi',
                  'subtitles_enabled': 'Altyazı seçimi', 'background_music_enabled': 'Müzik seçimi',
                  'thumbnail_planning_enabled': 'Thumbnail planlama seçimi'}
        for item in error.errors(include_input=False):
            field = item['loc'][0] if item['loc'] else 'scene_range'
            kind = item['type']
            if kind == 'value_error':
                message = str(item['ctx']['error'])  # Validators use fixed messages, never submitted values.
            elif kind == 'missing':
                message = labels.get(field, 'Alan') + ' gerekli.'
            elif field == 'target_duration_minutes' and kind == 'greater_than_equal':
                message = 'Video süresi 1 dakikadan kısa olamaz.'
            elif kind == 'less_than_equal':
                message = labels.get(field, 'Değer') + ' izin verilen sınırı aşıyor (video: 180 dakika, sahne: 120 saniye).'
            elif kind == 'greater_than_equal':
                message = labels.get(field, 'Süre') + ' 1 saniyeden kısa olamaz.'
            elif kind == 'string_too_long':
                message = labels.get(field, 'Metin') + ' çok uzun. Metni kısaltın.'
            elif kind == 'extra_forbidden':
                field = 'form'
                message = 'Yalnızca proje bilgileri kaydedilebilir; API anahtarı veya işlem durumu gönderilemez.'
            else:
                message = labels.get(field, 'Alan') + ' için geçerli bir değer girin.'
            messages[field] = message
        raise ProjectError(next(iter(messages.values())), fields=messages) from None


def linked(path: Path) -> bool:
    """Also reject Windows junctions/reparse points; never traverse them for deletion."""
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), 'st_file_attributes', 0)
        return bool(attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
    except FileNotFoundError:
        return False


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def public_project(row: sqlite3.Row, detail: bool = False) -> dict:
    project = dict(row)
    for field in ('subtitles_enabled', 'background_music_enabled', 'thumbnail_planning_enabled'):
        project[field] = bool(project[field])
    project['status_label'] = STATUS_LABELS[project['status']]
    project['language_label'] = LANGUAGE_LABELS[project['language']]
    project['script_engine_label'] = SCRIPT_ENGINE_LABELS[project['script_engine']]
    if detail:
        project['pipeline'] = [{'name': stage, 'status': 'Bekliyor', 'message': 'Henüz yapılmadı.'} for stage in STAGES]
    return project


class ProjectService:
    def __init__(self, storage: Path):
        self.storage = storage.resolve()
        self.database = self.storage / 'app.db'
        self.root = self.storage / 'projects'
        self.lock = RLock()

    def _connection(self):
        connection = sqlite3.connect(self.database.resolve().as_uri() + '?mode=rw', uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        return connection

    def _path(self, project_id: str) -> Path:
        if not re.fullmatch(r'[0-9a-f]{32}', project_id):
            raise ProjectError('Proje bulunamadı. Projeler sayfasına dönün.', 404)
        if linked(self.root) or (self.root.exists() and not self.root.is_dir()):
            raise ProjectError('Proje klasörü güvenli biçimde kullanılamıyor. Yerel klasör bağlantısını kaldırmak için destek isteyin; dosyalar silinmedi.', 409)
        path = self.root / project_id
        if linked(path) or path.resolve() != self.root / project_id:
            raise ProjectError('Bu proje klasörü başka bir konuma bağlı. Güvenlik için işlem yapılmadı; destek isteyin.', 409)
        return path

    def _check_tree(self, path: Path):
        if not path.is_dir():
            raise ProjectError('Proje klasörü beklenen biçimde değil. Dosyalar silinmedi; destek isteyin.', 409)
        def walk_error(error):
            raise error
        for base, directories, files in os.walk(path, followlinks=False, onerror=walk_error):
            for name in directories + files:
                if linked(Path(base) / name):
                    raise ProjectError('Proje klasöründe dış konuma bağlantı var. Diğer dosyaları korumak için silme durduruldu.', 409)

    def _row(self, connection, project_id):
        if not re.fullmatch(r'[0-9a-f]{32}', project_id):
            raise ProjectError('Proje bulunamadı. Projeler sayfasına dönün.', 404)
        row = connection.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
        if row is None:
            raise ProjectError('Proje bulunamadı. Silinmiş olabilir; Projeler sayfasına dönün.', 404)
        return row

    def create(self, payload: dict) -> dict:
        model = validate_project(payload)
        project_id = uuid4().hex
        stamp = now()
        values = {'id': project_id, **model.model_dump(), 'status': 'draft', 'created_at': stamp, 'updated_at': stamp}
        owned = False
        path = None
        with self.lock:
            try:
                with closing(self._connection()) as connection, connection:
                    connection.execute('BEGIN IMMEDIATE')
                    path = self._path(project_id)
                    self.root.mkdir(exist_ok=True)
                    path.mkdir()  # Exclusive: an existing directory is never overwritten or cleaned up.
                    owned = True
                    for folder in FOLDERS:
                        (path / folder).mkdir()
                    channel = connection.execute('SELECT id FROM channels WHERE id=?', (values['channel_id'],)).fetchone() if values['channel_id'] else None
                    if values['channel_id'] and channel is None:
                        raise ProjectError('Seçilen kanal bulunamadı. Kanallar sayfasını kontrol edin.', 404)
                    if not values['channel_id']:
                        values['channel_id'] = connection.execute('SELECT id FROM channels WHERE is_default=1').fetchone()[0]
                    columns = ', '.join(values)
                    connection.execute(f"INSERT INTO projects ({columns}) VALUES ({', '.join('?' for _ in values)})", tuple(values.values()))
                    from app.editor.editorial import initialize_project
                    initialize_project(connection,project_id)
                    project = self._detail(connection, project_id)
                return project
            except (OSError, sqlite3.Error, ProjectError) as error:
                if owned and path is not None:
                    try:
                        self._path(project_id)
                        self._check_tree(path)
                        shutil.rmtree(path)
                    except (OSError, ProjectError):
                        pass  # Do not damage any linked or pre-existing path during rollback.
                if isinstance(error, ProjectError):
                    raise
                raise ProjectError('Proje oluşturulamadı. Veri klasörünün yazılabilir olduğunu kontrol edip yeniden deneyin.', 503) from None

    def list(self) -> list:
        try:
            with closing(self._connection()) as connection:
                return [public_project(row) for row in connection.execute('SELECT * FROM projects ORDER BY created_at DESC, id DESC')]
        except sqlite3.Error:
            raise ProjectError('Projeler okunamadı. Uygulamayı kapatıp yeniden açın.', 503) from None

    def _detail(self, connection, project_id):
        # Same shape from create/get/update: the record plus its channel name.
        project = public_project(self._row(connection, project_id), detail=True)
        channel = connection.execute('SELECT name FROM channels WHERE id=?', (project.get('channel_id', ''),)).fetchone() if project.get('channel_id') else None
        project['channel_name'] = channel[0] if channel else 'Varsayılan kanal'
        return project

    def get(self, project_id: str) -> dict:
        try:
            with closing(self._connection()) as connection:
                return self._detail(connection, project_id)
        except sqlite3.Error:
            raise ProjectError('Proje okunamadı. Uygulamayı kapatıp yeniden açın.', 503) from None

    def update(self, project_id: str, payload: dict) -> dict:
        if not payload or any(key not in NewProject.model_fields for key in payload):
            raise ProjectError('Yalnızca proje bilgilerini güncelleyebilirsiniz; işlem durumu ve anahtarlar değiştirilemez.')
        try:
            with self.lock, closing(self._connection()) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                row = self._row(connection, project_id)
                merged = {key: row[key] for key in NewProject.model_fields}
                for key in ('subtitles_enabled', 'background_music_enabled', 'thumbnail_planning_enabled'):
                    merged[key] = bool(merged[key])
                model = validate_project({**merged, **payload})
                values = {**model.model_dump(), 'updated_at': now()}
                if not values['channel_id'] or not connection.execute('SELECT 1 FROM channels WHERE id=?', (values['channel_id'],)).fetchone():
                    raise ProjectError('Seçilen kanal bulunamadı. Kanallar sayfasını kontrol edin.', 404)
                assignments = ', '.join(f'{key} = ?' for key in values)
                connection.execute(f'UPDATE projects SET {assignments} WHERE id = ?', (*values.values(), project_id))
                return self._detail(connection, project_id)
        except sqlite3.Error:
            raise ProjectError('Proje bilgileri kaydedilemedi. Uygulamayı yeniden açıp tekrar deneyin.', 503) from None

    def delete(self, project_id: str, confirmation: dict | None) -> None:
        if confirmation != {'confirm': True} or type(confirmation.get('confirm')) is not bool:
            raise ProjectError('Projeyi ve yerel dosyalarını silmek için açık onay gerekli.')
        try:
            with self.lock, closing(self._connection()) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                self._row(connection, project_id)
                if connection.execute("SELECT 1 FROM script_jobs WHERE project_id=? AND status IN ('queued','analyzing','planning','generating','checking')", (project_id,)).fetchone():
                    raise ProjectError('Senaryo üretimi sürerken proje silinemez. İşlemin bitmesini bekleyin.', 409)
                if connection.execute("SELECT 1 FROM stock_jobs WHERE project_id=? AND status IN ('queued','running')",(project_id,)).fetchone():
                    raise ProjectError('Medya indirme sürerken proje silinemez. İşlemin bitmesini bekleyin.',409)
                if connection.execute("SELECT 1 FROM narration_jobs WHERE project_id=? AND status IN ('queued','running')",(project_id,)).fetchone():
                    raise ProjectError('Seslendirme işlemi sürerken proje silinemez. İşlemin bitmesini bekleyin.',409)
                if connection.execute("SELECT 1 FROM render_jobs WHERE project_id=? AND status IN ('queued','preparing','rendering','validating')",(project_id,)).fetchone():
                    raise ProjectError('Video render sürerken proje silinemez. İşlemi iptal edin veya bitmesini bekleyin.',409)
                path = self._path(project_id)
                if path.exists():
                    self._check_tree(path)
                # Any SQL error occurs before files are removed; a file error rolls back this record.
                connection.execute('DELETE FROM projects WHERE id = ?', (project_id,))
                if path.exists():
                    shutil.rmtree(path)
        except (OSError, sqlite3.Error):
            raise ProjectError('Proje tamamen silinemedi; kayıt korundu. Açık dosyaları kapatıp tekrar deneyin. Diğer projelere dokunulmadı.', 503) from None
