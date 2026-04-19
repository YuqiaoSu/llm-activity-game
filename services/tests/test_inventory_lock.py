"""Tests for item instance lock / unlock."""
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
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES ('inst1', ?, 'sword_common', '2026-01-01', 'chunk1')",
        (_PLAYER,),
    )
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


# ── field presence ─────────────────────────────────────────────────────────────

def test_inventory_has_locked_field(client):
    items = client.get("/inventory").json()
    assert len(items) > 0
    assert "locked" in items[0]


def test_inventory_locked_defaults_false(client):
    items = client.get("/inventory").json()
    assert items[0]["locked"] == 0


# ── lock toggle ────────────────────────────────────────────────────────────────

def test_lock_item(client):
    r = client.patch("/inventory/instances/inst1/lock", json={"locked": True})
    assert r.status_code == 200
    assert r.json()["locked"] is True


def test_unlock_item(client, db):
    db.execute("UPDATE inventory SET locked=1 WHERE instance_id='inst1'")
    db.commit()
    r = client.patch("/inventory/instances/inst1/lock", json={"locked": False})
    assert r.status_code == 200
    assert r.json()["locked"] is False


def test_lock_404_on_unknown(client):
    r = client.patch("/inventory/instances/no_such/lock", json={"locked": True})
    assert r.status_code == 404


# ── sell / discard guard ───────────────────────────────────────────────────────

def test_sell_409_when_locked(client, db):
    db.execute("UPDATE inventory SET locked=1 WHERE instance_id='inst1'")
    db.commit()
    r = client.post("/inventory/instances/inst1/sell")
    assert r.status_code == 409


def test_discard_409_when_locked(client, db):
    db.execute("UPDATE inventory SET locked=1 WHERE instance_id='inst1'")
    db.commit()
    r = client.delete("/inventory/instances/inst1")
    assert r.status_code == 409


def test_bulk_sell_skips_locked(client, db):
    db.execute("UPDATE inventory SET locked=1 WHERE instance_id='inst1'")
    db.commit()
    r = client.post("/inventory/bulk-sell", json={"rarity": "COMMON"})
    assert r.status_code == 200
    assert r.json()["sold_count"] == 0


def test_unlock_allows_sell(client, db):
    db.execute("UPDATE inventory SET locked=1 WHERE instance_id='inst1'")
    db.commit()
    client.patch("/inventory/instances/inst1/lock", json={"locked": False})
    r = client.post("/inventory/instances/inst1/sell")
    assert r.status_code == 200
