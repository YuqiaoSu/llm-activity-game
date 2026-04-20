"""Tests for GET /inventory/value-summary."""
import json
import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient

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


def _add_item(db, item_id: str, rarity: str = "COMMON"):
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
               (item_id, _item_data(item_id, rarity)))
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, '2025-01-01T00:00:00', 'test')",
        (str(uuid.uuid4()), item_id),
    )
    db.commit()


def test_empty_inventory(client):
    r = client.get("/inventory/value-summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total_items"] == 0
    assert body["by_rarity"] == {}
    assert body["estimated_value"] == 0


def test_response_shape(client, db):
    _add_item(db, "c1", "COMMON")
    r = client.get("/inventory/value-summary")
    assert r.status_code == 200
    body = r.json()
    assert "total_items" in body
    assert "by_rarity" in body
    assert "estimated_value" in body


def test_single_common_item(client, db):
    _add_item(db, "c1", "COMMON")
    r = client.get("/inventory/value-summary")
    body = r.json()
    assert body["total_items"] == 1
    assert body["by_rarity"].get("COMMON") == 1
    assert body["estimated_value"] == 5  # COMMON sell value


def test_mixed_rarities(client, db):
    _add_item(db, "c1", "COMMON")
    _add_item(db, "r1", "RARE")
    _add_item(db, "l1", "LEGENDARY")
    r = client.get("/inventory/value-summary")
    body = r.json()
    assert body["total_items"] == 3
    assert body["by_rarity"]["COMMON"] == 1
    assert body["by_rarity"]["RARE"] == 1
    assert body["by_rarity"]["LEGENDARY"] == 1
    # 5 + 30 + 100 = 135
    assert body["estimated_value"] == 135


def test_multiple_same_rarity(client, db):
    _add_item(db, "c1", "COMMON")
    _add_item(db, "c2", "COMMON")
    _add_item(db, "c3", "COMMON")
    r = client.get("/inventory/value-summary")
    body = r.json()
    assert body["total_items"] == 3
    assert body["by_rarity"]["COMMON"] == 3
    assert body["estimated_value"] == 15  # 3 × 5


def test_legendary_value(client, db):
    _add_item(db, "leg1", "LEGENDARY")
    r = client.get("/inventory/value-summary")
    assert r.json()["estimated_value"] == 100


def test_all_rarity_tiers(client, db):
    for rarity, item_id in [("COMMON","c"), ("UNCOMMON","u"), ("RARE","r"),
                              ("EPIC","e"), ("LEGENDARY","l")]:
        _add_item(db, item_id, rarity)
    body = client.get("/inventory/value-summary").json()
    assert body["total_items"] == 5
    # 5 + 15 + 30 + 60 + 100 = 210
    assert body["estimated_value"] == 210
    assert len(body["by_rarity"]) == 5
