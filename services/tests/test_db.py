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
        "places", "place_slots", "place_active_effects", "chunk_log",
        "streak_state", "achievements", "player_achievements",
        "weekly_challenges", "player_weekly_progress", "weekly_reroll_state",
        "collection_log", "daily_goals", "challenge_events", "place_perks",
        "trade_offers", "pinned_achievements", "wishlist",
        "skills", "player_skills", "player_settings",
        "notification_prefs", "place_invest_log", "place_activity_log",
        "slot_assignment_log",
    }
    assert expected == tables
    conn.close()


def test_get_db_returns_connection(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_db(str(db_path))
    assert conn is not None
    conn.close()


def test_get_db_enables_wal_mode(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_db(str(db_path))
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"
    conn.close()


def test_get_db_enables_foreign_keys(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_db(str(db_path))
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1
    conn.close()


def test_get_db_creates_tables_in_file_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_db(str(db_path))
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    assert "player_profile" in tables
    assert "reward_ledger" in tables
    assert "places" in tables
    conn.close()
