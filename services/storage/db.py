import json
import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "storage" / "schema.sql"

_DEFAULT_VISUAL = json.dumps({
    "base_sprite": "companion_hatchling.png",
    "evolution_stage": 0,
    "skin": None,
    "accessories": [],
    "anim_state": "idle",
})


def init_db(conn: sqlite3.Connection) -> None:
    """Execute schema.sql against the given connection."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()  # executescript already commits; this is a no-op but kept for clarity


def bootstrap_defaults(conn: sqlite3.Connection) -> None:
    """Ensure the minimum rows required to run exist.

    Safe to call multiple times — uses INSERT OR IGNORE throughout.
    Does NOT seed item definitions or places (run `python -m services.seeds` for those).
    """
    conn.execute(
        "INSERT OR IGNORE INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Lumi", _DEFAULT_VISUAL),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()


def get_db(path: str = "game.db") -> sqlite3.Connection:
    """Open (or create) the SQLite database at `path`, initialize schema, return connection."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    bootstrap_defaults(conn)
    return conn
