"""Tests for GET /catalogue endpoints."""
from __future__ import annotations

import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db


def _seed_item(conn, item_id: str, name: str, rarity: str, category: str) -> None:
    data = json.dumps({
        "item_id": item_id,
        "name": name,
        "rarity": rarity,
        "category": category,
        "description": f"A {rarity.lower()} {name}",
        "effects": [],
        "icon": "",
        "drop_requirement": {},
    })
    conn.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, data),
    )


def _discover(conn, item_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO collection_log (item_id, player_id, first_seen_at) "
        "VALUES (?, 'player_default', '2026-01-01T00:00:00')",
        (item_id,),
    )


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Seed items across two categories
    _seed_item(conn, "work_common", "Work Widget", "COMMON", "WORK")
    _seed_item(conn, "work_rare", "Work Relic", "RARE", "WORK")
    _seed_item(conn, "game_uncommon", "Game Gem", "UNCOMMON", "GAME")
    _seed_item(conn, "game_epic", "Game Crystal", "EPIC", "GAME")
    # Discover two items
    _discover(conn, "work_common")
    _discover(conn, "game_epic")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    app = create_app(db=db)
    return TestClient(app)


# ── GET /catalogue ────────────────────────────────────────────────────────────

def test_catalogue_returns_all_items(client):
    r = client.get("/catalogue")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 4


def test_catalogue_item_shape(client):
    r = client.get("/catalogue")
    item = next(i for i in r.json() if i["item_id"] == "work_common")
    assert item["name"] == "Work Widget"
    assert item["rarity"] == "COMMON"
    assert item["category"] == "WORK"
    assert "description" in item
    assert "effects" in item
    assert item["discovered"] is True
    assert item["first_seen_at"] is not None


def test_catalogue_undiscovered_flag(client):
    r = client.get("/catalogue")
    item = next(i for i in r.json() if i["item_id"] == "work_rare")
    assert item["discovered"] is False
    assert item["first_seen_at"] is None


def test_catalogue_sorted_by_category_then_rarity(client):
    items = client.get("/catalogue").json()
    # GAME comes before WORK alphabetically; within GAME: UNCOMMON < EPIC
    ids = [i["item_id"] for i in items]
    assert ids.index("game_uncommon") < ids.index("game_epic")
    assert ids.index("game_uncommon") < ids.index("work_common")


# ── GET /catalogue/by-category ───────────────────────────────────────────────

def test_by_category_keys(client):
    r = client.get("/catalogue/by-category")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"WORK", "GAME"}


def test_by_category_item_counts(client):
    data = client.get("/catalogue/by-category").json()
    assert len(data["WORK"]) == 2
    assert len(data["GAME"]) == 2


def test_by_category_sorted_by_rarity(client):
    data = client.get("/catalogue/by-category").json()
    # WORK: COMMON < RARE
    work = data["WORK"]
    assert work[0]["rarity"] == "COMMON"
    assert work[1]["rarity"] == "RARE"
    # GAME: UNCOMMON < EPIC
    game = data["GAME"]
    assert game[0]["rarity"] == "UNCOMMON"
    assert game[1]["rarity"] == "EPIC"


def test_by_category_discovery_flags(client):
    data = client.get("/catalogue/by-category").json()
    work_common = next(i for i in data["WORK"] if i["item_id"] == "work_common")
    assert work_common["discovered"] is True
    work_rare = next(i for i in data["WORK"] if i["item_id"] == "work_rare")
    assert work_rare["discovered"] is False


# ── GET /catalogue/by-category/{category} ────────────────────────────────────

def test_single_category_returns_items(client):
    r = client.get("/catalogue/by-category/WORK")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert all(i["category"] == "WORK" for i in items)


def test_single_category_case_insensitive(client):
    r = client.get("/catalogue/by-category/work")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_single_category_sorted_by_rarity(client):
    items = client.get("/catalogue/by-category/GAME").json()
    assert items[0]["rarity"] == "UNCOMMON"
    assert items[1]["rarity"] == "EPIC"


def test_single_category_404_unknown(client):
    r = client.get("/catalogue/by-category/UNKNOWN_XYZ")
    assert r.status_code == 404
