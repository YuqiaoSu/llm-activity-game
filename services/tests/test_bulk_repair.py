"""Tests for POST /inventory/bulk-repair."""
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
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, durability)"
        " VALUES ('inst1', ?, 'sword_common', '2026-01-01', 'c1', 50)",
        (_PLAYER,),
    )
    conn.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, durability)"
        " VALUES ('inst2', ?, 'shield_rare', '2026-01-01', 'c2', 30)",
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


def test_bulk_repair_repairs_all_worn(client, db):
    r = client.post("/inventory/bulk-repair", json={})
    assert r.status_code == 200
    assert r.json()["repaired_count"] == 2
    rows = db.execute("SELECT instance_id, durability FROM inventory").fetchall()
    assert all(int(row["durability"]) == 100 for row in rows)


def test_bulk_repair_deducts_correct_xp(client, db):
    # COMMON cost=10, RARE cost=40 → total 50
    client.post("/inventory/bulk-repair", json={})
    total_xp = db.execute(
        "SELECT COALESCE(SUM(xp),0) AS x FROM player_category_xp WHERE character_id=?", (_PLAYER,)
    ).fetchone()["x"]
    assert int(total_xp) == 450  # 500 - 50


def test_bulk_repair_rarity_filter(client, db):
    r = client.post("/inventory/bulk-repair", json={"rarity": "COMMON"})
    assert r.status_code == 200
    d = r.json()
    assert d["repaired_count"] == 1
    assert d["total_xp_spent"] == 10
    # Only COMMON repaired; RARE still at 30
    rare_dur = db.execute("SELECT durability FROM inventory WHERE instance_id='inst2'").fetchone()
    assert int(rare_dur["durability"]) == 30


def test_bulk_repair_402_on_insufficient_xp(client, db):
    db.execute("DELETE FROM player_category_xp WHERE character_id=?", (_PLAYER,))
    db.commit()
    r = client.post("/inventory/bulk-repair", json={})
    assert r.status_code == 402


def test_bulk_repair_skips_locked(client, db):
    db.execute("UPDATE inventory SET locked=1 WHERE instance_id='inst1'")
    db.commit()
    r = client.post("/inventory/bulk-repair", json={})
    assert r.status_code == 200
    d = r.json()
    assert d["repaired_count"] == 1
    assert d["skipped_locked"] == 1


def test_bulk_repair_skips_full_durability(client, db):
    db.execute("UPDATE inventory SET durability=100 WHERE instance_id='inst1'")
    db.commit()
    r = client.post("/inventory/bulk-repair", json={})
    d = r.json()
    assert d["repaired_count"] == 1   # only inst2 was worn


def test_bulk_repair_empty_when_all_full(client, db):
    db.execute("UPDATE inventory SET durability=100")
    db.commit()
    r = client.post("/inventory/bulk-repair", json={})
    assert r.status_code == 200
    assert r.json()["repaired_count"] == 0
    assert r.json()["total_xp_spent"] == 0


def test_bulk_repair_400_on_bad_rarity(client):
    r = client.post("/inventory/bulk-repair", json={"rarity": "MYTHIC"})
    assert r.status_code == 400
