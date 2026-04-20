"""Tests for GET /player/timeline."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (_VISUAL,),
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


def _insert_event(db, event_type: str, payload: dict, ts: str):
    db.execute(
        "INSERT INTO pending_notifications (character_id, event_type, payload, created_at)"
        " VALUES ('player_default', ?, ?, ?)",
        (event_type, json.dumps(payload), ts),
    )
    db.commit()


def test_empty_returns_empty(client):
    r = client.get("/player/timeline")
    assert r.status_code == 200
    assert r.json() == []


def test_response_shape(client, db):
    _insert_event(db, "level_up", {"new_level": 5}, "2025-01-01T10:00:00")
    r = client.get("/player/timeline")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 1
    e = entries[0]
    assert "event_type" in e
    assert "title" in e
    assert "detail" in e
    assert "happened_at" in e


def test_level_up_entry(client, db):
    _insert_event(db, "level_up", {"new_level": 7}, "2025-01-01T10:00:00")
    e = client.get("/player/timeline").json()[0]
    assert e["event_type"] == "level_up"
    assert "7" in e["title"]


def test_achievement_entry(client, db):
    _insert_event(db, "achievement_unlocked",
                  {"name": "First Steps", "description": "Begin your journey"},
                  "2025-01-01T10:00:00")
    e = client.get("/player/timeline").json()[0]
    assert e["event_type"] == "achievement_unlocked"
    assert "First Steps" in e["title"]
    assert e["detail"] == "Begin your journey"


def test_newest_first_ordering(client, db):
    _insert_event(db, "level_up", {"new_level": 2}, "2025-01-01T09:00:00")
    _insert_event(db, "level_up", {"new_level": 3}, "2025-01-02T09:00:00")
    entries = client.get("/player/timeline").json()
    assert entries[0]["title"].endswith("3")
    assert entries[1]["title"].endswith("2")


def test_only_whitelisted_event_types(client, db):
    _insert_event(db, "level_up", {"new_level": 2}, "2025-01-01T10:00:00")
    _insert_event(db, "item_drop", {"item_id": "x"}, "2025-01-01T11:00:00")
    _insert_event(db, "daily_goal_hit", {}, "2025-01-01T12:00:00")
    entries = client.get("/player/timeline").json()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "level_up"


def test_limit_param(client, db):
    for i in range(5):
        _insert_event(db, "level_up", {"new_level": i + 1}, f"2025-01-0{i+1}T10:00:00")
    entries = client.get("/player/timeline?limit=3").json()
    assert len(entries) == 3


def test_wishlist_drop_entry(client, db):
    _insert_event(db, "item_drop_wishlist",
                  {"item_name": "Crystal Orb", "rarity": "RARE"},
                  "2025-01-01T10:00:00")
    e = client.get("/player/timeline").json()[0]
    assert "Crystal Orb" in e["title"]
    assert e["detail"] == "RARE"


def test_streak_milestone_entry(client, db):
    _insert_event(db, "streak_milestone", {"milestone": 7}, "2025-01-01T10:00:00")
    e = client.get("/player/timeline").json()[0]
    assert "7" in e["title"]
