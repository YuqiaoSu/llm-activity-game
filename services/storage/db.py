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


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent column additions for DB schema evolution.

    SQLite does not support IF NOT EXISTS on ALTER TABLE, so we catch
    the OperationalError that fires when a column already exists.
    """
    _safe_add_column(conn, "places", "xp",    "INTEGER NOT NULL DEFAULT 0")
    _safe_add_column(conn, "places", "level",  "INTEGER NOT NULL DEFAULT 1")
    # Decay columns added to streak_state
    from services.progression.decay import migrate as _decay_migrate
    _decay_migrate(conn)
    # Goal-streak columns added to streak_state
    _safe_add_column(conn, "streak_state", "goal_streak",            "INTEGER NOT NULL DEFAULT 0")
    _safe_add_column(conn, "streak_state", "last_goal_streak_date",  "TEXT")
    # Item expiry: NULL = permanent, ISO datetime = expires then
    _safe_add_column(conn, "inventory", "expires_at", "TEXT")


def _safe_add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()
    except Exception:
        pass  # column already exists — nothing to do


def init_db(conn: sqlite3.Connection) -> None:
    """Execute schema.sql against the given connection, then run migrations."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()  # executescript already commits; this is a no-op but kept for clarity
    _run_migrations(conn)


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
