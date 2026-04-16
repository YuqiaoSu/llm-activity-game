"""Tests for inventory tooltip fields: description and first_seen_at."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({
        "base_sprite": "x.png", "evolution_stage": 0,
        "skin": None, "accessories": [], "anim_state": "idle",
    })
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("work_totem_rare", json.dumps({
            "item_id": "work_totem_rare",
            "name": "Work Totem",
            "rarity": "RARE",
            "category": "WORK",
            "icon": "work_totem.png",
            "description": "Place this in a slot to earn 30% more XP from WORK activity.",
            "drop_requirement": {},
            "effects": [
                {"effect_type": "category_xp_bonus", "target": "slot",
                 "params": {"category": "WORK", "factor": 1.3}},
            ],
        })),
    )
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES ('inst-1', 'player_default', 'work_totem_rare', ?, 'chunk-1')",
        (now,),
    )
    conn.execute(
        "INSERT INTO collection_log (player_id, item_id, first_seen_at) VALUES (?, ?, ?)",
        ("player_default", "work_totem_rare", "2026-01-15T08:00:00+00:00"),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def test_inventory_returns_description(client):
    resp = client.get("/inventory")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["description"] == "Place this in a slot to earn 30% more XP from WORK activity."


def test_inventory_returns_first_seen_at(client):
    resp = client.get("/inventory")
    assert resp.status_code == 200
    items = resp.json()
    assert items[0]["first_seen_at"] == "2026-01-15T08:00:00+00:00"


def test_inventory_description_empty_string_when_missing(db):
    """Items without a description field should return an empty string."""
    db.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("nodesc_item", json.dumps({
            "item_id": "nodesc_item", "name": "No Desc",
            "rarity": "COMMON", "category": "WORK",
            "icon": "", "drop_requirement": {}, "effects": [],
            # intentionally no "description" key
        })),
    )
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES ('inst-2', 'player_default', 'nodesc_item', ?, 'chunk-2')",
        (now,),
    )
    db.commit()

    client = TestClient(create_app(db=db))
    resp = client.get("/inventory")
    assert resp.status_code == 200
    nodesc = next(i for i in resp.json() if i["item_id"] == "nodesc_item")
    assert nodesc["description"] == ""


def test_inventory_first_seen_at_null_when_not_in_collection_log(db):
    """Items not yet in collection_log should have first_seen_at = null."""
    db.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("unseen_item", json.dumps({
            "item_id": "unseen_item", "name": "Unseen",
            "rarity": "COMMON", "category": "GAME",
            "icon": "", "drop_requirement": {}, "effects": [],
            "description": "A mystery.",
        })),
    )
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES ('inst-3', 'player_default', 'unseen_item', ?, 'chunk-3')",
        (now,),
    )
    db.commit()

    client = TestClient(create_app(db=db))
    resp = client.get("/inventory")
    assert resp.status_code == 200
    unseen = next(i for i in resp.json() if i["item_id"] == "unseen_item")
    assert unseen["first_seen_at"] is None


def test_inventory_effects_parsed_as_list(client):
    """Effects must be returned as a list, not a raw JSON string."""
    resp = client.get("/inventory")
    assert resp.status_code == 200
    items = resp.json()
    effects = items[0]["effects"]
    assert isinstance(effects, list)
    assert len(effects) == 1
    assert effects[0]["effect_type"] == "category_xp_bonus"
    assert effects[0]["params"]["factor"] == pytest.approx(1.3)
