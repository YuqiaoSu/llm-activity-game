"""Tests for item durability / wear system."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db


_PLAYER = "player_default"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', ?)",
        (_PLAYER, visual),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("sword_common", json.dumps({"item_id": "sword_common", "name": "Sword",
                                     "rarity": "COMMON", "category": "WORK",
                                     "description": "", "effects": []})),
    )
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("shield_rare", json.dumps({"item_id": "shield_rare", "name": "Shield",
                                    "rarity": "RARE", "category": "WORK",
                                    "description": "", "effects": []})),
    )
    conn.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES ('inst1', ?, 'sword_common', '2026-01-01', 'chunk1')",
        (_PLAYER,),
    )
    conn.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES ('inst2', ?, 'shield_rare', '2026-01-01', 'chunk2')",
        (_PLAYER,),
    )
    # Give player plenty of XP for repair tests
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 500)",
        (_PLAYER,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── GET /inventory returns durability ─────────────────────────────────────────

def test_inventory_has_durability_field(client):
    r = client.get("/inventory")
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    for item in items:
        assert "durability" in item


def test_inventory_durability_defaults_to_100(client):
    items = client.get("/inventory").json()
    for item in items:
        assert item["durability"] == 100


# ── repair endpoint ────────────────────────────────────────────────────────────

def test_repair_409_when_full_durability(client):
    r = client.post("/inventory/instances/inst1/repair")
    assert r.status_code == 409


def test_repair_restores_to_100(client, db):
    db.execute("UPDATE inventory SET durability=50 WHERE instance_id='inst1'")
    db.commit()
    r = client.post("/inventory/instances/inst1/repair")
    assert r.status_code == 200
    assert r.json()["durability"] == 100


def test_repair_costs_xp_common(client, db):
    db.execute("UPDATE inventory SET durability=50 WHERE instance_id='inst1'")
    db.commit()
    client.post("/inventory/instances/inst1/repair")
    row = db.execute(
        "SELECT COALESCE(SUM(xp),0) AS total FROM player_category_xp WHERE character_id=?",
        (_PLAYER,),
    ).fetchone()
    assert int(row["total"]) == 490   # 500 - 10 (COMMON cost)


def test_repair_costs_xp_rare(client, db):
    db.execute("UPDATE inventory SET durability=50 WHERE instance_id='inst2'")
    db.commit()
    client.post("/inventory/instances/inst2/repair")
    row = db.execute(
        "SELECT COALESCE(SUM(xp),0) AS total FROM player_category_xp WHERE character_id=?",
        (_PLAYER,),
    ).fetchone()
    assert int(row["total"]) == 460   # 500 - 40 (RARE cost)


def test_repair_402_on_insufficient_xp(client, db):
    db.execute("UPDATE inventory SET durability=50 WHERE instance_id='inst1'")
    db.execute("DELETE FROM player_category_xp WHERE character_id=?", (_PLAYER,))
    db.commit()
    r = client.post("/inventory/instances/inst1/repair")
    assert r.status_code == 402


def test_repair_404_on_unknown_instance(client):
    r = client.post("/inventory/instances/no_such_instance/repair")
    assert r.status_code == 404


# ── slot-assign decrements durability ─────────────────────────────────────────

def test_slot_assign_decrements_durability(client, db):
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level)"
        " VALUES ('lab', 'Lab', 'STUDY', '', 'UNLOCKED', '{}', 0, 1)"
    )
    db.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type) VALUES ('s1', 'lab', 'ITEM')"
    )
    db.commit()
    client.put("/places/lab/slots/s1", json={"instance_id": "inst1"})
    row = db.execute("SELECT durability FROM inventory WHERE instance_id='inst1'").fetchone()
    assert int(row["durability"]) == 90   # 100 - 10


def test_durability_floor_is_zero(client, db):
    db.execute("UPDATE inventory SET durability=5 WHERE instance_id='inst1'")
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level)"
        " VALUES ('lab2', 'Lab2', 'STUDY', '', 'UNLOCKED', '{}', 0, 1)"
    )
    db.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type) VALUES ('s2', 'lab2', 'ITEM')"
    )
    db.commit()
    client.put("/places/lab2/slots/s2", json={"instance_id": "inst1"})
    row = db.execute("SELECT durability FROM inventory WHERE instance_id='inst1'").fetchone()
    assert int(row["durability"]) == 0
