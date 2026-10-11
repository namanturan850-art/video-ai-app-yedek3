"""Transactional, additive schema upgrades that preserve existing local data."""
from contextlib import closing
import sqlite3
from pathlib import Path

SCHEMA_VERSION = "11"
PROJECT_SCHEMA = """
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    topic TEXT NOT NULL,
    reference_url TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'de',
    script_engine TEXT NOT NULL DEFAULT 'ollama' CHECK (script_engine IN ('ollama', 'openai', 'gemini')),
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
                version = '3'
            elif version == "2":
                connection.execute("ALTER TABLE projects ADD COLUMN script_engine TEXT NOT NULL DEFAULT 'ollama' CHECK (script_engine IN ('ollama', 'openai', 'gemini'))")
                version = '3'
            if version == '3':
                from app.scripts.schema import STATEMENTS
                for statement in STATEMENTS:
                    connection.execute(statement)
                version = '4'
            if version == '4':
                connection.execute('''CREATE TABLE script_artifacts (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    version_id TEXT NOT NULL REFERENCES script_versions(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, language TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL)''')
                connection.execute('''CREATE TABLE project_production (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                    version_id TEXT NOT NULL, plan_json TEXT NOT NULL, updated_at TEXT NOT NULL)''')
                version = '5'
            if version == '5':
                connection.execute('''CREATE TABLE IF NOT EXISTS scene_plan_versions (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    version_id TEXT NOT NULL REFERENCES script_versions(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
                    plan_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    origin_job_id TEXT UNIQUE, UNIQUE(project_id,version))''')
                # Keep old active plans and import them as the first history entry.
                import json
                from uuid import uuid4
                for row in connection.execute('SELECT project_id,version_id,plan_json,updated_at FROM project_production').fetchall():
                    plan = json.loads(row[2])
                    plan_id = uuid4().hex
                    plan.update(plan_id=plan_id, plan_version=1, revision=1, provider='legacy', model='', created_at=row[3])
                    connection.execute('INSERT OR IGNORE INTO scene_plan_versions VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (plan_id,row[0],row[1],1,'legacy','',json.dumps(plan,ensure_ascii=False),row[3],row[3],None))
                    connection.execute('UPDATE project_production SET plan_json=? WHERE project_id=?',(json.dumps(plan,ensure_ascii=False),row[0]))
                version = '6'
            if version == '6':
                from app.stock.schema import STATEMENTS
                for statement in STATEMENTS:
                    connection.execute(statement)
                version = '7'
            if version == '7':
                from app.narration.schema import STATEMENTS
                for statement in STATEMENTS:
                    connection.execute(statement)
                version = '8'
            if version == '8':
                from app.subtitles.schema import STATEMENTS
                for statement in STATEMENTS:
                    connection.execute(statement)
                version = '9'
            if version == '9':
                from app.rendering.schema import STATEMENTS
                for statement in STATEMENTS:
                    connection.execute(statement)
                version = '10'
            if version == '10':
                # Additive only: a new cost ledger. Existing tables are untouched.
                from app.ai_usage import STATEMENTS
                for statement in STATEMENTS:
                    connection.execute(statement)
                version = '11'
            if version != SCHEMA_VERSION:
                raise sqlite3.DatabaseError("Bu veritabanı sürümü desteklenmiyor; mevcut dosyalar değiştirilmedi.")
            connection.execute("UPDATE app_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION,))
    return database


def database_healthy(database: Path) -> bool:
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            return (connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
                    and connection.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone() == (SCHEMA_VERSION,)
                    and connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'projects'").fetchone() == (1,))
    except (sqlite3.Error, OSError):
        return False
