"""Tests for POST /places/{id}/gift-item."""
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

    for item_id, rarity in [
        ("sword_common", "COMMON"),
        ("shield_rare", "RARE"),
        ("blade_legendary", "LEGENDARY"),
    ]:
        conn.execute(
            "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
            (item_id, json.dumps({"item_id": item_id, "name": item_id,
                                  "rarity": rarity, "category": "WORK",
                                  "description": "", "effects": []})),
        )

    for inst, item in [("inst1", "sword_common"), ("inst2", "shield_rare"),
                       ("inst3", "blade_legendary"), ("inst4", "sword_common")]:
        conn.execute(
            "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
            " VALUES (?, ?, ?, '2026-01-01', 'c1')",
            (inst, _PLAYER, item),
        )

    conn.execute(
        "INSERT INTO places (place_id, name, place_type, state, xp, level, item_pool)"
        " VALUES ('place1', 'Library', 'STUDY', 'UNLOCKED', 0, 1, '{}')"
    )
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, state, xp, level, item_pool)"
        " VALUES ('place_locked', 'Dungeon', 'COMBAT', 'LOCKED', 0, 1, '{}')"
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def test_gift_removes_item(client, db):
    client.post("/places/place1/gift-item", json={"instance_id": "inst1"})
    row = db.execute("SELECT 1 FROM inventory WHERE instance_id='inst1'").fetchone()
    assert row is None


def test_gift_awards_xp_common(client, db):
    r = client.post("/places/place1/gift-item", json={"instance_id": "inst1"})
    assert r.status_code == 200
    assert r.json()["xp_gained"] == 5


def test_gift_awards_xp_rare(client, db):
    r = client.post("/places/place1/gift-item", json={"instance_id": "inst2"})
    assert r.status_code == 200
    assert r.json()["xp_gained"] == 30


def test_gift_awards_xp_legendary(client, db):
    r = client.post("/places/place1/gift-item", json={"instance_id": "inst3"})
    assert r.status_code == 200
    assert r.json()["xp_gained"] == 100


def test_gift_increments_place_xp(client, db):
    client.post("/places/place1/gift-item", json={"instance_id": "inst1"})
    xp = db.execute("SELECT xp FROM places WHERE place_id='place1'").fetchone()["xp"]
    assert int(xp) == 5


def test_gift_404_on_unknown_place(client):
    r = client.post("/places/no_such/gift-item", json={"instance_id": "inst1"})
    assert r.status_code == 404


def test_gift_404_on_unknown_instance(client):
    r = client.post("/places/place1/gift-item", json={"instance_id": "no_inst"})
    assert r.status_code == 404


def test_gift_409_on_locked_instance(client, db):
    db.execute("UPDATE inventory SET locked=1 WHERE instance_id='inst1'")
    db.commit()
    r = client.post("/places/place1/gift-item", json={"instance_id": "inst1"})
    assert r.status_code == 409


def test_gift_409_on_locked_place(client):
    r = client.post("/places/place_locked/gift-item", json={"instance_id": "inst1"})
    assert r.status_code == 409


def test_gift_second_call_fails(client, db):
    client.post("/places/place1/gift-item", json={"instance_id": "inst1"})
    r = client.post("/places/place1/gift-item", json={"instance_id": "inst1"})
    assert r.status_code == 404


def test_gift_logs_activity(client, db):
    client.post("/places/place1/gift-item", json={"instance_id": "inst1"})
    row = db.execute(
        "SELECT action, amount FROM place_activity_log WHERE place_id='place1'"
    ).fetchone()
    assert row["action"] == "gift_item"
    assert int(row["amount"]) == 5
