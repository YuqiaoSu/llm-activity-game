"""Tests for item expiry — expired items excluded from inventory counts."""
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
    # Seed a test item type
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("item_test", json.dumps({"name": "Test Item", "rarity": "COMMON",
                                   "category": "WORK", "effects": []})),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app = create_app(db=db)
    return TestClient(app), db


def _add_item(db, item_id: str = "item_test", expires_at: str | None = None) -> str:
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, expires_at)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'chunk_x', ?)",
        (iid, item_id, expires_at),
    )
    db.commit()
    return iid


def _future(days: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ── permanent items unaffected ────────────────────────────────────────────────

def test_permanent_item_shown_normally(client):
    tc, db = client
    _add_item(db, expires_at=None)
    r = tc.get("/inventory")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["expires_at"] is None


def test_permanent_item_quantity_counts_correctly(client):
    tc, db = client
    _add_item(db, expires_at=None)
    _add_item(db, expires_at=None)
    r = tc.get("/inventory")
    assert r.json()[0]["quantity"] == 2


# ── expired items excluded ────────────────────────────────────────────────────

def test_expired_item_hidden_from_inventory(client):
    tc, db = client
    _add_item(db, expires_at=_past(1))
    r = tc.get("/inventory")
    assert r.json() == []


def test_expired_item_excluded_from_quantity(client):
    tc, db = client
    _add_item(db, expires_at=None)       # permanent copy
    _add_item(db, expires_at=_past(1))   # expired copy
    r = tc.get("/inventory")
    assert len(r.json()) == 1
    assert r.json()[0]["quantity"] == 1  # only the permanent copy


# ── future-expiring items shown ───────────────────────────────────────────────

def test_future_expiry_item_shown(client):
    tc, db = client
    _add_item(db, expires_at=_future(3))
    r = tc.get("/inventory")
    assert len(r.json()) == 1
    entry = r.json()[0]
    assert entry["expires_at"] is not None
    assert entry["quantity"] == 1


def test_expires_at_is_earliest_expiry(client):
    tc, db = client
    _add_item(db, expires_at=_future(10))
    _add_item(db, expires_at=_future(3))   # earlier expiry
    r = tc.get("/inventory")
    entry = r.json()[0]
    # Both are non-expired; expires_at should be the earlier one
    assert entry["quantity"] == 2
    assert entry["expires_at"] is not None


# ── schema migration ──────────────────────────────────────────────────────────

def test_expires_at_column_exists(client):
    tc, db = client
    _add_item(db, expires_at=None)
    r = tc.get("/inventory")
    assert "expires_at" in r.json()[0]


# ── mixed permanent and expiring ──────────────────────────────────────────────

def test_mixed_batch_shows_only_valid_quantity(client):
    tc, db = client
    _add_item(db, expires_at=None)         # permanent
    _add_item(db, expires_at=_future(5))   # expiring but valid
    _add_item(db, expires_at=_past(2))     # expired
    r = tc.get("/inventory")
    assert r.json()[0]["quantity"] == 2  # permanent + valid expiring
