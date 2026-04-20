"""Tests for GET /notifications/summary."""
import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_VISUAL = '{"base_sprite":"x.png","evolution_stage":0,"skin":null,"accessories":[],"anim_state":"idle"}'


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


def _notif(db, event_type: str, acked: int = 0):
    db.execute(
        "INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at, acknowledged)"
        " VALUES (?, 'player_default', ?, '{}', '2025-01-01T00:00:00', ?)",
        (str(uuid.uuid4()), event_type, acked),
    )
    db.commit()


def test_empty_summary(client):
    body = client.get("/notifications/summary").json()
    assert body["total"] == 0
    assert body["unread"] == 0
    assert body["by_type"] == []


def test_response_shape(client, db):
    _notif(db, "item_drop")
    body = client.get("/notifications/summary").json()
    assert "total" in body
    assert "unread" in body
    assert "by_type" in body
    entry = body["by_type"][0]
    for key in ("event_type", "total", "unread", "latest_at"):
        assert key in entry


def test_counts_accumulate(client, db):
    for _ in range(3):
        _notif(db, "item_drop")
    _notif(db, "level_up")
    body = client.get("/notifications/summary").json()
    assert body["total"] == 4
    by = {e["event_type"]: e for e in body["by_type"]}
    assert by["item_drop"]["total"] == 3
    assert by["level_up"]["total"] == 1


def test_unread_excludes_acked(client, db):
    _notif(db, "item_drop", acked=0)
    _notif(db, "item_drop", acked=0)
    _notif(db, "item_drop", acked=1)
    body = client.get("/notifications/summary").json()
    assert body["unread"] == 2
    assert body["by_type"][0]["unread"] == 2
    assert body["by_type"][0]["total"] == 3


def test_sorted_by_total_desc(client, db):
    _notif(db, "level_up")
    for _ in range(5):
        _notif(db, "item_drop")
    body = client.get("/notifications/summary").json()
    totals = [e["total"] for e in body["by_type"]]
    assert totals == sorted(totals, reverse=True)


def test_grand_total_matches_sum(client, db):
    for _ in range(4):
        _notif(db, "item_drop")
    for _ in range(2):
        _notif(db, "level_up")
    body = client.get("/notifications/summary").json()
    assert body["total"] == sum(e["total"] for e in body["by_type"])


def test_grand_unread_matches_sum(client, db):
    _notif(db, "item_drop", acked=0)
    _notif(db, "item_drop", acked=1)
    _notif(db, "level_up", acked=0)
    body = client.get("/notifications/summary").json()
    assert body["unread"] == sum(e["unread"] for e in body["by_type"])


def test_capped_at_ten_types(client, db):
    for i in range(12):
        _notif(db, f"type_{i:02d}")
    body = client.get("/notifications/summary").json()
    assert len(body["by_type"]) <= 10
