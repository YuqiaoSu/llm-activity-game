"""Tests for dynamic goal difficulty scaling."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest

from services.progression.daily_goals import (
    compute_goal_difficulty_multiplier,
    ensure_daily_goals,
    _MAX_TARGET_SEC,
)
from services.storage.db import init_db


# ── pure unit tests for the multiplier formula ────────────────────────────────

def test_multiplier_streak_0():
    assert compute_goal_difficulty_multiplier(0) == pytest.approx(1.0)


def test_multiplier_streak_2():
    assert compute_goal_difficulty_multiplier(2) == pytest.approx(1.0)


def test_multiplier_streak_3():
    # 1 tier completed → 1.2^1
    assert compute_goal_difficulty_multiplier(3) == pytest.approx(1.2)


def test_multiplier_streak_6():
    # 2 tiers → 1.2^2 = 1.44
    assert compute_goal_difficulty_multiplier(6) == pytest.approx(1.44)


def test_multiplier_streak_9():
    # 3 tiers → 1.2^3 = 1.728
    assert compute_goal_difficulty_multiplier(9) == pytest.approx(1.728, rel=1e-3)


def test_multiplier_streak_5_same_as_3():
    # 5 // 3 == 1 tier, same as streak=3
    assert compute_goal_difficulty_multiplier(5) == pytest.approx(
        compute_goal_difficulty_multiplier(3)
    )


# ── integration tests for ensure_daily_goals ─────────────────────────────────

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
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


def _fake_suggestions(target_min: int = 20):
    return [
        {"type": "gap", "category": "WORK",   "target_min": target_min},
        {"type": "gap", "category": "SOCIAL", "target_min": target_min},
    ]


def test_goals_use_base_target_at_streak_0(db):
    with patch("services.progression.daily_goals.get_suggestions",
               return_value=_fake_suggestions(20)):
        ensure_daily_goals(db, "player_default")
    rows = db.execute("SELECT target_sec FROM daily_goals WHERE player_id='player_default'").fetchall()
    assert len(rows) == 2
    for r in rows:
        assert r["target_sec"] == 1200   # 20 min × 60


def test_goals_scaled_at_streak_3(db):
    db.execute("UPDATE streak_state SET goal_streak=3 WHERE player_id='default'")
    db.commit()
    with patch("services.progression.daily_goals.get_suggestions",
               return_value=_fake_suggestions(20)):
        ensure_daily_goals(db, "player_default")
    rows = db.execute("SELECT target_sec FROM daily_goals WHERE player_id='player_default'").fetchall()
    # 1200 × 1.2 = 1440
    for r in rows:
        assert r["target_sec"] == 1440


def test_goals_scaled_at_streak_6(db):
    db.execute("UPDATE streak_state SET goal_streak=6 WHERE player_id='default'")
    db.commit()
    with patch("services.progression.daily_goals.get_suggestions",
               return_value=_fake_suggestions(20)):
        ensure_daily_goals(db, "player_default")
    rows = db.execute("SELECT target_sec FROM daily_goals WHERE player_id='player_default'").fetchall()
    # 1200 × 1.44 = 1728
    for r in rows:
        assert r["target_sec"] == 1728


def test_goals_capped_at_max(db):
    # Very high streak → target would exceed 7200s without cap
    db.execute("UPDATE streak_state SET goal_streak=99 WHERE player_id='default'")
    db.commit()
    with patch("services.progression.daily_goals.get_suggestions",
               return_value=_fake_suggestions(200)):   # 200 min base = 12000s
        ensure_daily_goals(db, "player_default")
    rows = db.execute("SELECT target_sec FROM daily_goals WHERE player_id='player_default'").fetchall()
    for r in rows:
        assert r["target_sec"] == _MAX_TARGET_SEC   # == 7200


def test_no_streak_state_row_uses_1x(db):
    # Delete streak_state so the fallback (0 streak) is used
    db.execute("DELETE FROM streak_state WHERE player_id='default'")
    db.commit()
    with patch("services.progression.daily_goals.get_suggestions",
               return_value=_fake_suggestions(20)):
        ensure_daily_goals(db, "player_default")
    rows = db.execute("SELECT target_sec FROM daily_goals WHERE player_id='player_default'").fetchall()
    for r in rows:
        assert r["target_sec"] == 1200
