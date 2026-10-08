"""Additive Part 8 migration; existing project/version/media tables untouched."""
STATEMENTS = (
    '''CREATE TABLE IF NOT EXISTS subtitle_versions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        version INTEGER NOT NULL, source_script_version_id TEXT NOT NULL REFERENCES script_versions(id),
        source_narration_version_id TEXT NOT NULL REFERENCES narration_versions(id),
        metadata_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(project_id,version))''',
    '''CREATE TABLE IF NOT EXISTS subtitle_cues (
        version_id TEXT NOT NULL REFERENCES subtitle_versions(id) ON DELETE CASCADE,
        cue_index INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL, text TEXT NOT NULL,
        PRIMARY KEY(version_id,cue_index), CHECK(start>=0 AND end>start))''',
    '''CREATE TABLE IF NOT EXISTS subtitle_state (
        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        active_version_id TEXT REFERENCES subtitle_versions(id), updated_at TEXT NOT NULL)''',
)
