"""Tests for place mood influence on award_place_xp."""
import json
import sqlite3
from datetime import date, timedelta

import pytest

from services.storage.db import init_db
from services.progression.mood import mood_xp_multiplier
from services.place_service.upgrade import award_place_xp


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
    # Seed one place
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, item_pool, metadata, state, xp, level)"
        " VALUES ('place_test', 'Test Place', 'home', '{}', '{}', 'UNLOCKED', 0, 1)"
    )
    conn.commit()
    yield conn
    conn.close()


def _set_streak(db, days: int) -> None:
    today = date.today().isoformat()
    db.execute(
        "UPDATE streak_state SET current_streak=?, last_active_date=? WHERE player_id='default'",
        (days, today),
    )
    db.commit()


def _set_dormant(db, days_ago: int) -> None:
    past = (date.today() - timedelta(days=days_ago)).isoformat()
    db.execute(
        "UPDATE streak_state SET current_streak=0, last_active_date=? WHERE player_id='default'",
        (past,),
    )
    db.commit()


# ── mood_xp_multiplier unit tests ─────────────────────────────────────────────

def test_happy_multiplier():
    assert abs(mood_xp_multiplier("happy") - 1.1) < 0.001


def test_neutral_multiplier():
    assert abs(mood_xp_multiplier("neutral") - 1.0) < 0.001


def test_sad_multiplier():
    assert abs(mood_xp_multiplier("sad") - 0.9) < 0.001


def test_anxious_multiplier():
    assert abs(mood_xp_multiplier("anxious") - 0.8) < 0.001


def test_unknown_mood_defaults_to_1():
    assert abs(mood_xp_multiplier("unknown_mood") - 1.0) < 0.001


# ── award_place_xp integration ────────────────────────────────────────────────

def test_happy_player_earns_more_place_xp(db):
    _set_streak(db, 7)  # streak ≥ 7 → happy
    award_place_xp(db, "place_test", 100)
    row = db.execute("SELECT xp FROM places WHERE place_id='place_test'").fetchone()
    assert row["xp"] >= 110  # 100 * 1.1 = 110


def test_neutral_player_earns_base_place_xp(db):
    _set_streak(db, 1)  # streak < 7, not dormant → neutral
    award_place_xp(db, "place_test", 100)
    row = db.execute("SELECT xp FROM places WHERE place_id='place_test'").fetchone()
    assert row["xp"] == 100  # 100 * 1.0 = 100


def test_anxious_player_earns_less_place_xp(db):
    _set_dormant(db, 14)  # 14 days dormant → anxious
    award_place_xp(db, "place_test", 100)
    row = db.execute("SELECT xp FROM places WHERE place_id='place_test'").fetchone()
    assert row["xp"] == 80  # 100 * 0.8 = 80


def test_minimum_one_xp_when_multiplier_rounds_down(db):
    _set_dormant(db, 14)  # anxious
    award_place_xp(db, "place_test", 1)  # 1 * 0.8 = 0.8 → clamped to 1
    row = db.execute("SELECT xp FROM places WHERE place_id='place_test'").fetchone()
    assert row["xp"] >= 1
