"""Tests for POST /inventory/fuse (item fusion system)."""
import json
import uuid
import sqlite3
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    # Seed item defs: one COMMON, one UNCOMMON, one LEGENDARY
    for item_id, rarity in [
        ("sword_common", "COMMON"),
        ("shield_uncommon", "UNCOMMON"),
        ("crown_legendary", "LEGENDARY"),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
            (item_id, json.dumps({
                "item_id": item_id, "name": item_id, "rarity": rarity,
                "category": "WORK", "icon": "x.png", "effects": [],
                "drop_requirement": {}, "description": "", "stackable": False,
            })),
        )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _add_instances(db, item_id: str, count: int, placed_in=None, equipped=0) -> list[str]:
    ids = []
    for _ in range(count):
        iid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, placed_in, equipped) "
            "VALUES (?, 'player_default', ?, '2026-01-01', 'drop', ?, ?)",
            (iid, item_id, placed_in, equipped),
        )
        ids.append(iid)
    db.commit()
    return ids


# ── success path ─────────────────────────────────────────────────────────────

def test_fuse_success_returns_200(client, db):
    _add_instances(db, "sword_common", 3)
    resp = client.post("/inventory/fuse", json={"item_id": "sword_common"})
    assert resp.status_code == 200


def test_fuse_result_is_next_rarity(client, db):
    _add_instances(db, "sword_common", 3)
    data = client.post("/inventory/fuse", json={"item_id": "sword_common"}).json()
    assert data["fused_from_rarity"] == "COMMON"
    assert data["new_rarity"] == "UNCOMMON"


def test_fuse_consumes_three_instances(client, db):
    ids = _add_instances(db, "sword_common", 3)
    client.post("/inventory/fuse", json={"item_id": "sword_common"})
    # All three consumed instances should be gone from inventory
    for iid in ids:
        row = db.execute("SELECT 1 FROM inventory WHERE instance_id=?", (iid,)).fetchone()
        assert row is None


def test_fuse_adds_one_new_instance(client, db):
    _add_instances(db, "sword_common", 3)
    data = client.post("/inventory/fuse", json={"item_id": "sword_common"}).json()
    new_iid = data["new_instance_id"]
    row = db.execute("SELECT * FROM inventory WHERE instance_id=?", (new_iid,)).fetchone()
    assert row is not None
    assert row["character_id"] == "player_default"


def test_fuse_returns_consumed_ids(client, db):
    ids = set(_add_instances(db, "sword_common", 3))
    data = client.post("/inventory/fuse", json={"item_id": "sword_common"}).json()
    assert set(data["consumed_instance_ids"]) == ids


def test_fuse_stamps_collection_log(client, db):
    _add_instances(db, "sword_common", 3)
    data = client.post("/inventory/fuse", json={"item_id": "sword_common"}).json()
    new_item_id = data["new_item_id"]
    row = db.execute(
        "SELECT 1 FROM collection_log WHERE player_id='player_default' AND item_id=?",
        (new_item_id,),
    ).fetchone()
    assert row is not None


def test_fuse_with_extra_copies_only_consumes_three(client, db):
    _add_instances(db, "sword_common", 5)
    client.post("/inventory/fuse", json={"item_id": "sword_common"})
    remaining = db.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE item_id='sword_common'",
    ).fetchone()["n"]
    assert remaining == 2   # 5 − 3 consumed = 2 left, plus 1 new UNCOMMON


def test_fuse_prefers_unequipped_over_equipped(client, db):
    equipped_ids = _add_instances(db, "sword_common", 2, equipped=1)
    unequipped_id = _add_instances(db, "sword_common", 1, equipped=0)[0]
    data = client.post("/inventory/fuse", json={"item_id": "sword_common"}).json()
    consumed = data["consumed_instance_ids"]
    # The unequipped instance should be consumed
    assert unequipped_id in consumed


# ── error paths ───────────────────────────────────────────────────────────────

def test_fuse_400_when_not_enough_copies(client, db):
    _add_instances(db, "sword_common", 2)   # only 2, need 3
    resp = client.post("/inventory/fuse", json={"item_id": "sword_common"})
    assert resp.status_code == 400


def test_fuse_400_when_all_copies_placed(client, db):
    _add_instances(db, "sword_common", 3, placed_in="slot_x")   # all placed
    resp = client.post("/inventory/fuse", json={"item_id": "sword_common"})
    assert resp.status_code == 400
    assert "unplaced" in resp.json()["detail"].lower()


def test_fuse_400_for_legendary(client, db):
    _add_instances(db, "crown_legendary", 3)
    resp = client.post("/inventory/fuse", json={"item_id": "crown_legendary"})
    assert resp.status_code == 400
    assert "legendary" in resp.json()["detail"].lower()


def test_fuse_404_for_unknown_item(client, db):
    resp = client.post("/inventory/fuse", json={"item_id": "nonexistent_item"})
    assert resp.status_code == 404
