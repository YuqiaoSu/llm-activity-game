"""Tests for GET /inventory/drop-odds — item drop probability viewer."""
import json
import sqlite3

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


def _seed_item(db, item_id: str, rarity: str, category: str = "WORK") -> None:
    data = json.dumps({
        "item_id": item_id, "name": item_id.replace("_", " ").title(),
        "rarity": rarity, "category": category,
        "icon": "", "effects": [], "drop_requirement": {}, "description": "",
    })
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, data),
    )
    db.commit()


# ── basic shape ───────────────────────────────────────────────────────────────

def test_drop_odds_returns_200(client):
    tc, db = client
    _seed_item(db, "item_a", "COMMON")
    r = tc.get("/inventory/drop-odds?category=WORK")
    assert r.status_code == 200


def test_drop_odds_entry_has_required_keys(client):
    tc, db = client
    _seed_item(db, "item_a", "COMMON")
    r = tc.get("/inventory/drop-odds?category=WORK")
    entry = r.json()[0]
    for key in ("item_id", "name", "rarity", "weight", "probability_pct"):
        assert key in entry


def test_empty_category_returns_empty_list(client):
    tc, _ = client
    r = tc.get("/inventory/drop-odds?category=SLEEP")
    assert r.status_code == 200
    assert r.json() == []


def test_unknown_category_returns_422(client):
    tc, _ = client
    r = tc.get("/inventory/drop-odds?category=BOGUS")
    assert r.status_code == 422


# ── probability correctness ───────────────────────────────────────────────────

def test_probabilities_sum_to_100(client):
    tc, db = client
    _seed_item(db, "item_c", "COMMON")
    _seed_item(db, "item_u", "UNCOMMON")
    _seed_item(db, "item_r", "RARE")
    _seed_item(db, "item_e", "EPIC")
    _seed_item(db, "item_l", "LEGENDARY")
    r = tc.get("/inventory/drop-odds?category=WORK")
    total = sum(e["probability_pct"] for e in r.json())
    assert abs(total - 100.0) < 0.1


def test_common_has_higher_probability_than_legendary(client):
    tc, db = client
    _seed_item(db, "item_c", "COMMON")
    _seed_item(db, "item_l", "LEGENDARY")
    r = tc.get("/inventory/drop-odds?category=WORK")
    entries = {e["rarity"]: e["probability_pct"] for e in r.json()}
    assert entries["COMMON"] > entries["LEGENDARY"]


def test_results_sorted_by_probability_descending(client):
    tc, db = client
    _seed_item(db, "item_c", "COMMON")
    _seed_item(db, "item_u", "UNCOMMON")
    _seed_item(db, "item_r", "RARE")
    r = tc.get("/inventory/drop-odds?category=WORK")
    probs = [e["probability_pct"] for e in r.json()]
    assert probs == sorted(probs, reverse=True)


def test_only_items_in_requested_category_returned(client):
    tc, db = client
    _seed_item(db, "work_item", "COMMON", "WORK")
    _seed_item(db, "game_item", "COMMON", "GAME")
    r = tc.get("/inventory/drop-odds?category=WORK")
    ids = [e["item_id"] for e in r.json()]
    assert "work_item" in ids
    assert "game_item" not in ids


def test_single_item_has_100_pct(client):
    tc, db = client
    _seed_item(db, "solo_item", "RARE")
    r = tc.get("/inventory/drop-odds?category=WORK")
    assert r.json()[0]["probability_pct"] == 100.0
