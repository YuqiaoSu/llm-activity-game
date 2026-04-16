"""Tests for daily goal streak reward mechanic."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.progression.daily_goals import check_goal_streak_reward
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
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


def _add_item_def(db, item_id: str, rarity: str) -> None:
    data = json.dumps({"name": item_id, "category": "focus", "rarity": rarity,
                       "description": "", "effects": []})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?,?)",
               (item_id, data))
    db.commit()


_GOAL_CATS = ["focus", "rest", "social", "creative", "exercise", "learning"]
_goal_cat_idx = 0


def _add_goal(db, completed: bool, date: str | None = None, category: str | None = None) -> str:
    global _goal_cat_idx
    today = date or datetime.now(timezone.utc).date().isoformat()
    cat = category or _GOAL_CATS[_goal_cat_idx % len(_GOAL_CATS)]
    _goal_cat_idx += 1
    gid = str(uuid.uuid4())
    db.execute(
        "INSERT OR IGNORE INTO daily_goals (goal_id, player_id, date, category, target_sec, "
        "progress_sec, completed, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (gid, "player_default", today, cat, 1200,
         1200 if completed else 0, 1 if completed else 0,
         datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    return gid


def _set_goal_streak(db, streak: int, last_date: str | None = None) -> None:
    db.execute(
        "UPDATE streak_state SET goal_streak=?, last_goal_streak_date=? WHERE player_id='default'",
        (streak, last_date),
    )
    db.commit()


# ── no-reward cases ───────────────────────────────────────────────────────────

def test_no_goals_today_no_reward(db):
    _add_item_def(db, "rare_item", "RARE")
    result = check_goal_streak_reward(db)
    assert result is False


def test_not_all_goals_completed_no_reward(db):
    _add_item_def(db, "rare_item", "RARE")
    _add_goal(db, completed=True)
    _add_goal(db, completed=False)
    result = check_goal_streak_reward(db)
    assert result is False


def test_not_all_goals_resets_streak(db):
    _add_item_def(db, "rare_item", "RARE")
    _set_goal_streak(db, 5)
    _add_goal(db, completed=True)
    _add_goal(db, completed=False)
    check_goal_streak_reward(db)
    row = db.execute("SELECT goal_streak FROM streak_state WHERE player_id='default'").fetchone()
    assert row["goal_streak"] == 0


def test_idempotent_same_day(db):
    _add_item_def(db, "rare_item", "RARE")
    _set_goal_streak(db, 6)  # 7th call will cross the milestone
    _add_goal(db, completed=True)
    result1 = check_goal_streak_reward(db)
    result2 = check_goal_streak_reward(db)
    assert result1 is True   # first call awards milestone
    assert result2 is False  # second call same day is no-op


# ── streak increment ──────────────────────────────────────────────────────────

def test_streak_increments_on_all_goals_complete(db):
    _set_goal_streak(db, 2)
    _add_goal(db, completed=True)
    check_goal_streak_reward(db)
    row = db.execute("SELECT goal_streak FROM streak_state WHERE player_id='default'").fetchone()
    assert row["goal_streak"] == 3


# ── milestone rewards ─────────────────────────────────────────────────────────

def test_7_day_milestone_awards_rare_item(db):
    _add_item_def(db, "rare_item", "RARE")
    _set_goal_streak(db, 6)  # next completion crosses 7
    _add_goal(db, completed=True)
    result = check_goal_streak_reward(db)
    assert result is True
    row = db.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE character_id='player_default' AND item_id='rare_item'"
    ).fetchone()
    assert row["n"] >= 1


def test_14_day_milestone_awards_epic_item(db):
    _add_item_def(db, "epic_item", "EPIC")
    _set_goal_streak(db, 13)  # next completion crosses 14
    _add_goal(db, completed=True)
    result = check_goal_streak_reward(db)
    assert result is True
    row = db.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE character_id='player_default' AND item_id='epic_item'"
    ).fetchone()
    assert row["n"] >= 1


def test_milestone_stamps_reward_ledger(db):
    _add_item_def(db, "rare_item", "RARE")
    today = datetime.now(timezone.utc).date().isoformat()
    _set_goal_streak(db, 6)
    _add_goal(db, completed=True)
    check_goal_streak_reward(db)
    row = db.execute(
        "SELECT * FROM reward_ledger WHERE chunk_id=?",
        (f"goal_streak_7_{today}",),
    ).fetchone()
    assert row is not None


def test_milestone_creates_notification(db):
    _add_item_def(db, "rare_item", "RARE")
    _set_goal_streak(db, 6)
    _add_goal(db, completed=True)
    check_goal_streak_reward(db)
    row = db.execute(
        "SELECT * FROM pending_notifications WHERE character_id='player_default' AND event_type='item_drop'"
    ).fetchone()
    assert row is not None


def test_non_milestone_streak_no_reward(db):
    _add_item_def(db, "rare_item", "RARE")
    _set_goal_streak(db, 3)  # → 4, not a milestone
    _add_goal(db, completed=True)
    result = check_goal_streak_reward(db)
    assert result is False
    row = db.execute("SELECT goal_streak FROM streak_state WHERE player_id='default'").fetchone()
    assert row["goal_streak"] == 4
