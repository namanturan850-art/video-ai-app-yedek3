STATEMENTS = (
    '''CREATE TABLE IF NOT EXISTS stock_plans (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plan_id TEXT NOT NULL REFERENCES scene_plan_versions(id) ON DELETE CASCADE,
        source_version_id TEXT NOT NULL, state_json TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id,plan_id))''',
    '''CREATE TABLE IF NOT EXISTS stock_jobs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plan_id TEXT NOT NULL, action TEXT NOT NULL, slot_id TEXT,
        status TEXT NOT NULL, progress_json TEXT NOT NULL, error_message TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS stock_assets (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        provider TEXT NOT NULL, media_id TEXT NOT NULL, media_type TEXT NOT NULL,
        metadata_json TEXT NOT NULL, PRIMARY KEY(project_id,provider,media_id,media_type))''',
    '''CREATE TABLE IF NOT EXISTS stock_search_cache (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        provider TEXT NOT NULL, media_type TEXT NOT NULL, query TEXT NOT NULL,
        result_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(project_id,provider,media_type,query))''',
    '''CREATE UNIQUE INDEX IF NOT EXISTS stock_one_active_job ON stock_jobs(project_id)
        WHERE status IN ('queued','running')''',
)
