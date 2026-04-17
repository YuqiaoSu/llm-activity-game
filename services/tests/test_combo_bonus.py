"""Tests for the combo activity bonus (1.1× XP when ≥ 3 distinct categories in one poll)."""
import json
import sqlite3  # noqa: F401 — used in test_two_categories_no_combo_bonus
from unittest.mock import MagicMock

import pytest

from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition, DropRequirement
from services.progression.xp import get_total_xp
from services.storage.db import init_db
from services.sync_agent.agent import SyncAgent, _COMBO_BONUS_FACTOR, _COMBO_CATEGORY_THRESHOLD
from services.sync_agent.tracker_client import TrackerClient


def _chunk(label: str, duration: int = 600, conf: float = 0.9) -> dict:
    return {
        "chunk_id": f"c_{label}_{duration}",
        "label": label,
        "duration_sec": duration,
        "confidence": conf,
        "started_at": "2026-04-16T10:00:00+00:00",
        "time_of_day": "morning",
    }


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
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


def _make_agent(db, chunks: list[dict]) -> SyncAgent:
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "cursor_x")
    return SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        min_confidence=0.5,
    )


# ── constant sanity ───────────────────────────────────────────────────────────

def test_combo_threshold_is_three():
    assert _COMBO_CATEGORY_THRESHOLD == 3


def test_combo_factor_is_1_1():
    assert abs(_COMBO_BONUS_FACTOR - 1.1) < 0.001


# ── no bonus with < 3 categories ─────────────────────────────────────────────

def test_one_category_no_combo_bonus(db):
    """One category → no combo; two 600-sec WORK chunks = 20 XP exactly."""
    chunks = [_chunk("WORK", 600), _chunk("WORK", 600)]
    xp_before = get_total_xp(db, "player_default")
    agent = _make_agent(db, chunks)
    agent.poll()
    xp_after = get_total_xp(db, "player_default")
    xp_gained = xp_after - xp_before

    # 2 × 10 base XP, no combo multiplier → exactly 20
    assert xp_gained == 20


def test_two_categories_no_combo_bonus(db):
    """2 distinct categories → no combo; XP should equal 2× single chunk."""
    # Use fresh db so streak/recovery don't interfere
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "T", visual),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()

    chunks = [_chunk("WORK", 600), _chunk("GAME", 600)]
    xp_before = get_total_xp(conn, "player_default")
    agent = _make_agent(conn, chunks)
    agent.poll()
    xp_after = get_total_xp(conn, "player_default")
    xp_gained = xp_after - xp_before

    # Each 600-sec chunk awards 10 XP base; two chunks → 20, not 22
    assert xp_gained == 20
    conn.close()


# ── bonus applies at exactly 3 categories ────────────────────────────────────

def test_three_categories_triggers_combo_bonus(db):
    """3 distinct categories → each chunk gets 1.1× XP."""
    chunks = [_chunk("WORK", 600), _chunk("GAME", 600), _chunk("VIDEO", 600)]
    xp_before = get_total_xp(db, "player_default")
    agent = _make_agent(db, chunks)
    agent.poll()
    xp_after = get_total_xp(db, "player_default")
    xp_gained = xp_after - xp_before

    # Base = 10 XP per 600-sec chunk, 3 chunks, with 1.1× = 3 × 11 = 33
    assert xp_gained == 33


def test_four_categories_also_triggers_combo_bonus(db):
    """≥ 3 distinct categories always qualifies for the combo."""
    chunks = [_chunk("WORK", 600), _chunk("GAME", 600),
              _chunk("VIDEO", 600), _chunk("SOCIAL", 600)]
    xp_before = get_total_xp(db, "player_default")
    agent = _make_agent(db, chunks)
    agent.poll()
    xp_after = get_total_xp(db, "player_default")
    xp_gained = xp_after - xp_before

    # 4 × 10 × 1.1 = 44
    assert xp_gained == 44


# ── low-confidence chunks don't count for combo ──────────────────────────────

def test_low_confidence_chunks_dont_count_for_combo(db):
    """Chunks below min_confidence are skipped in both XP and combo counting."""
    chunks = [
        _chunk("WORK", 600, conf=0.9),
        _chunk("GAME", 600, conf=0.1),   # below threshold
        _chunk("VIDEO", 600, conf=0.1),  # below threshold
    ]
    xp_before = get_total_xp(db, "player_default")
    agent = _make_agent(db, chunks)
    agent.poll()
    xp_after = get_total_xp(db, "player_default")
    xp_gained = xp_after - xp_before

    # Only 1 valid category → no combo; only 1 valid chunk → 10 XP base
    assert xp_gained == 10


# ── duplicate categories don't inflate the count ─────────────────────────────

def test_repeated_category_counts_once_for_combo(db):
    """Three chunks of WORK + one GAME + one VIDEO = 3 distinct → combo active."""
    chunks = [
        _chunk("WORK", 600), _chunk("WORK", 600), _chunk("WORK", 600),
        _chunk("GAME", 600), _chunk("VIDEO", 600),
    ]
    xp_before = get_total_xp(db, "player_default")
    agent = _make_agent(db, chunks)
    agent.poll()
    xp_after = get_total_xp(db, "player_default")
    xp_gained = xp_after - xp_before

    # 5 chunks × 10 base XP × 1.1 = 55
    assert xp_gained == 55
