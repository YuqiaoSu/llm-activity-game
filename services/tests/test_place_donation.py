"""Tests for place item donation / place perk system."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.place_service.effects import load_place_perks
from services.storage.db import init_db
from services.sync_agent.agent import SyncAgent
from services.sync_agent.rate_limiter import RateLimiter
from services.sync_agent.tracker_client import TrackerClient


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
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def _make_place(db, place_id: str, level: int = 5, state: str = "UNLOCKED") -> None:
    db.execute(
        "INSERT OR IGNORE INTO places "
        "(place_id, name, place_type, description, state, item_pool, level) "
        "VALUES (?,?,?,?,?,?,?)",
        (place_id, "Library", "study", "", state, '{"rarities":[]}', level),
    )
    db.commit()


def _make_item(db, item_id: str, rarity: str = "RARE") -> None:
    data = json.dumps({"name": item_id, "category": "focus",
                       "rarity": rarity, "description": "", "effects": []})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?,?)",
               (item_id, data))
    db.commit()


def _make_instance(db, instance_id: str, item_id: str, placed_in: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, placed_in) "
        "VALUES (?,?,?,?,?,?)",
        (instance_id, "player_default", item_id, now, "test_chunk", placed_in),
    )
    db.commit()


# ── success path ──────────────────────────────────────────────────────────────

def test_donate_creates_perk(client, db):
    _make_place(db, "place1", level=5)
    _make_item(db, "book_rare")
    _make_instance(db, "inst1", "book_rare")

    resp = client.post("/places/place1/donate", json={"instance_id": "inst1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["place_id"] == "place1"
    assert data["item_id"] == "book_rare"
    assert data["boost_factor"] == pytest.approx(0.10)


def test_donate_removes_item_from_inventory(client, db):
    _make_place(db, "place1", level=5)
    _make_item(db, "book_rare")
    _make_instance(db, "inst1", "book_rare")

    client.post("/places/place1/donate", json={"instance_id": "inst1"})
    row = db.execute("SELECT * FROM inventory WHERE instance_id='inst1'").fetchone()
    assert row is None


def test_donate_inserts_perk_row(client, db):
    _make_place(db, "place1", level=5)
    _make_item(db, "book_rare")
    _make_instance(db, "inst1", "book_rare")

    client.post("/places/place1/donate", json={"instance_id": "inst1"})
    row = db.execute(
        "SELECT * FROM place_perks WHERE place_id='place1' AND item_id='book_rare'"
    ).fetchone()
    assert row is not None
    assert float(row["boost_factor"]) == pytest.approx(0.10)


# ── validation errors ─────────────────────────────────────────────────────────

def test_donate_place_not_found(client, db):
    _make_item(db, "book_rare")
    _make_instance(db, "inst1", "book_rare")
    resp = client.post("/places/nonexistent/donate", json={"instance_id": "inst1"})
    assert resp.status_code == 404


def test_donate_place_locked(client, db):
    _make_place(db, "place1", level=5, state="LOCKED")
    _make_item(db, "book_rare")
    _make_instance(db, "inst1", "book_rare")
    resp = client.post("/places/place1/donate", json={"instance_id": "inst1"})
    assert resp.status_code == 400


def test_donate_place_below_level_5(client, db):
    _make_place(db, "place1", level=4)
    _make_item(db, "book_rare")
    _make_instance(db, "inst1", "book_rare")
    resp = client.post("/places/place1/donate", json={"instance_id": "inst1"})
    assert resp.status_code == 400
    assert "level" in resp.json()["detail"].lower()


def test_donate_item_not_found(client, db):
    _make_place(db, "place1", level=5)
    resp = client.post("/places/place1/donate", json={"instance_id": "nonexistent_inst"})
    assert resp.status_code == 404


def test_donate_item_already_in_slot(client, db):
    _make_place(db, "place1", level=5)
    _make_item(db, "book_rare")
    _make_instance(db, "inst1", "book_rare", placed_in="some_slot")
    resp = client.post("/places/place1/donate", json={"instance_id": "inst1"})
    assert resp.status_code == 400
    assert "placed" in resp.json()["detail"].lower()


def test_donate_duplicate_item_type(client, db):
    _make_place(db, "place1", level=5)
    _make_item(db, "book_rare")
    _make_instance(db, "inst1", "book_rare")
    _make_instance(db, "inst2", "book_rare")
    client.post("/places/place1/donate", json={"instance_id": "inst1"})
    resp = client.post("/places/place1/donate", json={"instance_id": "inst2"})
    assert resp.status_code == 409


# ── load_place_perks ──────────────────────────────────────────────────────────

def test_load_place_perks_returns_effects(db):
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO place_perks (perk_id, place_id, item_id, instance_id, boost_factor, donated_at) "
        "VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), "place_x", "some_item", "inst_x", 0.10, now),
    )
    db.commit()
    effects = load_place_perks(db)
    assert len(effects) == 1
    assert effects[0].effect_type == "xp_multiplier"
    assert effects[0].params["factor"] == pytest.approx(1.10)


def test_load_place_perks_empty_by_default(db):
    effects = load_place_perks(db)
    assert effects == []


# ── XP multiplier applied in agent ───────────────────────────────────────────

def _make_agent(db) -> SyncAgent:
    mock_tracker = MagicMock(spec=TrackerClient)
    return SyncAgent(
        db=db, tracker_client=mock_tracker,
        character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )


def _make_chunk(category: str = "WORK", duration_min: int = 10) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "chunk_id": str(uuid.uuid4()),
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_sec": duration_min * 60,
        "label": category,
        "confidence": 0.9,
        "time_of_day": "morning",
    }


def test_perk_boosts_xp_in_agent(db):
    """A donated perk's xp_multiplier is applied during poll()."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO place_perks (perk_id, place_id, item_id, instance_id, boost_factor, donated_at) "
        "VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), "place_y", "item_y", "inst_y", 0.10, now),
    )
    db.commit()

    agent = _make_agent(db)
    agent.tracker_client.fetch_chunks.return_value = ([_make_chunk("WORK", 10)], "cursor1")
    agent.poll()

    xp_row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='WORK'"
    ).fetchone()
    # Base: 10 min × 1 XP/min = 10. With 1.1× perk → 11.
    assert xp_row is not None
    assert xp_row["xp"] == 11


# ── perk viewer in GET /places ────────────────────────────────────────────────

def test_places_response_includes_perks_field(client, db):
    _make_place(db, "place1", level=5)
    data = client.get("/places").json()
    assert len(data) == 1
    assert "perks" in data[0]
    assert data[0]["perks"] == []


def test_places_perks_empty_when_none_donated(client, db):
    _make_place(db, "place1", level=5)
    resp = client.get("/places/place1")
    assert resp.status_code == 200
    assert resp.json()["perks"] == []


def test_places_perks_shows_donated_item(client, db):
    _make_place(db, "place1", level=5)
    _make_item(db, "tome_epic", "EPIC")
    _make_instance(db, "inst1", "tome_epic")
    client.post("/places/place1/donate", json={"instance_id": "inst1"})

    data = client.get("/places/place1").json()
    assert len(data["perks"]) == 1
    perk = data["perks"][0]
    assert perk["item_id"] == "tome_epic"
    assert perk["item_name"] == "tome_epic"
    assert perk["item_rarity"] == "EPIC"
    assert perk["boost_factor"] == pytest.approx(0.10)


def test_places_list_perks_grouped_by_place(client, db):
    _make_place(db, "place1", level=5)
    _make_place(db, "place2", level=5)
    _make_item(db, "book_a")
    _make_item(db, "book_b")
    _make_instance(db, "inst_a", "book_a")
    _make_instance(db, "inst_b", "book_b")
    client.post("/places/place1/donate", json={"instance_id": "inst_a"})
    client.post("/places/place2/donate", json={"instance_id": "inst_b"})

    places = client.get("/places").json()
    p1 = next(p for p in places if p["place_id"] == "place1")
    p2 = next(p for p in places if p["place_id"] == "place2")
    assert len(p1["perks"]) == 1
    assert p1["perks"][0]["item_id"] == "book_a"
    assert len(p2["perks"]) == 1
    assert p2["perks"][0]["item_id"] == "book_b"


def test_places_multiple_perks_on_same_place(client, db):
    _make_place(db, "place1", level=5)
    _make_item(db, "item_x")
    _make_item(db, "item_y")
    _make_instance(db, "inst_x", "item_x")
    _make_instance(db, "inst_y", "item_y")
    client.post("/places/place1/donate", json={"instance_id": "inst_x"})
    client.post("/places/place1/donate", json={"instance_id": "inst_y"})

    data = client.get("/places/place1").json()
    assert len(data["perks"]) == 2
    item_ids = {p["item_id"] for p in data["perks"]}
    assert item_ids == {"item_x", "item_y"}
