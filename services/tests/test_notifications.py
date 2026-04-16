"""Tests for the notifications router: inbox filtering, ack-all, ack-by-type."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({
        "base_sprite": "x.png", "evolution_stage": 0,
        "skin": None, "accessories": [], "anim_state": "idle",
    })
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.commit()
    yield conn
    conn.close()


def _insert_notif(db, event_type: str, payload: dict, acknowledged: int = 0) -> str:
    nid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO pending_notifications "
        "(notification_id, character_id, event_type, payload, created_at, acknowledged) "
        "VALUES (?, 'player_default', ?, ?, ?, ?)",
        (nid, event_type, json.dumps(payload), now, acknowledged),
    )
    db.commit()
    return nid


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


# ── GET /notifications/inbox ──────────────────────────────────────────────────

def test_inbox_empty_returns_empty_list(client):
    resp = client.get("/notifications/inbox")
    assert resp.status_code == 200
    assert resp.json() == []


def test_inbox_returns_all_types(db, client):
    _insert_notif(db, "item_drop", {"item_name": "Scroll"})
    _insert_notif(db, "level_up", {"new_level": 5})
    resp = client.get("/notifications/inbox")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_inbox_filter_by_event_type(db, client):
    _insert_notif(db, "item_drop", {"item_name": "Scroll"})
    _insert_notif(db, "level_up", {"new_level": 5})
    resp = client.get("/notifications/inbox?event_type=item_drop")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "item_drop"


def test_inbox_filter_place_level_up(db, client):
    _insert_notif(db, "place_level_up", {"place_name": "Lab", "new_level": 2})
    _insert_notif(db, "item_drop", {"item_name": "Scroll"})
    resp = client.get("/notifications/inbox?event_type=place_level_up")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "place_level_up"


def test_inbox_includes_acknowledged_entries(db, client):
    _insert_notif(db, "item_drop", {"item_name": "Scroll"}, acknowledged=1)
    resp = client.get("/notifications/inbox")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_inbox_limit_param(db, client):
    for i in range(5):
        _insert_notif(db, "item_drop", {"item_name": f"item_{i}"})
    resp = client.get("/notifications/inbox?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_inbox_newest_first(db, client):
    import time
    _insert_notif(db, "level_up", {"new_level": 1})
    time.sleep(0.01)
    _insert_notif(db, "level_up", {"new_level": 2})
    resp = client.get("/notifications/inbox?event_type=level_up")
    entries = resp.json()
    p1 = json.loads(entries[0]["payload"])
    p2 = json.loads(entries[1]["payload"])
    assert p1["new_level"] > p2["new_level"]   # level 2 first


# ── POST /notifications/ack-all ───────────────────────────────────────────────

def test_ack_all_marks_all_as_acknowledged(db, client):
    _insert_notif(db, "item_drop", {})
    _insert_notif(db, "level_up", {})
    resp = client.post("/notifications/ack-all")
    assert resp.status_code == 200
    assert resp.json()["acknowledged_count"] == 2


def test_ack_all_idempotent(db, client):
    _insert_notif(db, "item_drop", {}, acknowledged=1)
    resp = client.post("/notifications/ack-all")
    assert resp.json()["acknowledged_count"] == 0


# ── POST /notifications/ack-by-type ──────────────────────────────────────────

def test_ack_by_type_only_targets_type(db, client):
    _insert_notif(db, "item_drop", {})
    _insert_notif(db, "level_up", {})
    resp = client.post("/notifications/ack-by-type", json={"event_type": "item_drop"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["acknowledged_count"] == 1
    assert body["event_type"] == "item_drop"

    # level_up should still be unread
    row = db.execute(
        "SELECT acknowledged FROM pending_notifications WHERE event_type='level_up'"
    ).fetchone()
    assert row["acknowledged"] == 0


def test_ack_by_type_returns_count(db, client):
    _insert_notif(db, "item_drop", {})
    _insert_notif(db, "item_drop", {})
    resp = client.post("/notifications/ack-by-type", json={"event_type": "item_drop"})
    assert resp.json()["acknowledged_count"] == 2


def test_ack_by_type_place_level_up(db, client):
    _insert_notif(db, "place_level_up", {"place_name": "Lab", "new_level": 2})
    resp = client.post("/notifications/ack-by-type", json={"event_type": "place_level_up"})
    assert resp.status_code == 200
    assert resp.json()["acknowledged_count"] == 1


def test_ack_by_type_empty_event_type_returns_400(client):
    resp = client.post("/notifications/ack-by-type", json={"event_type": ""})
    assert resp.status_code == 400


def test_ack_by_type_nonexistent_type_returns_zero(db, client):
    _insert_notif(db, "item_drop", {})
    resp = client.post("/notifications/ack-by-type", json={"event_type": "no_such_type"})
    assert resp.status_code == 200
    assert resp.json()["acknowledged_count"] == 0
