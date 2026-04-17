"""Tests for the place unlock quest chain feature.

Verifies that:
- GET /places returns LOCKED places with unlock_condition data
- GET /places/{id} works for locked places
- Polling with enough XP to trigger a level-up unlocks matching places
- A place_unlock notification is created on unlock
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.models.enums import Category, PlaceState, SlotType
from services.models.place import Condition, Place, PlaceItemPool, PlaceSlot
from services.place_service.service import save_place, check_unlock_condition
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


def _seed_locked_place(db, place_id: str = "test_workshop", min_level: int = 3) -> None:
    place = Place(
        place_id=place_id,
        name="Test Workshop",
        place_type="workshop",
        description="Test locked place",
        category=Category.WORK,
        state=PlaceState.LOCKED,
        unlock_condition=Condition(condition_type="player_level", params={"min_level": min_level}),
        item_pool=PlaceItemPool(),
        slots=[],
    )
    save_place(db, place)


def _seed_unlocked_place(db, place_id: str = "home_study") -> None:
    place = Place(
        place_id=place_id,
        name="Home Study",
        place_type="home",
        description="An unlocked place",
        category=Category.WORK,
        state=PlaceState.UNLOCKED,
        item_pool=PlaceItemPool(),
        slots=[],
    )
    save_place(db, place)


# ── GET /places ───────────────────────────────────────────────────────────────

def test_get_places_includes_locked(client, db):
    _seed_locked_place(db)
    data = client.get("/places").json()
    locked = [p for p in data if p.get("state") == "LOCKED"]
    assert len(locked) == 1


def test_locked_place_has_unlock_condition(client, db):
    _seed_locked_place(db, min_level=5)
    data = client.get("/places").json()
    locked = [p for p in data if p.get("state") == "LOCKED"][0]
    cond = locked.get("unlock_condition")
    assert cond is not None
    assert cond["condition_type"] == "player_level"
    assert cond["params"]["min_level"] == 5


def test_unlocked_place_has_no_unlock_condition(client, db):
    _seed_unlocked_place(db)
    data = client.get("/places").json()
    unlocked = [p for p in data if p.get("state") == "UNLOCKED"]
    assert len(unlocked) == 1
    assert unlocked[0].get("unlock_condition") is None


def test_get_places_returns_both_locked_and_unlocked(client, db):
    _seed_locked_place(db)
    _seed_unlocked_place(db)
    data = client.get("/places").json()
    states = {p["state"] for p in data}
    assert "LOCKED" in states
    assert "UNLOCKED" in states


def test_get_place_by_id_locked(client, db):
    _seed_locked_place(db, "test_workshop", min_level=4)
    resp = client.get("/places/test_workshop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "LOCKED"
    assert data["unlock_condition"]["params"]["min_level"] == 4


def test_get_place_by_id_not_found(client, db):
    resp = client.get("/places/nonexistent_place")
    assert resp.status_code == 404


# ── check_unlock_condition logic ──────────────────────────────────────────────

def test_check_unlock_condition_met(db):
    place = Place(
        place_id="p1", name="P", place_type="t",
        unlock_condition=Condition(condition_type="player_level", params={"min_level": 3}),
        item_pool=PlaceItemPool(), slots=[],
    )
    assert check_unlock_condition(db, place, player_level=5) is True


def test_check_unlock_condition_not_met(db):
    place = Place(
        place_id="p2", name="P", place_type="t",
        unlock_condition=Condition(condition_type="player_level", params={"min_level": 10}),
        item_pool=PlaceItemPool(), slots=[],
    )
    assert check_unlock_condition(db, place, player_level=3) is False


def test_check_unlock_condition_exact_level_met(db):
    place = Place(
        place_id="p3", name="P", place_type="t",
        unlock_condition=Condition(condition_type="player_level", params={"min_level": 5}),
        item_pool=PlaceItemPool(), slots=[],
    )
    assert check_unlock_condition(db, place, player_level=5) is True


def test_place_unlock_notification_on_agent_poll(db):
    """A LOCKED place unlocks and notifies when poll awards enough XP to level past the threshold."""
    from unittest.mock import MagicMock
    from services.sync_agent.agent import SyncAgent
    from services.sync_agent.tracker_client import TrackerClient
    from services.drop_engine.strategies import SessionStrategy

    _seed_locked_place(db, "workshop", min_level=2)

    # 7200-second WORK chunk delivers enough XP to reach level 2
    chunks = [{
        "chunk_id": "c_unlock_test", "label": "WORK", "duration_sec": 7200,
        "confidence": 0.9, "started_at": "2026-04-14T09:00:00+00:00",
        "time_of_day": "morning",
    }]
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "c_unlock_test")
    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    agent.poll()

    row = db.execute("SELECT state FROM places WHERE place_id='workshop'").fetchone()
    notif = db.execute(
        "SELECT payload FROM pending_notifications "
        "WHERE character_id='player_default' AND event_type='place_unlock'"
    ).fetchone()
    assert row["state"] == "UNLOCKED"
    assert notif is not None
    assert json.loads(notif["payload"])["place_id"] == "workshop"
