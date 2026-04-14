import sqlite3
from services.storage.db import init_db, get_db


def test_init_db_creates_all_tables():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    expected = {
        "sync_state", "item_definitions", "inventory", "reward_ledger",
        "pending_notifications", "player_profile", "player_category_xp",
        "places", "place_slots", "place_active_effects",
    }
    assert expected == tables
    conn.close()


def test_get_db_returns_connection(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_db(str(db_path))
    assert conn is not None
    conn.close()
