"""Tests for item wishlist API endpoints and drop notification enrichment."""
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
    init_db(conn)
    # Seed two item definitions for use in tests
    for item_id, category in [("item_a", "WORK"), ("item_b", "GAME")]:
        data = json.dumps({
            "name": item_id.upper(), "rarity": "COMMON",
            "category": category, "description": "", "effects": [],
        })
        conn.execute(
            "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
            (item_id, data),
        )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app = create_app(db=db)
    return TestClient(app), db


# ── GET /catalogue includes wishlisted field ─────────────────────────────────

def test_catalogue_includes_wishlisted_false_by_default(client):
    tc, _ = client
    r = tc.get("/catalogue")
    assert r.status_code == 200
    item = r.json()[0]
    assert "wishlisted" in item
    assert item["wishlisted"] is False


def test_catalogue_reflects_wishlisted_true(client):
    tc, _ = client
    tc.post("/catalogue/item_a/wishlist")
    r = tc.get("/catalogue")
    by_id = {i["item_id"]: i for i in r.json()}
    assert by_id["item_a"]["wishlisted"] is True
    assert by_id["item_b"]["wishlisted"] is False


# ── GET /catalogue/wishlist ──────────────────────────────────────────────────

def test_get_wishlist_empty_by_default(client):
    tc, _ = client
    r = tc.get("/catalogue/wishlist")
    assert r.status_code == 200
    assert r.json() == []


def test_get_wishlist_returns_wishlisted_items(client):
    tc, _ = client
    tc.post("/catalogue/item_a/wishlist")
    r = tc.get("/catalogue/wishlist")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["item_id"] == "item_a"
    assert data[0]["wishlisted"] is True


# ── POST /catalogue/{id}/wishlist ────────────────────────────────────────────

def test_wishlist_nonexistent_item_returns_404(client):
    tc, _ = client
    r = tc.post("/catalogue/does_not_exist/wishlist")
    assert r.status_code == 404


def test_wishlist_already_wishlisted_returns_409(client):
    tc, _ = client
    tc.post("/catalogue/item_a/wishlist")
    r = tc.post("/catalogue/item_a/wishlist")
    assert r.status_code == 409


def test_wishlist_success_response_shape(client):
    tc, _ = client
    r = tc.post("/catalogue/item_a/wishlist")
    assert r.status_code == 200
    data = r.json()
    assert data["item_id"] == "item_a"
    assert data["wishlisted"] is True
    assert "added_at" in data


# ── DELETE /catalogue/{id}/wishlist ─────────────────────────────────────────

def test_unwishlist_not_wishlisted_returns_404(client):
    tc, _ = client
    r = tc.delete("/catalogue/item_a/wishlist")
    assert r.status_code == 404


def test_unwishlist_success_response(client):
    tc, _ = client
    tc.post("/catalogue/item_a/wishlist")
    r = tc.delete("/catalogue/item_a/wishlist")
    assert r.status_code == 200
    assert r.json()["wishlisted"] is False


def test_unwishlist_removes_from_wishlist_endpoint(client):
    tc, _ = client
    tc.post("/catalogue/item_a/wishlist")
    tc.delete("/catalogue/item_a/wishlist")
    r = tc.get("/catalogue/wishlist")
    assert r.json() == []


# ── Drop notification enrichment ─────────────────────────────────────────────

def test_drop_notification_includes_wishlisted_false_by_default(db):
    from services.models.item import ItemDefinition
    from services.models.enums import Rarity, Category
    from services.reward_ledger.ledger import record_drop

    from services.models.item import DropRequirement
    item = ItemDefinition(
        item_id="item_a", name="ITEM_A",
        rarity=Rarity.COMMON, category=Category.WORK,
        description="", effects=[], icon="",
        drop_requirement=DropRequirement(),
    )
    record_drop(db, "chunk_1", 0, item, "player_default")

    row = db.execute(
        "SELECT payload FROM pending_notifications WHERE event_type='item_drop'"
    ).fetchone()
    payload = json.loads(row["payload"])
    assert payload["wishlisted"] is False


def test_drop_notification_includes_wishlisted_true_when_on_wishlist(db):
    from services.models.item import ItemDefinition
    from services.models.enums import Rarity, Category
    from services.reward_ledger.ledger import record_drop

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO wishlist (player_id, item_id, added_at) VALUES ('player_default', 'item_a', ?)",
        (now,),
    )
    db.commit()

    from services.models.item import DropRequirement
    item = ItemDefinition(
        item_id="item_a", name="ITEM_A",
        rarity=Rarity.COMMON, category=Category.WORK,
        description="", effects=[], icon="",
        drop_requirement=DropRequirement(),
    )
    record_drop(db, "chunk_2", 0, item, "player_default")

    row = db.execute(
        "SELECT payload FROM pending_notifications WHERE event_type='item_drop'"
    ).fetchone()
    payload = json.loads(row["payload"])
    assert payload["wishlisted"] is True
