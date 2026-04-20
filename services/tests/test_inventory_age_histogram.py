"""Tests for GET /inventory/age-histogram."""
import json
import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta

from services.storage.db import init_db

_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


def _item_data(item_id: str, rarity: str = "COMMON") -> str:
    return json.dumps({
        "item_id": item_id, "name": item_id, "rarity": rarity,
        "category": "WORK", "description": "", "effects": [],
        "icon": "", "stackable": False, "set_id": None,
        "drop_requirement": {"activity_label": None, "min_duration_sec": 0,
                             "min_confidence": 0.0, "time_of_day": None},
    })


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


def _add_item(db, item_id: str, days_ago: int, rarity: str = "COMMON"):
    acquired = (date.today() - timedelta(days=days_ago)).isoformat() + "T00:00:00"
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
               (item_id, _item_data(item_id, rarity)))
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, ?, 'test')",
        (str(uuid.uuid4()), item_id, acquired),
    )
    db.commit()


def test_empty_inventory_returns_all_buckets(client):
    r = client.get("/inventory/age-histogram")
    assert r.status_code == 200
    data = r.json()
    labels = [b["bucket"] for b in data]
    assert labels == ["0-7d", "8-30d", "31-90d", "91-365d", "365d+"]
    for b in data:
        assert b["count"] == 0
        assert b["value_xp"] == 0


def test_response_shape(client, db):
    _add_item(db, "i1", 0)
    data = client.get("/inventory/age-histogram").json()
    assert len(data) == 5
    b = data[0]
    assert "bucket" in b
    assert "count" in b
    assert "value_xp" in b


def test_item_today_in_first_bucket(client, db):
    _add_item(db, "i1", 0)
    data = client.get("/inventory/age-histogram").json()
    assert data[0]["bucket"] == "0-7d"
    assert data[0]["count"] == 1


def test_item_7_days_ago_in_first_bucket(client, db):
    _add_item(db, "i1", 7)
    data = client.get("/inventory/age-histogram").json()
    assert data[0]["count"] == 1


def test_item_8_days_ago_in_second_bucket(client, db):
    _add_item(db, "i1", 8)
    data = client.get("/inventory/age-histogram").json()
    assert data[1]["bucket"] == "8-30d"
    assert data[1]["count"] == 1


def test_old_item_in_last_bucket(client, db):
    _add_item(db, "i1", 400)
    data = client.get("/inventory/age-histogram").json()
    assert data[4]["bucket"] == "365d+"
    assert data[4]["count"] == 1


def test_value_xp_uses_sell_values(client, db):
    _add_item(db, "leg1", 0, "LEGENDARY")
    data = client.get("/inventory/age-histogram").json()
    assert data[0]["value_xp"] == 100  # LEGENDARY sell value


def test_total_count_matches_inventory(client, db):
    _add_item(db, "i1", 2)
    _add_item(db, "i2", 15)
    _add_item(db, "i3", 50)
    data = client.get("/inventory/age-histogram").json()
    total = sum(b["count"] for b in data)
    assert total == 3
