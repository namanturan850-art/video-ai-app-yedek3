"""Small, idempotent database bootstrap; project features come later."""
import sqlite3
from pathlib import Path


def initialize_database(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    database = data_dir / "app.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT OR IGNORE INTO app_metadata VALUES ('schema_version', '1')")
    return database


def database_healthy(database: Path) -> bool:
    try:
        # Read-only: diagnostics must not create a missing database.
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            return connection.execute("PRAGMA quick_check").fetchone() == ("ok",) and connection.execute(
                "SELECT value FROM app_metadata WHERE key = 'schema_version'"
            ).fetchone() == ("1",)
    except (sqlite3.Error, OSError):
        return False
