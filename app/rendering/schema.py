STATEMENTS=(
    '''CREATE TABLE IF NOT EXISTS render_versions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        version INTEGER NOT NULL, source_script_version_id TEXT NOT NULL REFERENCES script_versions(id),
        narration_version_id TEXT NOT NULL REFERENCES narration_versions(id),
        subtitle_version_id TEXT NOT NULL REFERENCES subtitle_versions(id), scene_plan_id TEXT NOT NULL,
        source_fingerprint TEXT NOT NULL, metadata_json TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(project_id,version))''',
    '''CREATE TABLE IF NOT EXISTS render_jobs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        render_version_id TEXT NOT NULL REFERENCES render_versions(id) ON DELETE CASCADE,
        status TEXT NOT NULL, progress_json TEXT NOT NULL, error_category TEXT NOT NULL DEFAULT '',
        error_message TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS render_state (
        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        active_version_id TEXT REFERENCES render_versions(id), updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS render_music (
        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        metadata_json TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE UNIQUE INDEX IF NOT EXISTS render_one_active_job ON render_jobs(project_id)
        WHERE status IN ('queued','preparing','rendering','validating')''',
)
