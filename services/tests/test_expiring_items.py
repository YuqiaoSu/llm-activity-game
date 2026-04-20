"""Tests for GET /inventory/expiring."""
import json
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
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


def _add_item_def(db, item_id: str, rarity: str = "COMMON", category: str = "WORK") -> str:
    data = json.dumps({"name": item_id, "rarity": rarity, "category": category})
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, data),
    )
    db.commit()
    return item_id


def _add_inventory(db, item_id: str, expires_at: str | None) -> str:
    import uuid
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, expires_at)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'test', ?)",
        (iid, item_id, expires_at),
    )
    db.commit()
    return iid


def _future(days: float) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _past(days: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def test_empty_when_no_items(client):
    result = client.get("/inventory/expiring").json()
    assert result == []


def test_empty_when_no_expiring_items(client, db):
    _add_item_def(db, "item_no_expiry")
    _add_inventory(db, "item_no_expiry", None)
    result = client.get("/inventory/expiring").json()
    assert result == []


def test_finds_soon_expiring(client, db):
    _add_item_def(db, "item_soon")
    _add_inventory(db, "item_soon", _future(3))
    result = client.get("/inventory/expiring").json()
    assert len(result) == 1
    assert result[0]["item_id"] == "item_soon"


def test_excludes_far_future(client, db):
    _add_item_def(db, "item_far")
    _add_inventory(db, "item_far", _future(30))
    result = client.get("/inventory/expiring").json()
    assert result == []


def test_excludes_already_expired(client, db):
    _add_item_def(db, "item_expired")
    _add_inventory(db, "item_expired", _past(1))
    result = client.get("/inventory/expiring").json()
    assert result == []


def test_days_param_boundary(client, db):
    _add_item_def(db, "item_day10")
    _add_inventory(db, "item_day10", _future(10))
    assert client.get("/inventory/expiring?days=7").json() == []
    result = client.get("/inventory/expiring?days=14").json()
    assert len(result) == 1


def test_sorted_ascending(client, db):
    _add_item_def(db, "item_a")
    _add_item_def(db, "item_b")
    _add_inventory(db, "item_a", _future(5))
    _add_inventory(db, "item_b", _future(2))
    result = client.get("/inventory/expiring").json()
    assert len(result) == 2
    assert result[0]["item_id"] == "item_b"
    assert result[1]["item_id"] == "item_a"


def test_response_shape(client, db):
    _add_item_def(db, "shape_item", rarity="RARE", category="SOCIAL")
    _add_inventory(db, "shape_item", _future(3))
    entry = client.get("/inventory/expiring").json()[0]
    for key in ("instance_id", "item_id", "item_name", "rarity", "category", "expires_at", "days_left"):
        assert key in entry
    assert entry["rarity"] == "RARE"
    assert entry["category"] == "SOCIAL"
    assert entry["days_left"] >= 0
