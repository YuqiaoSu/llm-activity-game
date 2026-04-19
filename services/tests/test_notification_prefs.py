"""Tests for GET/PATCH /notifications/prefs and mute-gate in _insert_notification."""
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db, bootstrap_defaults
from services.reward_ledger.ledger import _insert_notification
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


# ── GET /notifications/prefs ───────────────────────────────────────────────────

def test_get_prefs_returns_list(client):
    resp = client.get("/notifications/prefs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_prefs_all_unmuted_by_default(client):
    data = client.get("/notifications/prefs").json()
    assert all(not item["muted"] for item in data)


def test_get_prefs_contains_known_types(client):
    event_types = {item["event_type"] for item in client.get("/notifications/prefs").json()}
    assert "item_drop" in event_types
    assert "level_up" in event_types
    assert "achievement_unlock" in event_types


# ── PATCH /notifications/prefs/{event_type} ────────────────────────────────────

def test_patch_pref_mutes_type(client):
    client.patch("/notifications/prefs/item_drop", json={"muted": True})
    prefs = {i["event_type"]: i["muted"] for i in client.get("/notifications/prefs").json()}
    assert prefs["item_drop"] is True


def test_patch_pref_unmutes_type(client):
    client.patch("/notifications/prefs/item_drop", json={"muted": True})
    client.patch("/notifications/prefs/item_drop", json={"muted": False})
    prefs = {i["event_type"]: i["muted"] for i in client.get("/notifications/prefs").json()}
    assert prefs["item_drop"] is False


def test_patch_pref_unknown_type_returns_404(client):
    resp = client.patch("/notifications/prefs/nonexistent_type", json={"muted": True})
    assert resp.status_code == 404


# ── mute gate in _insert_notification ─────────────────────────────────────────

def test_muted_type_does_not_insert_notification(db):
    db.execute(
        "UPDATE notification_prefs SET muted=1 WHERE player_id='player_default' AND event_type='item_drop'"
    )
    db.commit()
    _insert_notification(db, "player_default", "item_drop", {"test": True})
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) AS n FROM pending_notifications WHERE event_type='item_drop'"
    ).fetchone()["n"]
    assert count == 0


def test_unmuted_type_inserts_notification(db):
    _insert_notification(db, "player_default", "item_drop", {"test": True})
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) AS n FROM pending_notifications WHERE event_type='item_drop'"
    ).fetchone()["n"]
    assert count == 1


def test_muting_one_type_does_not_affect_others(db):
    db.execute(
        "UPDATE notification_prefs SET muted=1 WHERE player_id='player_default' AND event_type='item_drop'"
    )
    db.commit()
    _insert_notification(db, "player_default", "level_up", {"new_level": 2})
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) AS n FROM pending_notifications WHERE event_type='level_up'"
    ).fetchone()["n"]
    assert count == 1


def test_unknown_type_still_inserts_if_not_in_prefs(db):
    # Event types not in the known list have no pref row — they pass through unmuted
    _insert_notification(db, "player_default", "some_new_type", {"data": 1})
    db.commit()
    count = db.execute(
        "SELECT COUNT(*) AS n FROM pending_notifications WHERE event_type='some_new_type'"
    ).fetchone()["n"]
    assert count == 1
