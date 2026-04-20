"""Tests for POST /inventory/batch-tag."""
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


def _add_item(db, item_id: str = "itm") -> str:
    data = json.dumps({"name": item_id, "rarity": "COMMON", "category": "WORK"})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data))
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'test')",
        (iid, item_id),
    )
    db.commit()
    return iid


def test_empty_instance_ids_returns_422(client):
    r = client.post("/inventory/batch-tag", json={"instance_ids": [], "tags": ["test"]})
    assert r.status_code == 422


def test_too_many_tags_returns_422(client, db):
    iid = _add_item(db)
    r = client.post("/inventory/batch-tag", json={
        "instance_ids": [iid], "tags": ["a", "b", "c", "d"]
    })
    assert r.status_code == 422


def test_tag_too_long_returns_422(client, db):
    iid = _add_item(db)
    r = client.post("/inventory/batch-tag", json={
        "instance_ids": [iid], "tags": ["x" * 13]
    })
    assert r.status_code == 422


def test_updates_multiple_items(client, db):
    iid_a = _add_item(db, "itm_a")
    iid_b = _add_item(db, "itm_b")
    r = client.post("/inventory/batch-tag", json={
        "instance_ids": [iid_a, iid_b], "tags": ["focus"]
    })
    assert r.status_code == 200
    assert r.json()["updated_count"] == 2


def test_returns_updated_count(client, db):
    iid = _add_item(db)
    r = client.post("/inventory/batch-tag", json={"instance_ids": [iid], "tags": ["work"]})
    assert r.json()["updated_count"] == 1


def test_tags_appear_in_get_inventory(client, db):
    iid = _add_item(db)
    client.post("/inventory/batch-tag", json={"instance_ids": [iid], "tags": ["mytag"]})
    inv = client.get("/inventory").json()
    found = next((x for x in inv if x["item_id"] == "itm"), None)
    assert found is not None
    assert "mytag" in found.get("tags", [])


def test_unknown_instance_ids_silently_skipped(client, db):
    iid = _add_item(db)
    r = client.post("/inventory/batch-tag", json={
        "instance_ids": [iid, "nonexistent-id"], "tags": ["x"]
    })
    assert r.status_code == 200
    assert r.json()["updated_count"] == 1


def test_single_item_works(client, db):
    iid = _add_item(db)
    r = client.post("/inventory/batch-tag", json={"instance_ids": [iid], "tags": ["solo"]})
    assert r.status_code == 200
    assert r.json()["updated_count"] == 1
