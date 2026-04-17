"""Tests for GET /inventory/recipes endpoint."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
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
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default','T',?)",
        (visual,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def _add_item_def(db, item_id: str, rarity: str, category: str = "focus") -> None:
    data = json.dumps({"name": item_id, "rarity": rarity, "category": category,
                       "description": "", "effects": []})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?,?)",
               (item_id, data))
    db.commit()


def _add_instance(db, item_id: str, placed_in: str | None = None) -> str:
    iid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, placed_in) "
        "VALUES (?,?,?,?,?,?)",
        (iid, "player_default", item_id, now, "test", placed_in),
    )
    db.commit()
    return iid


# ── tests ─────────────────────────────────────────────────────────────────────

def test_recipes_empty_inventory(client, db):
    resp = client.get("/inventory/recipes")
    assert resp.status_code == 200
    assert resp.json() == []


def test_recipes_single_item_cant_craft(client, db):
    _add_item_def(db, "book_a", "COMMON", "focus")
    _add_instance(db, "book_a")
    data = client.get("/inventory/recipes").json()
    assert len(data) == 1
    assert data[0]["can_craft"] is False
    assert data[0]["have_item_types"] == 1


def test_recipes_two_types_can_craft(client, db):
    _add_item_def(db, "book_a", "COMMON", "focus")
    _add_item_def(db, "book_b", "COMMON", "focus")
    _add_instance(db, "book_a")
    _add_instance(db, "book_b")
    data = client.get("/inventory/recipes").json()
    assert len(data) == 1
    rec = data[0]
    assert rec["can_craft"] is True
    assert rec["have_item_types"] == 2
    assert rec["from_rarity"] == "COMMON"
    assert rec["to_rarity"] == "UNCOMMON"
    assert rec["from_qty"] == 2


def test_recipes_legendary_has_no_upgrade(client, db):
    _add_item_def(db, "legend_a", "LEGENDARY", "focus")
    _add_item_def(db, "legend_b", "LEGENDARY", "focus")
    _add_instance(db, "legend_a")
    _add_instance(db, "legend_b")
    data = client.get("/inventory/recipes").json()
    assert len(data) == 1
    assert data[0]["to_rarity"] is None


def test_recipes_placed_items_not_counted(client, db):
    _add_item_def(db, "book_a", "COMMON", "focus")
    _add_item_def(db, "book_b", "COMMON", "focus")
    _add_instance(db, "book_a", placed_in="some_slot")
    _add_instance(db, "book_b")
    data = client.get("/inventory/recipes").json()
    # Only book_b is unplaced → 1 type, can't craft
    assert data[0]["can_craft"] is False
    assert data[0]["have_item_types"] == 1


def test_recipes_groups_by_category(client, db):
    _add_item_def(db, "focus_a", "COMMON", "focus")
    _add_item_def(db, "work_a",  "COMMON", "productivity")
    _add_instance(db, "focus_a")
    _add_instance(db, "work_a")
    data = client.get("/inventory/recipes").json()
    categories = {r["category"] for r in data}
    assert "focus" in categories
    assert "productivity" in categories


def test_recipes_rarity_progression(client, db):
    rarities = ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    expected_to = ["UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
    for i, (r, nxt) in enumerate(zip(rarities, expected_to)):
        iid_a = f"item_{r.lower()}_a"
        iid_b = f"item_{r.lower()}_b"
        _add_item_def(db, iid_a, r, "focus")
        _add_item_def(db, iid_b, r, "focus")
        _add_instance(db, iid_a)
        _add_instance(db, iid_b)
    data = client.get("/inventory/recipes").json()
    recipe_map = {r["from_rarity"]: r["to_rarity"] for r in data if r["category"] == "focus"}
    for r, nxt in zip(rarities, expected_to):
        assert recipe_map[r] == nxt


def test_recipes_entry_shape(client, db):
    _add_item_def(db, "book_a", "COMMON", "focus")
    _add_instance(db, "book_a")
    rec = client.get("/inventory/recipes").json()[0]
    for key in ("category", "from_rarity", "to_rarity", "from_qty", "have_item_types", "can_craft", "item_ids"):
        assert key in rec


def test_recipes_item_ids_lists_available_types(client, db):
    _add_item_def(db, "book_a", "COMMON", "focus")
    _add_item_def(db, "book_b", "COMMON", "focus")
    _add_instance(db, "book_a")
    _add_instance(db, "book_b")
    data = client.get("/inventory/recipes").json()
    assert len(data) == 1
    item_ids = data[0]["item_ids"]
    assert isinstance(item_ids, list)
    assert set(item_ids) == {"book_a", "book_b"}


def test_recipes_item_ids_excludes_placed(client, db):
    _add_item_def(db, "book_a", "COMMON", "focus")
    _add_item_def(db, "book_b", "COMMON", "focus")
    _add_instance(db, "book_a", placed_in="slot_x")
    _add_instance(db, "book_b")
    data = client.get("/inventory/recipes").json()
    assert len(data) == 1
    item_ids = data[0]["item_ids"]
    assert "book_b" in item_ids
    assert "book_a" not in item_ids
