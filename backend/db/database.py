"""
DevProof AI — Database initialization and connection helpers.

ST-1: Creates the SQLite database file and directory on startup.
ST-4: schema.sql now contains the full schema; init_db() applies it with
      IF NOT EXISTS guards so it is safe to call repeatedly on every startup
      without destroying existing data.
"""

import sqlite3
from pathlib import Path

# Resolve the data/ directory relative to this file's location.
_BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = _BASE_DIR / "data"
DB_PATH = DB_DIR / "devproof.db"


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory set to Row."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """
    Ensure the data/ directory and the SQLite database file exist.
    Applies schema.sql if it contains content.
    Full schema migrations are handled in ST-4.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).resolve().parent / "schema.sql"
    if schema_path.exists():
        schema_sql = schema_path.read_text()
        if schema_sql.strip():
            with get_connection() as conn:
                conn.executescript(schema_sql)

    print(f"[devproof-ai] Database ready: {DB_PATH}")
