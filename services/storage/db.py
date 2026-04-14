import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "storage" / "schema.sql"


def init_db(conn: sqlite3.Connection) -> None:
    """Execute schema.sql against the given connection."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()  # executescript already commits; this is a no-op but kept for clarity


def get_db(path: str = "game.db") -> sqlite3.Connection:
    """Open (or create) the SQLite database at `path`, initialize schema, return connection."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn
