"""Tests for POST /inventory/craft — combine two items of the same category."""
from __future__ import annotations

import json
import sqlite3
import uuid

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
    visual = json.dumps({
        "base_sprite": "x.png", "evolution_stage": 0,
        "skin": None, "accessories": [], "anim_state": "idle",
    })
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.commit()
    yield conn
    conn.close()


def _add_def(db, item_id: str, category: str, rarity: str) -> None:
    data = json.dumps({"name": item_id, "category": category, "rarity": rarity, "description": "", "effects": []})
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, data),
    )
    db.commit()


def _add_inv(db, item_id: str, instance_id: str | None = None, placed_in: str | None = None) -> str:
    iid = instance_id or str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, placed_in) "
        "VALUES (?, 'player_default', ?, DATETIME('now'), 'chunk-1', ?)",
        (iid, item_id, placed_in),
    )
    db.commit()
    return iid


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


# ── validation errors ─────────────────────────────────────────────────────────

def test_same_item_id_returns_400(client):
    resp = client.post("/inventory/craft", json={"item_id_a": "x", "item_id_b": "x"})
    assert resp.status_code == 400
    assert "different" in resp.json()["detail"].lower()


def test_item_a_not_found_returns_404(db, client):
    _add_def(db, "item_b", "focus", "COMMON")
    _add_inv(db, "item_b")
    resp = client.post("/inventory/craft", json={"item_id_a": "no_such", "item_id_b": "item_b"})
    assert resp.status_code == 404


def test_item_b_not_found_returns_404(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_inv(db, "item_a")
    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "no_such"})
    assert resp.status_code == 404


def test_category_mismatch_returns_400(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "rest", "COMMON")
    _add_inv(db, "item_a")
    _add_inv(db, "item_b")
    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    assert resp.status_code == 400
    assert "category" in resp.json()["detail"].lower()


def test_no_unplaced_copy_a_returns_400(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_def(db, "item_c", "focus", "COMMON")
    # item_a is placed
    _add_inv(db, "item_a", placed_in="place_1")
    _add_inv(db, "item_b")
    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    assert resp.status_code == 400
    assert "item_a" in resp.json()["detail"]


def test_no_unplaced_copy_b_returns_400(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_def(db, "item_c", "focus", "COMMON")
    _add_inv(db, "item_a")
    _add_inv(db, "item_b", placed_in="place_1")
    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    assert resp.status_code == 400
    assert "item_b" in resp.json()["detail"]


# ── successful craft ──────────────────────────────────────────────────────────

def test_craft_returns_200_with_expected_fields(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_def(db, "item_c", "focus", "COMMON")
    inst_a = _add_inv(db, "item_a")
    inst_b = _add_inv(db, "item_b")

    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    assert resp.status_code == 200
    body = resp.json()
    assert "new_instance_id" in body
    assert "new_item_id" in body
    assert "new_rarity" in body
    assert body["new_category"] == "focus"
    assert set(body["consumed_instance_ids"]) == {inst_a, inst_b}
    assert set(body["crafted_from"]) == {"item_a", "item_b"}


def test_craft_consumes_input_instances(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_def(db, "item_c", "focus", "COMMON")
    inst_a = _add_inv(db, "item_a")
    inst_b = _add_inv(db, "item_b")

    client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})

    row_a = db.execute("SELECT * FROM inventory WHERE instance_id=?", (inst_a,)).fetchone()
    row_b = db.execute("SELECT * FROM inventory WHERE instance_id=?", (inst_b,)).fetchone()
    assert row_a is None
    assert row_b is None


def test_craft_inserts_new_instance_into_inventory(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_def(db, "item_c", "focus", "COMMON")
    _add_inv(db, "item_a")
    _add_inv(db, "item_b")

    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    new_iid = resp.json()["new_instance_id"]
    row = db.execute("SELECT * FROM inventory WHERE instance_id=?", (new_iid,)).fetchone()
    assert row is not None
    assert row["source_chunk"] == "craft"


def test_craft_result_rarity_is_max_of_inputs(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "RARE")
    _add_def(db, "item_c", "focus", "RARE")  # result candidate
    _add_inv(db, "item_a")
    _add_inv(db, "item_b")

    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    assert resp.json()["new_rarity"] == "RARE"


def test_craft_result_excluded_from_inputs_when_alternatives_exist(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_def(db, "item_c", "focus", "COMMON")  # the only alternative
    _add_inv(db, "item_a")
    _add_inv(db, "item_b")

    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    assert resp.json()["new_item_id"] == "item_c"


def test_craft_falls_back_to_inputs_when_no_other_candidates(db, client):
    """When no third item exists at the result rarity, inputs themselves are valid results."""
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_inv(db, "item_a")
    _add_inv(db, "item_b")

    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    assert resp.status_code == 200
    assert resp.json()["new_item_id"] in ("item_a", "item_b")


def test_craft_stamps_collection_log(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_def(db, "item_c", "focus", "COMMON")
    _add_inv(db, "item_a")
    _add_inv(db, "item_b")

    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    new_item_id = resp.json()["new_item_id"]
    row = db.execute(
        "SELECT * FROM collection_log WHERE player_id='player_default' AND item_id=?",
        (new_item_id,),
    ).fetchone()
    assert row is not None


def test_craft_new_item_data_returned(db, client):
    _add_def(db, "item_a", "focus", "COMMON")
    _add_def(db, "item_b", "focus", "COMMON")
    _add_def(db, "item_c", "focus", "COMMON")
    _add_inv(db, "item_a")
    _add_inv(db, "item_b")

    resp = client.post("/inventory/craft", json={"item_id_a": "item_a", "item_id_b": "item_b"})
    body = resp.json()
    assert isinstance(body["new_item"], dict)
    assert body["new_item"].get("category") == "focus"
