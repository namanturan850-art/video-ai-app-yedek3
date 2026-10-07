"""Transactional, additive schema upgrades that preserve existing local data."""
from contextlib import closing
import sqlite3
from pathlib import Path

SCHEMA_VERSION = "2"
PROJECT_SCHEMA = """
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    topic TEXT NOT NULL,
    reference_url TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'de',
    target_duration_minutes REAL NOT NULL CHECK (target_duration_minutes >= 1),
    content_style TEXT NOT NULL,
    min_scene_duration_seconds REAL NOT NULL CHECK (min_scene_duration_seconds >= 1),
    max_scene_duration_seconds REAL NOT NULL CHECK (max_scene_duration_seconds >= min_scene_duration_seconds),
    subtitles_enabled INTEGER NOT NULL CHECK (subtitles_enabled IN (0, 1)),
    background_music_enabled INTEGER NOT NULL CHECK (background_music_enabled IN (0, 1)),
    thumbnail_planning_enabled INTEGER NOT NULL CHECK (thumbnail_planning_enabled IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ready', 'processing', 'completed', 'error')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def initialize_database(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    database = data_dir / "app.db"
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT OR IGNORE INTO app_metadata VALUES ('schema_version', '1')")
            version = connection.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone()[0]
            if version == "1":
                connection.execute(PROJECT_SCHEMA)
                connection.execute("CREATE INDEX projects_created_at ON projects(created_at DESC)")
                connection.execute("UPDATE app_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION,))
            elif version != SCHEMA_VERSION:
                raise sqlite3.DatabaseError("Bu veritabanı sürümü desteklenmiyor; mevcut dosyalar değiştirilmedi.")
    return database


def database_healthy(database: Path) -> bool:
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            return (connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
                    and connection.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone() == (SCHEMA_VERSION,)
                    and connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'projects'").fetchone() == (1,))
    except (sqlite3.Error, OSError):
        return False
