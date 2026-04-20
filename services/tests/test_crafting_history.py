"""Tests for GET /inventory/crafting-history and log insertion by upgrade/craft."""
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


def _add_def(db, item_id: str, rarity: str, category: str) -> str:
    data = json.dumps({"name": item_id, "rarity": rarity, "category": category})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data))
    db.commit()
    return item_id


def _add_inv(db, item_id: str) -> str:
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'test')",
        (iid, item_id),
    )
    db.commit()
    return iid


def _setup_upgrade(db):
    """Two COMMON WORK items + one UNCOMMON WORK item definition for upgrade target."""
    _add_def(db, "common_a", "COMMON", "WORK")
    _add_def(db, "uncommon_x", "UNCOMMON", "WORK")
    _add_inv(db, "common_a")
    _add_inv(db, "common_a")


def _setup_craft(db):
    """Two different COMMON WORK items for crafting."""
    _add_def(db, "craft_a", "COMMON", "WORK")
    _add_def(db, "craft_b", "COMMON", "WORK")
    _add_inv(db, "craft_a")
    _add_inv(db, "craft_b")


def test_empty_by_default(client):
    result = client.get("/inventory/crafting-history").json()
    assert result == []


def test_upgrade_inserts_log_row(client, db):
    _setup_upgrade(db)
    r = client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    assert r.status_code == 200
    history = client.get("/inventory/crafting-history").json()
    assert len(history) == 1
    assert history[0]["action"] == "upgrade"


def test_craft_inserts_log_row(client, db):
    _setup_craft(db)
    r = client.post("/inventory/craft", json={"item_id_a": "craft_a", "item_id_b": "craft_b"})
    assert r.status_code == 200
    history = client.get("/inventory/crafting-history").json()
    assert len(history) == 1
    assert history[0]["action"] == "craft"


def test_newest_first_ordering(client, db):
    _setup_upgrade(db)
    _setup_craft(db)
    client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    client.post("/inventory/craft", json={"item_id_a": "craft_a", "item_id_b": "craft_b"})
    history = client.get("/inventory/crafting-history").json()
    assert len(history) == 2
    assert history[0]["happened_at"] >= history[1]["happened_at"]


def test_limit_param(client, db):
    for _ in range(3):
        _setup_upgrade(db)
        client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    history = client.get("/inventory/crafting-history?limit=2").json()
    assert len(history) <= 2


def test_response_shape(client, db):
    _setup_upgrade(db)
    client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    entry = client.get("/inventory/crafting-history").json()[0]
    for key in ("log_id", "action", "source_ids", "result_item_id", "result_rarity", "happened_at"):
        assert key in entry
    assert isinstance(entry["source_ids"], list)


def test_upgrade_result_rarity(client, db):
    _setup_upgrade(db)
    client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    entry = client.get("/inventory/crafting-history").json()[0]
    assert entry["result_rarity"] == "UNCOMMON"


def test_craft_result_item_id_present(client, db):
    _setup_craft(db)
    client.post("/inventory/craft", json={"item_id_a": "craft_a", "item_id_b": "craft_b"})
    entry = client.get("/inventory/crafting-history").json()[0]
    assert entry["result_item_id"] != ""


def test_source_ids_are_list(client, db):
    _setup_upgrade(db)
    client.post("/inventory/upgrade", json={"target_rarity": "UNCOMMON", "category": "WORK"})
    entry = client.get("/inventory/crafting-history").json()[0]
    assert isinstance(entry["source_ids"], list)
    assert len(entry["source_ids"]) == 2
