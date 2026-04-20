"""Tests for GET /player/journal — player event timeline."""
import json
import sqlite3
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
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 10)",
        (_PLAYER,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _insert_notification(db, event_type: str, payload: dict, created_at: str = "2025-01-01T10:00:00"):
    import uuid
    db.execute(
        "INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), _PLAYER, event_type, json.dumps(payload), created_at),
    )
    db.commit()


def test_journal_empty(client):
    r = client.get("/player/journal")
    assert r.status_code == 200
    assert r.json() == []


def test_journal_shape(client, db):
    _insert_notification(db, "level_up", {"new_level": 3})
    r = client.get("/player/journal")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 1
    entry = entries[0]
    assert "event_type" in entry
    assert "summary" in entry
    assert "happened_at" in entry


def test_journal_event_type_present(client, db):
    _insert_notification(db, "item_drop", {"item_name": "Shiny Widget", "rarity": "RARE"})
    r = client.get("/player/journal")
    entries = r.json()
    assert entries[0]["event_type"] == "item_drop"


def test_journal_summary_not_empty(client, db):
    _insert_notification(db, "achievement_unlock", {"name": "First Blood"})
    r = client.get("/player/journal")
    assert r.json()[0]["summary"] != ""


def test_journal_summary_item_drop(client, db):
    _insert_notification(db, "item_drop", {"item_name": "Orb", "rarity": "EPIC"})
    r = client.get("/player/journal")
    summary = r.json()[0]["summary"]
    assert "Orb" in summary
    assert "EPIC" in summary


def test_journal_summary_level_up(client, db):
    _insert_notification(db, "level_up", {"new_level": 5})
    r = client.get("/player/journal")
    assert "5" in r.json()[0]["summary"]


def test_journal_newest_first(client, db):
    _insert_notification(db, "level_up", {"new_level": 2}, "2025-01-01T08:00:00")
    _insert_notification(db, "level_up", {"new_level": 3}, "2025-01-02T08:00:00")
    r = client.get("/player/journal")
    entries = r.json()
    assert entries[0]["happened_at"] > entries[1]["happened_at"]


def test_journal_limit_respected(client, db):
    for i in range(10):
        _insert_notification(db, "item_drop", {"item_name": f"item_{i}"}, f"2025-01-{i+1:02d}T00:00:00")
    r = client.get("/player/journal?limit=3")
    assert len(r.json()) == 3


def test_journal_multiple_event_types(client, db):
    _insert_notification(db, "level_up", {"new_level": 2})
    _insert_notification(db, "achievement_unlock", {"name": "Go-getter"})
    _insert_notification(db, "recovery_gift", {"item_name": "Crystal"})
    r = client.get("/player/journal")
    types = {e["event_type"] for e in r.json()}
    assert "level_up" in types
    assert "achievement_unlock" in types
    assert "recovery_gift" in types


def test_journal_recovery_gift_summary(client, db):
    _insert_notification(db, "recovery_gift", {"item_name": "WelcomePack"})
    r = client.get("/player/journal")
    assert "WelcomePack" in r.json()[0]["summary"]
