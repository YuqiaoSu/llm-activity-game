"""Tests for category-specific XP bonus effects."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock
import pytest
from services.storage.db import init_db
from services.models.item import Effect
from services.sync_agent.agent import SyncAgent
from services.sync_agent.tracker_client import TrackerClient
from services.sync_agent.rate_limiter import RateLimiter


# ── unit tests for _category_xp_bonus ────────────────────────────────────────

def test_no_effects_returns_1():
    assert SyncAgent._category_xp_bonus([], "WORK") == pytest.approx(1.0)


def test_matching_category_applies_factor():
    effects = [Effect(effect_type="category_xp_bonus", target="slot",
                      params={"category": "WORK", "factor": 1.3})]
    assert SyncAgent._category_xp_bonus(effects, "WORK") == pytest.approx(1.3)


def test_non_matching_category_returns_1():
    effects = [Effect(effect_type="category_xp_bonus", target="slot",
                      params={"category": "GAME", "factor": 1.3})]
    assert SyncAgent._category_xp_bonus(effects, "WORK") == pytest.approx(1.0)


def test_multiple_matching_effects_stack():
    effects = [
        Effect(effect_type="category_xp_bonus", target="slot",
               params={"category": "WORK", "factor": 1.3}),
        Effect(effect_type="category_xp_bonus", target="slot",
               params={"category": "WORK", "factor": 1.2}),
    ]
    assert SyncAgent._category_xp_bonus(effects, "WORK") == pytest.approx(1.3 * 1.2)


def test_only_matching_category_stacks():
    effects = [
        Effect(effect_type="category_xp_bonus", target="slot",
               params={"category": "WORK", "factor": 1.3}),
        Effect(effect_type="category_xp_bonus", target="slot",
               params={"category": "GAME", "factor": 2.0}),
    ]
    assert SyncAgent._category_xp_bonus(effects, "WORK") == pytest.approx(1.3)


def test_category_check_is_case_insensitive():
    effects = [Effect(effect_type="category_xp_bonus", target="slot",
                      params={"category": "work", "factor": 1.5})]
    assert SyncAgent._category_xp_bonus(effects, "WORK") == pytest.approx(1.5)


def test_other_effect_types_ignored():
    effects = [
        Effect(effect_type="xp_multiplier", target="slot", params={"factor": 2.0}),
        Effect(effect_type="drop_weight_mod", target="slot",
               params={"rarity": "RARE", "factor": 2.0}),
    ]
    assert SyncAgent._category_xp_bonus(effects, "WORK") == pytest.approx(1.0)


# ── integration: category bonus applied during poll ───────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
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
    conn.commit()
    return conn


def _make_chunk(label: str, duration_sec: int = 600, chunk_id: str = "c1") -> dict:
    return {
        "chunk_id": chunk_id,
        "started_at": "2026-01-01T10:00:00+00:00",
        "duration_sec": duration_sec,
        "label": label,
        "confidence": 0.9,
        "time_of_day": "morning",
    }


def test_category_bonus_increases_xp_for_matching_category(db):
    """A WORK category_xp_bonus effect should increase XP for WORK chunks."""
    # Seed a place_active_effect for category_xp_bonus on WORK
    db.execute(
        """
        INSERT INTO places (place_id, name, place_type, item_pool, metadata)
        VALUES ('lab', 'Lab', 'home', '{}', '{}')
        """
    )
    db.execute(
        """
        INSERT INTO place_slots (slot_id, place_id, slot_type, metadata)
        VALUES ('lab_s1', 'lab', 'ITEM', '{}')
        """
    )
    import uuid
    from datetime import datetime, timezone
    db.execute(
        """
        INSERT INTO place_active_effects
        (effect_id, place_id, source_slot_id, effect_type, params, applied_at)
        VALUES (?, 'lab', 'lab_s1', 'category_xp_bonus', ?, ?)
        """,
        (
            str(uuid.uuid4()),
            json.dumps({"category": "WORK", "factor": 2.0}),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()

    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (
        [_make_chunk("WORK", 600)],
        "cursor_1",
    )

    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )
    agent.poll(manual=True)

    xp = db.execute(
        "SELECT xp_awarded FROM chunk_log WHERE chunk_id='c1'"
    ).fetchone()["xp_awarded"]
    # Base: 600/60 * 1 XP/min = 10 XP; with 2.0 category bonus → 20 XP
    assert xp == 20


def test_category_bonus_does_not_affect_other_categories(db):
    """A WORK category bonus should not affect GAME chunks."""
    db.execute(
        "INSERT INTO places (place_id, name, place_type, item_pool, metadata) "
        "VALUES ('lab2', 'Lab2', 'home', '{}', '{}')"
    )
    db.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type, metadata) "
        "VALUES ('lab2_s1', 'lab2', 'ITEM', '{}')"
    )
    import uuid
    from datetime import datetime, timezone
    db.execute(
        "INSERT INTO place_active_effects "
        "(effect_id, place_id, source_slot_id, effect_type, params, applied_at) "
        "VALUES (?, 'lab2', 'lab2_s1', 'category_xp_bonus', ?, ?)",
        (
            str(uuid.uuid4()),
            json.dumps({"category": "WORK", "factor": 2.0}),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    # Also seed a GAME item for drops
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        ("game_scroll", json.dumps({
            "item_id": "game_scroll", "name": "Game Scroll", "rarity": "COMMON",
            "category": "GAME", "icon": "", "effects": [], "description": "",
            "drop_requirement": {},
        })),
    )
    db.commit()

    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (
        [_make_chunk("GAME", 600)],
        "cursor_2",
    )

    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )
    agent.poll(manual=True)

    xp = db.execute(
        "SELECT xp_awarded FROM chunk_log WHERE chunk_id='c1'"
    ).fetchone()["xp_awarded"]
    # Base 10 XP; WORK bonus shouldn't apply to GAME → still 10
    assert xp == 10
