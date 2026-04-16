"""Tests for NPC trade post endpoints."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.seeds.trade import seed_trade_offers
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


def _add_item(db, item_id: str, rarity: str, category: str = "focus") -> None:
    data = json.dumps({"name": item_id, "rarity": rarity, "category": category,
                       "description": "", "effects": []})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?,?)",
               (item_id, data))
    db.commit()


def _add_instance(db, instance_id: str, item_id: str, placed_in: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, placed_in) "
        "VALUES (?,?,?,?,?,?)",
        (instance_id, "player_default", item_id, now, "test", placed_in),
    )
    db.commit()


def _seed_simple_offer(db, offer_id: str = "test_offer",
                       from_rarity: str = "COMMON", from_qty: int = 3,
                       to_rarity: str = "UNCOMMON") -> None:
    db.execute(
        "INSERT OR IGNORE INTO trade_offers "
        "(offer_id, trader_name, label, from_rarity, from_qty, from_category, to_rarity, to_qty, to_category) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (offer_id, "TestTrader", "3×COMMON→1×UNCOMMON",
         from_rarity, from_qty, None, to_rarity, 1, None),
    )
    db.commit()


# ── seed helper tests ─────────────────────────────────────────────────────────

def test_seed_inserts_offers(db):
    n = seed_trade_offers(db)
    assert n == 5


def test_seed_is_idempotent(db):
    seed_trade_offers(db)
    n2 = seed_trade_offers(db)
    assert n2 == 0  # already inserted; OR IGNORE returns 0


# ── GET /trade/offers ─────────────────────────────────────────────────────────

def test_get_offers_empty(client, db):
    data = client.get("/trade/offers").json()
    assert data == []


def test_get_offers_returns_seeded(client, db):
    seed_trade_offers(db)
    data = client.get("/trade/offers").json()
    assert len(data) == 5


def test_get_offers_have_qty_zero_when_no_inventory(client, db):
    _seed_simple_offer(db)
    data = client.get("/trade/offers").json()
    assert data[0]["have_qty"] == 0
    assert data[0]["have_enough"] is False


def test_get_offers_have_qty_counts_unplaced(client, db):
    _seed_simple_offer(db, from_rarity="COMMON", from_qty=3)
    _add_item(db, "common_book", "COMMON")
    for i in range(3):
        _add_instance(db, f"inst_{i}", "common_book")
    data = client.get("/trade/offers").json()
    assert data[0]["have_qty"] == 3
    assert data[0]["have_enough"] is True


def test_get_offers_placed_items_not_counted(client, db):
    _seed_simple_offer(db, from_rarity="COMMON", from_qty=2)
    _add_item(db, "common_book", "COMMON")
    _add_instance(db, "placed_inst", "common_book", placed_in="some_slot")
    _add_instance(db, "free_inst", "common_book")
    data = client.get("/trade/offers").json()
    assert data[0]["have_qty"] == 1
    assert data[0]["have_enough"] is False


# ── POST /trade/accept ────────────────────────────────────────────────────────

def test_accept_trade_not_found(client, db):
    resp = client.post("/trade/accept", json={"offer_id": "nonexistent"})
    assert resp.status_code == 404


def test_accept_trade_not_enough_items(client, db):
    _seed_simple_offer(db, from_rarity="COMMON", from_qty=3)
    _add_item(db, "common_book", "COMMON")
    _add_instance(db, "inst_0", "common_book")
    resp = client.post("/trade/accept", json={"offer_id": "test_offer"})
    assert resp.status_code == 400
    assert "need 3" in resp.json()["detail"]


def test_accept_trade_consumes_source_items(client, db):
    _seed_simple_offer(db, from_rarity="COMMON", from_qty=3, to_rarity="UNCOMMON")
    _add_item(db, "common_book", "COMMON")
    _add_item(db, "uncommon_scroll", "UNCOMMON")
    for i in range(3):
        _add_instance(db, f"src_{i}", "common_book")
    client.post("/trade/accept", json={"offer_id": "test_offer"})
    remaining = db.execute(
        "SELECT COUNT(*) FROM inventory WHERE character_id='player_default' AND item_id='common_book'"
    ).fetchone()[0]
    assert remaining == 0


def test_accept_trade_grants_output_item(client, db):
    _seed_simple_offer(db, from_rarity="COMMON", from_qty=3, to_rarity="UNCOMMON")
    _add_item(db, "common_book", "COMMON")
    _add_item(db, "uncommon_scroll", "UNCOMMON")
    for i in range(3):
        _add_instance(db, f"src_{i}", "common_book")
    resp = client.post("/trade/accept", json={"offer_id": "test_offer"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["granted"]) == 1
    assert data["granted"][0]["item_id"] == "uncommon_scroll"


def test_accept_trade_response_shape(client, db):
    _seed_simple_offer(db, from_rarity="COMMON", from_qty=3, to_rarity="UNCOMMON")
    _add_item(db, "common_book", "COMMON")
    _add_item(db, "uncommon_scroll", "UNCOMMON")
    for i in range(3):
        _add_instance(db, f"src_{i}", "common_book")
    data = client.post("/trade/accept", json={"offer_id": "test_offer"}).json()
    assert "offer_id" in data
    assert "consumed" in data
    assert "granted" in data
    assert "traded_at" in data
    assert len(data["consumed"]) == 3


def test_accept_trade_no_target_item_raises_400(client, db):
    _seed_simple_offer(db, from_rarity="COMMON", from_qty=2, to_rarity="LEGENDARY")
    _add_item(db, "common_book", "COMMON")
    for i in range(2):
        _add_instance(db, f"src_{i}", "common_book")
    # No LEGENDARY items in catalogue
    resp = client.post("/trade/accept", json={"offer_id": "test_offer"})
    assert resp.status_code == 400
    assert "rarity LEGENDARY" in resp.json()["detail"]
