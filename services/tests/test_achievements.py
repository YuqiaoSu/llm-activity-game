"""Tests for achievement unlock logic and API endpoint."""
import sqlite3
import pytest
from services.storage.db import init_db
from services.progression.achievements import check_achievements
from services.seeds.achievements import SEED_ACHIEVEMENTS


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Seed achievement definitions
    for ach in SEED_ACHIEVEMENTS:
        conn.execute(
            "INSERT OR IGNORE INTO achievements "
            "(achievement_id, name, description, condition_type, threshold) VALUES (?, ?, ?, ?, ?)",
            ach,
        )
    # Seed minimal player state
    import json
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Tester", visual),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


def _set_xp(db, xp: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'WORK', ?)",
        (xp,),
    )
    db.commit()


def _set_level(db, level: int) -> None:
    db.execute("UPDATE player_profile SET level=? WHERE character_id='player_default'", (level,))
    db.commit()


def _set_streak(db, streak: int) -> None:
    db.execute("UPDATE streak_state SET current_streak=? WHERE player_id='default'", (streak,))
    db.commit()


def _set_items(db, count: int) -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.execute("DELETE FROM inventory WHERE character_id='player_default'")
    for i in range(count):
        db.execute(
            "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
            "VALUES (?, 'player_default', 'item_x', ?, 'c0')",
            (f"inst_{i}", now),
        )
    db.commit()


# ── condition type tests ─────────────────────────────────────────────────────

def test_total_xp_unlocks_first_blood(db):
    _set_xp(db, 1)
    unlocked = check_achievements(db, "player_default")
    db.commit()
    assert "first_blood" in unlocked


def test_total_xp_threshold_not_met(db):
    _set_xp(db, 0)
    unlocked = check_achievements(db, "player_default")
    assert "first_blood" not in unlocked


def test_level_achievement_unlocks(db):
    _set_level(db, 5)
    unlocked = check_achievements(db, "player_default")
    db.commit()
    assert "level_5" in unlocked


def test_level_achievement_not_met(db):
    _set_level(db, 4)
    unlocked = check_achievements(db, "player_default")
    assert "level_5" not in unlocked


def test_streak_achievement_unlocks(db):
    _set_streak(db, 3)
    unlocked = check_achievements(db, "player_default")
    db.commit()
    assert "on_a_roll" in unlocked


def test_streak_achievement_not_met(db):
    _set_streak(db, 2)
    unlocked = check_achievements(db, "player_default")
    assert "on_a_roll" not in unlocked


def test_items_collected_achievement_unlocks(db):
    _set_items(db, 10)
    unlocked = check_achievements(db, "player_default")
    db.commit()
    assert "collector" in unlocked


def test_items_collected_not_met(db):
    _set_items(db, 9)
    unlocked = check_achievements(db, "player_default")
    assert "collector" not in unlocked


# ── idempotency ──────────────────────────────────────────────────────────────

def test_already_unlocked_not_returned_again(db):
    _set_xp(db, 1)
    first = check_achievements(db, "player_default")
    db.commit()
    assert "first_blood" in first

    second = check_achievements(db, "player_default")
    db.commit()
    assert "first_blood" not in second


# ── notification created ─────────────────────────────────────────────────────

def test_notification_created_on_unlock(db):
    _set_xp(db, 1)
    check_achievements(db, "player_default")
    db.commit()
    row = db.execute(
        "SELECT payload FROM pending_notifications "
        "WHERE character_id='player_default' AND event_type='achievement_unlock'"
    ).fetchone()
    assert row is not None
    import json
    payload = json.loads(row["payload"])
    assert payload["achievement_id"] == "first_blood"
    assert payload["name"] == "First Blood"


# ── API endpoint ─────────────────────────────────────────────────────────────

def test_get_achievements_returns_all(db):
    from fastapi.testclient import TestClient
    from services.api.main import create_app
    app = create_app(db=db)
    client = TestClient(app)

    r = client.get("/achievements")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == len(SEED_ACHIEVEMENTS)
    # All locked initially
    assert all(not item["unlocked"] for item in data)


def test_get_achievements_shows_unlocked(db):
    from fastapi.testclient import TestClient
    from services.api.main import create_app

    _set_xp(db, 1)
    check_achievements(db, "player_default")
    db.commit()

    app = create_app(db=db)
    client = TestClient(app)
    r = client.get("/achievements")
    assert r.status_code == 200
    by_id = {item["achievement_id"]: item for item in r.json()}
    assert by_id["first_blood"]["unlocked"] is True
    assert by_id["first_blood"]["unlocked_at"] is not None
    assert by_id["getting_warmed_up"]["unlocked"] is False
