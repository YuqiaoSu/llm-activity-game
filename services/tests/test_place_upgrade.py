"""Tests for place XP and levelling system."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from services.storage.db import init_db
from services.place_service.upgrade import (
    xp_threshold,
    xp_to_level,
    award_place_xp,
    get_active_place_ids,
)
from services.sync_agent.agent import SyncAgent
from services.sync_agent.tracker_client import TrackerClient
from services.sync_agent.rate_limiter import RateLimiter


# ── unit tests for level math ─────────────────────────────────────────────────

def test_xp_threshold_level_1_is_zero():
    assert xp_threshold(1) == 0


def test_xp_threshold_level_2_is_50():
    assert xp_threshold(2) == 50


def test_xp_threshold_level_3_is_200():
    assert xp_threshold(3) == 200


def test_xp_threshold_level_4_is_450():
    assert xp_threshold(4) == 450


def test_xp_to_level_zero_xp_is_level_1():
    assert xp_to_level(0) == 1


def test_xp_to_level_49_is_level_1():
    assert xp_to_level(49) == 1


def test_xp_to_level_50_is_level_2():
    assert xp_to_level(50) == 2


def test_xp_to_level_200_is_level_3():
    assert xp_to_level(200) == 3


def test_xp_to_level_199_is_level_2():
    assert xp_to_level(199) == 2


# ── integration tests ─────────────────────────────────────────────────────────

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
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("scroll", json.dumps({
            "item_id": "scroll", "name": "Scroll", "rarity": "COMMON",
            "category": "WORK", "icon": "", "effects": [], "description": "",
            "drop_requirement": {},
        })),
    )
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, item_pool, metadata) "
        "VALUES ('lab', 'Lab', 'home', '{}', '{}')"
    )
    conn.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type, metadata) "
        "VALUES ('lab_s1', 'lab', 'ITEM', '{}')"
    )
    conn.commit()
    return conn


def test_award_place_xp_increments_xp(db):
    award_place_xp(db, "lab", 30)
    db.commit()
    row = db.execute("SELECT xp FROM places WHERE place_id='lab'").fetchone()
    assert row["xp"] == 30


def test_award_place_xp_level_up_on_threshold(db):
    levelled = award_place_xp(db, "lab", 50)
    db.commit()
    assert levelled is True
    row = db.execute("SELECT level FROM places WHERE place_id='lab'").fetchone()
    assert row["level"] == 2


def test_award_place_xp_no_level_up_below_threshold(db):
    levelled = award_place_xp(db, "lab", 49)
    db.commit()
    assert levelled is False
    row = db.execute("SELECT level FROM places WHERE place_id='lab'").fetchone()
    assert row["level"] == 1


def test_award_place_xp_notification_created_on_level_up(db):
    award_place_xp(db, "lab", 50, character_id="player_default")
    db.commit()
    n = db.execute(
        "SELECT payload FROM pending_notifications WHERE event_type='place_level_up'"
    ).fetchone()
    assert n is not None
    assert '"new_level":2' in n["payload"]


def test_award_place_xp_no_notification_without_level_up(db):
    award_place_xp(db, "lab", 10, character_id="player_default")
    db.commit()
    n = db.execute(
        "SELECT * FROM pending_notifications WHERE event_type='place_level_up'"
    ).fetchone()
    assert n is None


def test_get_active_place_ids_returns_occupied(db):
    db.execute("UPDATE place_slots SET occupant_id='inst-1' WHERE slot_id='lab_s1'")
    db.commit()
    ids = get_active_place_ids(db)
    assert "lab" in ids


def test_get_active_place_ids_excludes_empty_slots(db):
    ids = get_active_place_ids(db)
    assert "lab" not in ids


def test_poll_awards_place_xp_for_active_slots(db):
    """A chunk processed while a slot has an occupant should increase place XP."""
    # Put an item in the slot
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES ('inst-1', 'player_default', 'scroll', '2026-01-01T00:00:00+00:00', 'c0')"
    )
    db.execute("UPDATE place_slots SET occupant_id='inst-1' WHERE slot_id='lab_s1'")
    db.commit()

    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (
        [{
            "chunk_id": "c1",
            "started_at": "2026-01-01T10:00:00+00:00",
            "duration_sec": 600,
            "label": "WORK",
            "confidence": 0.9,
            "time_of_day": "morning",
        }],
        "cursor_1",
    )

    agent = SyncAgent(
        db=db, tracker_client=mock_client,
        character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )
    agent.poll(manual=True)

    xp = db.execute("SELECT xp FROM places WHERE place_id='lab'").fetchone()["xp"]
    assert xp > 0


def test_poll_does_not_award_place_xp_when_no_slots_occupied(db):
    """If no slots are occupied, places should not gain XP."""
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (
        [{
            "chunk_id": "c2",
            "started_at": "2026-01-01T10:00:00+00:00",
            "duration_sec": 600,
            "label": "WORK",
            "confidence": 0.9,
            "time_of_day": "morning",
        }],
        "cursor_2",
    )

    agent = SyncAgent(
        db=db, tracker_client=mock_client,
        character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )
    agent.poll(manual=True)

    xp = db.execute("SELECT xp FROM places WHERE place_id='lab'").fetchone()["xp"]
    assert xp == 0
