"""Tests for POST /inventory/upgrade."""
import json
import sqlite3
import uuid
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


def _def(item_id: str, rarity: str, category: str = "WORK") -> str:
    return json.dumps({
        "item_id": item_id, "name": item_id, "rarity": rarity,
        "category": category, "description": "", "effects": [],
        "icon": "", "stackable": False, "set_id": None,
        "drop_requirement": {"activity_label": None, "min_duration_sec": 0,
                             "min_confidence": 0.0, "time_of_day": None},
    })


def _add_item(db, item_id: str, rarity: str, category: str = "WORK", n: int = 1) -> list:
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
               (item_id, _def(item_id, rarity, category)))
    ids = []
    for _ in range(n):
        iid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO inventory"
            " (instance_id, character_id, item_id, acquired_at, source_chunk)"
            " VALUES (?, 'player_default', ?, '2025-01-01T00:00:00', 'test')",
            (iid, item_id),
        )
        ids.append(iid)
    db.commit()
    return ids


def test_common_target_400(client):
    r = client.post("/inventory/upgrade", json={"target_rarity": "COMMON", "category": "WORK"})
    assert r.status_code == 400


def test_unknown_rarity_422(client):
    r = client.post("/inventory/upgrade", json={"target_rarity": "MYTHIC", "category": "WORK"})
    assert r.status_code == 422


def test_not_enough_items_400(client, db):
    _add_item(db, "sword", "COMMON", "WORK", n=1)   # only 1, need 2
    _add_item(db, "hammer", "UNCOMMON", "WORK")      # target tier result
    r = client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    assert r.status_code == 400


def test_successful_uncommon_craft(client, db):
    _add_item(db, "c1", "COMMON", "WORK", n=2)
    _add_item(db, "u1", "UNCOMMON", "WORK")
    r = client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    assert r.status_code == 200
    body = r.json()
    assert body["new_rarity"] == "UNCOMMON"
    assert body["new_category"] == "WORK"
    assert len(body["consumed_instance_ids"]) == 2


def test_consumed_items_removed(client, db):
    consumed = _add_item(db, "c1", "COMMON", "WORK", n=2)
    _add_item(db, "u1", "UNCOMMON", "WORK")
    client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    remaining = db.execute(
        "SELECT instance_id FROM inventory WHERE instance_id IN (?, ?)", consumed
    ).fetchall()
    assert len(remaining) == 0


def test_new_item_in_inventory(client, db):
    _add_item(db, "c1", "COMMON", "WORK", n=2)
    _add_item(db, "u1", "UNCOMMON", "WORK")
    body = client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"}).json()
    row = db.execute(
        "SELECT instance_id FROM inventory WHERE instance_id=?",
        (body["new_instance_id"],)
    ).fetchone()
    assert row is not None


def test_rare_craft_consumes_uncommon(client, db):
    _add_item(db, "u1", "UNCOMMON", "WORK", n=2)
    _add_item(db, "r1", "RARE", "WORK")
    body = client.post("/inventory/upgrade", json={"target_rarity": "RARE", "category": "WORK"}).json()
    assert body["new_rarity"] == "RARE"
    assert body["source_rarity"] == "UNCOMMON"


def test_legendary_craft_consumes_epic(client, db):
    _add_item(db, "e1", "EPIC", "WORK", n=2)
    _add_item(db, "leg1", "LEGENDARY", "WORK")
    body = client.post("/inventory/upgrade", json={"target_rarity": "LEGENDARY", "category": "WORK"}).json()
    assert body["new_rarity"] == "LEGENDARY"
    assert body["source_rarity"] == "EPIC"


def test_response_shape(client, db):
    _add_item(db, "c1", "COMMON", "WORK", n=2)
    _add_item(db, "u1", "UNCOMMON", "WORK")
    body = client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"}).json()
    for key in ("new_instance_id", "new_item_id", "new_rarity", "new_category",
                "new_item", "consumed_instance_ids", "source_rarity"):
        assert key in body


def test_locked_items_skipped(client, db):
    ids = _add_item(db, "c1", "COMMON", "WORK", n=2)
    # Lock both — upgrade should fail
    for iid in ids:
        db.execute("UPDATE inventory SET locked=1 WHERE instance_id=?", (iid,))
    db.commit()
    _add_item(db, "u1", "UNCOMMON", "WORK")
    r = client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    assert r.status_code == 400
