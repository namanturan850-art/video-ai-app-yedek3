"""Additive Part 4 tables; executed inside the existing migration transaction."""
STATEMENTS = (
    '''CREATE TABLE script_versions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        version INTEGER NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, language TEXT NOT NULL,
        mode TEXT NOT NULL, content_type TEXT NOT NULL, text TEXT NOT NULL, options_json TEXT NOT NULL,
        report_json TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('draft','approved')),
        word_count INTEGER NOT NULL, estimated_minutes REAL NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, approved_at TEXT,
        UNIQUE(project_id, version))''',
    '''CREATE TABLE script_state (
        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        current_version_id TEXT, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE script_jobs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        provider TEXT NOT NULL, model TEXT NOT NULL, action TEXT NOT NULL,
        status TEXT NOT NULL, options_json TEXT NOT NULL, input_json TEXT NOT NULL,
        progress_json TEXT NOT NULL, error_message TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    'CREATE INDEX script_jobs_project ON script_jobs(project_id, created_at DESC)',
)
