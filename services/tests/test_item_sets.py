"""Tests for GET /inventory/sets — item set completion tracker."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Tester", visual),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app = create_app(db=db)
    return TestClient(app), db


def _def(db, item_id: str, rarity: str = "COMMON", set_id: str | None = None) -> None:
    data: dict = {
        "item_id": item_id, "name": item_id.replace("_", " ").title(),
        "rarity": rarity, "category": "WORK",
        "icon": "", "effects": [], "drop_requirement": {}, "description": "",
    }
    if set_id:
        data["set_id"] = set_id
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, json.dumps(data)),
    )
    db.commit()


def _own(db, item_id: str, expires_at: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, expires_at)"
        " VALUES (?, 'player_default', ?, ?, 'chunk_x', ?)",
        (str(uuid.uuid4()), item_id, now, expires_at),
    )
    db.commit()


# ── basic shape ───────────────────────────────────────────────────────────────

def test_sets_empty_when_no_set_items(client):
    tc, db = client
    _def(db, "no_set_item")   # no set_id
    r = tc.get("/inventory/sets")
    assert r.status_code == 200
    assert r.json() == []


def test_sets_returns_set_entry_shape(client):
    tc, db = client
    _def(db, "item_a", set_id="my_set")
    r = tc.get("/inventory/sets")
    entry = r.json()[0]
    for key in ("set_id", "items", "owned_count", "total_count", "complete"):
        assert key in entry
    assert entry["items"][0]["owned"] is False


def test_set_item_shape(client):
    tc, db = client
    _def(db, "item_a", set_id="my_set")
    r = tc.get("/inventory/sets")
    item = r.json()[0]["items"][0]
    for key in ("item_id", "name", "rarity", "owned"):
        assert key in item


# ── ownership tracking ────────────────────────────────────────────────────────

def test_owned_flag_true_when_player_has_item(client):
    tc, db = client
    _def(db, "item_a", set_id="my_set")
    _own(db, "item_a")
    r = tc.get("/inventory/sets")
    item = r.json()[0]["items"][0]
    assert item["owned"] is True


def test_owned_count_and_total_correct(client):
    tc, db = client
    _def(db, "item_a", set_id="s1")
    _def(db, "item_b", set_id="s1")
    _def(db, "item_c", set_id="s1")
    _own(db, "item_a")
    r = tc.get("/inventory/sets")
    s = r.json()[0]
    assert s["total_count"] == 3
    assert s["owned_count"] == 1
    assert s["complete"] is False


def test_complete_true_when_all_owned(client):
    tc, db = client
    _def(db, "item_a", set_id="s1")
    _def(db, "item_b", set_id="s1")
    _own(db, "item_a")
    _own(db, "item_b")
    r = tc.get("/inventory/sets")
    assert r.json()[0]["complete"] is True


def test_expired_item_does_not_count_as_owned(client):
    tc, db = client
    _def(db, "item_a", set_id="s1")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _own(db, "item_a", expires_at=past)
    r = tc.get("/inventory/sets")
    assert r.json()[0]["items"][0]["owned"] is False


# ── multiple sets ─────────────────────────────────────────────────────────────

def test_multiple_sets_returned(client):
    tc, db = client
    _def(db, "item_a", set_id="set_alpha")
    _def(db, "item_b", set_id="set_beta")
    r = tc.get("/inventory/sets")
    set_ids = [s["set_id"] for s in r.json()]
    assert "set_alpha" in set_ids
    assert "set_beta" in set_ids


def test_items_within_set_sorted_by_rarity(client):
    tc, db = client
    _def(db, "leg_item", rarity="LEGENDARY", set_id="s1")
    _def(db, "com_item", rarity="COMMON",    set_id="s1")
    _def(db, "rar_item", rarity="RARE",      set_id="s1")
    r = tc.get("/inventory/sets")
    rarities = [i["rarity"] for i in r.json()[0]["items"]]
    assert rarities == ["COMMON", "RARE", "LEGENDARY"]
