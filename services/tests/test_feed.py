"""Tests for GET /feed — social activity feed endpoint."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Tester", visual),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app = create_app(db=db)
    return TestClient(app), db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _insert_chunk(db, category: str = "WORK", xp: int = 10) -> None:
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)"
        " VALUES (?, ?, ?, ?, 600, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category, xp, _now()),
    )
    db.commit()


def _insert_drop(db, item_id: str = "item_x") -> None:
    db.execute(
        "INSERT INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at)"
        " VALUES (?, ?, 0, ?, 'player_default', ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), item_id, _now()),
    )
    db.commit()


def _insert_notif(db, event_type: str) -> None:
    db.execute(
        "INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)"
        " VALUES (?, 'player_default', ?, '{}', ?)",
        (str(uuid.uuid4()), event_type, _now()),
    )
    db.commit()


# ── shape tests ───────────────────────────────────────────────────────────────

def test_feed_empty_returns_list(client):
    tc, _ = client
    r = tc.get("/feed")
    assert r.status_code == 200
    assert r.json() == []


def test_feed_entry_shape(client):
    tc, db = client
    _insert_chunk(db)
    r = tc.get("/feed")
    entry = r.json()[0]
    for key in ("event_type", "description", "happened_at"):
        assert key in entry


# ── event types ───────────────────────────────────────────────────────────────

def test_feed_includes_activity_events(client):
    tc, db = client
    _insert_chunk(db, "GAME", 25)
    r = tc.get("/feed")
    types = [e["event_type"] for e in r.json()]
    assert "activity" in types


def test_feed_includes_item_drop_events(client):
    tc, db = client
    _insert_drop(db)
    r = tc.get("/feed")
    types = [e["event_type"] for e in r.json()]
    assert "item_drop" in types


def test_feed_includes_level_up_events(client):
    tc, db = client
    _insert_notif(db, "level_up")
    r = tc.get("/feed")
    types = [e["event_type"] for e in r.json()]
    assert "level_up" in types


def test_feed_ignores_non_notable_notification_types(client):
    tc, db = client
    _insert_notif(db, "item_drop_ordinary")  # not in allowlist
    r = tc.get("/feed")
    assert r.json() == []


# ── ordering ──────────────────────────────────────────────────────────────────

def test_feed_newest_first(client):
    tc, db = client
    _insert_chunk(db)      # inserted at now
    _insert_drop(db)       # also at now but different type
    r = tc.get("/feed")
    happened_ats = [e["happened_at"] for e in r.json()]
    assert happened_ats == sorted(happened_ats, reverse=True)


# ── limit param ───────────────────────────────────────────────────────────────

def test_feed_limit_respected(client):
    tc, db = client
    for _ in range(10):
        _insert_chunk(db)
    r = tc.get("/feed?limit=3")
    assert len(r.json()) == 3


def test_feed_activity_description_contains_xp(client):
    tc, db = client
    _insert_chunk(db, "WORK", 42)
    r = tc.get("/feed")
    activity = next(e for e in r.json() if e["event_type"] == "activity")
    assert "42" in activity["description"]


# ── enrichment: item name in drop descriptions ────────────────────────────────

def _insert_item_def(db, item_id: str, name: str) -> None:
    data = json.dumps({"name": name, "rarity": "COMMON", "category": "WORK"})
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, data),
    )
    db.commit()


def test_drop_description_uses_item_name(client):
    tc, db = client
    _insert_item_def(db, "item_sword", "Iron Sword")
    _insert_drop(db, "item_sword")
    r = tc.get("/feed")
    drop = next(e for e in r.json() if e["event_type"] == "item_drop")
    assert "Iron Sword" in drop["description"]
    assert "item_sword" not in drop["description"]


def test_drop_description_falls_back_to_item_id(client):
    tc, db = client
    _insert_drop(db, "item_unknown_xyz")
    r = tc.get("/feed")
    drop = next(e for e in r.json() if e["event_type"] == "item_drop")
    assert "item_unknown_xyz" in drop["description"]


# ── enrichment: level number in level_up notifications ───────────────────────

def _insert_level_up_notif(db, new_level: int) -> None:
    payload = json.dumps({"new_level": new_level})
    db.execute(
        "INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)"
        " VALUES (?, 'player_default', 'level_up', ?, ?)",
        (str(uuid.uuid4()), payload, _now()),
    )
    db.commit()


def test_level_up_description_contains_level_number(client):
    tc, db = client
    _insert_level_up_notif(db, 7)
    r = tc.get("/feed")
    lu = next(e for e in r.json() if e["event_type"] == "level_up")
    assert "7" in lu["description"]
    assert "Lv." in lu["description"]


def test_level_up_description_with_empty_payload_shows_question_mark(client):
    tc, db = client
    _insert_notif(db, "level_up")  # payload = '{}'
    r = tc.get("/feed")
    lu = next(e for e in r.json() if e["event_type"] == "level_up")
    assert "?" in lu["description"]


# ── enrichment: milestone day count in streak_milestone notifications ─────────

def _insert_streak_milestone_notif(db, milestone: int) -> None:
    payload = json.dumps({"milestone": milestone})
    db.execute(
        "INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)"
        " VALUES (?, 'player_default', 'streak_milestone', ?, ?)",
        (str(uuid.uuid4()), payload, _now()),
    )
    db.commit()


def test_streak_milestone_description_contains_day_count(client):
    tc, db = client
    _insert_streak_milestone_notif(db, 14)
    r = tc.get("/feed")
    sm = next(e for e in r.json() if e["event_type"] == "streak_milestone")
    assert "14" in sm["description"]
    assert "Day" in sm["description"]


def test_streak_milestone_empty_payload_shows_question_mark(client):
    tc, db = client
    _insert_notif(db, "streak_milestone")  # payload = '{}'
    r = tc.get("/feed")
    sm = next(e for e in r.json() if e["event_type"] == "streak_milestone")
    assert "?" in sm["description"]
