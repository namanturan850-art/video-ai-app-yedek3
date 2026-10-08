"""Additive Part 7 tables; never rewrite previous projects, settings or media."""
STATEMENTS=(
    '''CREATE TABLE IF NOT EXISTS narration_versions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        version INTEGER NOT NULL, kind TEXT NOT NULL,
        source_script_version_id TEXT NOT NULL REFERENCES script_versions(id),
        metadata_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id,kind,version))''',
    '''CREATE TABLE IF NOT EXISTS narration_jobs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        narration_version_id TEXT NOT NULL REFERENCES narration_versions(id) ON DELETE CASCADE,
        status TEXT NOT NULL, progress_json TEXT NOT NULL, error_message TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS narration_state (
        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        active_version_id TEXT REFERENCES narration_versions(id), updated_at TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS narration_jobs_project ON narration_jobs(project_id,created_at DESC)',
)
