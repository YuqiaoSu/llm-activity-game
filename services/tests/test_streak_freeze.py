"""Tests for streak freeze (insurance) system."""
import sqlite3
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from services.storage.db import init_db
from services.progression.streak import update_streak, consume_streak_freeze, get_streak


_PLAYER = "player_default"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', '{}')",
        (_PLAYER,),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute(
        "INSERT OR IGNORE INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 500)",
        (_PLAYER,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── consume_streak_freeze unit tests ──────────────────────────────────────────

def test_consume_freeze_returns_false_when_none(db):
    result = consume_streak_freeze(db)
    assert result is False


def test_consume_freeze_returns_true_when_available(db):
    db.execute("UPDATE streak_state SET streak_freeze=2 WHERE player_id='default'")
    db.commit()
    result = consume_streak_freeze(db)
    assert result is True


def test_consume_freeze_decrements_count(db):
    db.execute("UPDATE streak_state SET streak_freeze=2 WHERE player_id='default'")
    db.commit()
    consume_streak_freeze(db)
    db.commit()
    row = db.execute("SELECT streak_freeze FROM streak_state WHERE player_id='default'").fetchone()
    assert int(row["streak_freeze"]) == 1


# ── update_streak freeze protection ───────────────────────────────────────────

def test_freeze_prevents_streak_reset(db):
    today = date.today()
    yesterday = today - timedelta(days=1)
    three_days_ago = today - timedelta(days=3)

    # Build a streak up to yesterday
    update_streak(db, three_days_ago)
    update_streak(db, three_days_ago + timedelta(days=1))
    update_streak(db, yesterday)
    db.commit()
    assert get_streak(db)["current_streak"] == 3

    # Give the player a freeze
    db.execute("UPDATE streak_state SET streak_freeze=1 WHERE player_id='default'")
    db.commit()

    # Simulate "today" — gap was yesterday→today (skipped a day), freeze should protect
    # But the player already has last_active_date=yesterday, and today is consecutive
    # so actually no gap. Let's skip to 2 days later instead.
    future = today + timedelta(days=2)
    update_streak(db, future)
    db.commit()

    # Freeze consumed: streak should NOT have reset to 1
    streak = get_streak(db)
    assert streak["current_streak"] == 3  # kept, freeze consumed


def test_no_freeze_causes_reset(db):
    today = date.today()
    # Set last_active_date to 3 days ago — will cause gap
    three_ago = (today - timedelta(days=3)).isoformat()
    db.execute(
        "UPDATE streak_state SET current_streak=5, last_active_date=? WHERE player_id='default'",
        (three_ago,),
    )
    db.commit()

    update_streak(db, today)
    db.commit()
    streak = get_streak(db)
    assert streak["current_streak"] == 1  # reset because no freeze


# ── API endpoints ──────────────────────────────────────────────────────────────

def test_get_streak_freeze_returns_shape(client):
    r = client.get("/player/streak-freeze")
    assert r.status_code == 200
    data = r.json()
    assert "freeze_count" in data
    assert "max_freezes" in data
    assert "cost_next" in data
    assert "can_buy" in data


def test_buy_streak_freeze_increments(client, db):
    r = client.post("/player/streak-freeze/buy")
    assert r.status_code == 200
    data = r.json()
    assert data["freeze_count"] == 1
    assert data["xp_spent"] == 100


def test_buy_freeze_deducts_xp(client, db):
    client.post("/player/streak-freeze/buy")
    row = db.execute(
        "SELECT COALESCE(SUM(xp),0) AS total FROM player_category_xp WHERE character_id=?",
        (_PLAYER,),
    ).fetchone()
    assert int(row["total"]) == 400  # 500 - 100


def test_buy_freeze_cost_doubles(client, db):
    client.post("/player/streak-freeze/buy")   # cost 100
    r = client.post("/player/streak-freeze/buy")   # cost 200
    assert r.status_code == 200
    data = r.json()
    assert data["xp_spent"] == 200
    assert data["freeze_count"] == 2


def test_buy_freeze_402_on_insufficient_xp(client, db):
    # Remove all XP
    db.execute("DELETE FROM player_category_xp WHERE character_id=?", (_PLAYER,))
    db.commit()
    r = client.post("/player/streak-freeze/buy")
    assert r.status_code == 402


def test_buy_freeze_409_at_max(client, db):
    db.execute("UPDATE streak_state SET streak_freeze=3 WHERE player_id='default'")
    db.commit()
    r = client.post("/player/streak-freeze/buy")
    assert r.status_code == 409
