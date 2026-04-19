"""Tests for player-set mood system and daily login streak."""
import json
import sqlite3
from datetime import datetime, timezone, timedelta, date
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_PLAYER = "player_default"
_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', ?)",
        (_PLAYER, _VISUAL),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── GET /player/mood ──────────────────────────────────────────────────────────

def test_mood_get_shape(client):
    r = client.get("/player/mood")
    assert r.status_code == 200
    d = r.json()
    assert "mood" in d
    assert "mood_set_at" in d
    assert "drop_multiplier" in d


def test_mood_default_is_neutral(client):
    r = client.get("/player/mood")
    assert r.json()["mood"] == "neutral"
    assert r.json()["drop_multiplier"] == 1.0


# ── PATCH /player/mood ────────────────────────────────────────────────────────

def test_mood_patch_happy(client):
    r = client.patch("/player/mood", json={"mood": "happy"})
    assert r.status_code == 200
    assert r.json()["mood"] == "happy"
    assert r.json()["drop_multiplier"] == 1.15


def test_mood_patch_sad(client):
    r = client.patch("/player/mood", json={"mood": "sad"})
    assert r.status_code == 200
    assert r.json()["drop_multiplier"] == 0.9


def test_mood_patch_anxious(client):
    r = client.patch("/player/mood", json={"mood": "anxious"})
    assert r.status_code == 200
    assert r.json()["drop_multiplier"] == 0.85


def test_mood_patch_neutral(client):
    r = client.patch("/player/mood", json={"mood": "neutral"})
    assert r.status_code == 200
    assert r.json()["drop_multiplier"] == 1.0


def test_mood_invalid_rejected(client):
    r = client.patch("/player/mood", json={"mood": "ecstatic"})
    assert r.status_code == 422


def test_mood_persists_in_get(client):
    client.patch("/player/mood", json={"mood": "happy"})
    r = client.get("/player/mood")
    assert r.json()["mood"] == "happy"
    assert r.json()["mood_set_at"] is not None


def test_mood_decay_after_24h(db, client):
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    db.execute(
        "UPDATE player_profile SET mood='happy', mood_set_at=? WHERE character_id=?",
        (old_ts, _PLAYER),
    )
    db.commit()
    r = client.get("/player/mood")
    # Stored mood shows "happy" but multiplier decays to neutral
    assert r.json()["drop_multiplier"] == 1.0


def test_mood_set_at_updates_on_patch(client):
    client.patch("/player/mood", json={"mood": "happy"})
    r1 = client.get("/player/mood")
    ts1 = r1.json()["mood_set_at"]
    client.patch("/player/mood", json={"mood": "sad"})
    r2 = client.get("/player/mood")
    ts2 = r2.json()["mood_set_at"]
    assert ts2 >= ts1


# ── GET /player/login-streak ──────────────────────────────────────────────────

def test_login_streak_shape(client):
    r = client.get("/player/login-streak")
    assert r.status_code == 200
    d = r.json()
    assert "current_streak" in d
    assert "last_login_date" in d
    assert "next_reward_at" in d


def test_login_streak_zero_initially(client):
    r = client.get("/player/login-streak")
    assert r.json()["current_streak"] == 0


# ── POST /player/login-checkin ────────────────────────────────────────────────

def test_first_checkin_sets_streak_1(client):
    r = client.post("/player/login-checkin")
    assert r.status_code == 200
    assert r.json()["login_streak"] == 1
    assert r.json()["xp_awarded"] == 10
    assert r.json()["streak_bonus"] is False


def test_checkin_idempotent_same_day(client):
    client.post("/player/login-checkin")
    r = client.post("/player/login-checkin")
    assert r.json()["already_checked_in"] is True
    assert r.json()["xp_awarded"] == 0


def test_checkin_increments_consecutive_days(client, db):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db.execute(
        "UPDATE streak_state SET login_streak=3, last_login_date=? WHERE player_id='default'",
        (yesterday,),
    )
    db.commit()
    r = client.post("/player/login-checkin")
    assert r.json()["login_streak"] == 4


def test_checkin_resets_on_missed_day(client, db):
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()
    db.execute(
        "UPDATE streak_state SET login_streak=5, last_login_date=? WHERE player_id='default'",
        (two_days_ago,),
    )
    db.commit()
    r = client.post("/player/login-checkin")
    assert r.json()["login_streak"] == 1


def test_checkin_day7_bonus(client, db):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db.execute(
        "UPDATE streak_state SET login_streak=6, last_login_date=? WHERE player_id='default'",
        (yesterday,),
    )
    db.commit()
    r = client.post("/player/login-checkin")
    assert r.json()["login_streak"] == 7
    assert r.json()["streak_bonus"] is True
    assert r.json()["xp_awarded"] == 110  # 10 base + 100 bonus


def test_checkin_streak_in_get_after_checkin(client):
    client.post("/player/login-checkin")
    r = client.get("/player/login-streak")
    assert r.json()["current_streak"] == 1


def test_checkin_next_reward_at(client):
    r = client.post("/player/login-checkin")
    assert r.json()["next_reward_at"] == 6  # 7 - (1 % 7) = 6
