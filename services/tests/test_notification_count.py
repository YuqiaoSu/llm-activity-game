"""Tests for GET /notifications/count unread badge endpoint."""
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db, bootstrap_defaults
from services.api.main import app


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    bootstrap_defaults(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app.state.db = db
    return TestClient(app)


def _insert_notif(db, event_type: str = "level_up", acknowledged: int = 0) -> str:
    import uuid, json
    from datetime import datetime, timezone
    nid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, acknowledged, created_at)"
        " VALUES (?, 'player_default', ?, ?, ?, ?)",
        (nid, event_type, json.dumps({}), acknowledged, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    return nid


def test_count_zero_when_no_notifications(client):
    resp = client.get("/notifications/count")
    assert resp.status_code == 200
    assert resp.json() == {"unread": 0}


def test_count_increments_on_insert(client, db):
    _insert_notif(db, "level_up")
    resp = client.get("/notifications/count")
    assert resp.json()["unread"] == 1


def test_count_ignores_acknowledged(client, db):
    _insert_notif(db, "level_up", acknowledged=1)
    resp = client.get("/notifications/count")
    assert resp.json()["unread"] == 0


def test_count_multiple_unread(client, db):
    _insert_notif(db, "level_up")
    _insert_notif(db, "item_drop")
    _insert_notif(db, "xp_milestone")
    resp = client.get("/notifications/count")
    assert resp.json()["unread"] == 3


def test_count_decrements_after_ack_all(client, db):
    _insert_notif(db)
    _insert_notif(db)
    client.post("/notifications/ack-all")
    resp = client.get("/notifications/count")
    assert resp.json()["unread"] == 0


def test_count_response_has_unread_key(client):
    resp = client.get("/notifications/count")
    assert "unread" in resp.json()
