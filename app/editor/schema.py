STATEMENTS = (
    '''CREATE TABLE IF NOT EXISTS editor_revisions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plan_id TEXT NOT NULL, parent_plan_id TEXT, kind TEXT NOT NULL,
        payload_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE INDEX IF NOT EXISTS editor_revisions_project ON editor_revisions(project_id,created_at DESC)''',
    '''CREATE TABLE IF NOT EXISTS media_clip_ranges (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        provider TEXT NOT NULL, media_id TEXT NOT NULL, sha256 TEXT NOT NULL,
        start_seconds REAL NOT NULL, end_seconds REAL NOT NULL, rights_json TEXT NOT NULL,
        revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id,provider,media_id))''',
    '''CREATE TABLE IF NOT EXISTS archive_analysis_cache (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        sha256 TEXT NOT NULL, analyzer_version TEXT NOT NULL, result_json TEXT NOT NULL,
        created_at TEXT NOT NULL, PRIMARY KEY(project_id,sha256,analyzer_version))''',
)
