"""Tests for challenge progress (50%) notifications."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest

from services.storage.db import init_db
from services.progression.weekly_challenges import update_weekly_progress, get_week_start


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _seed_challenge(db, challenge_id: str, category: str, threshold: int, metric: str = "xp") -> None:
    db.execute(
        "INSERT INTO weekly_challenges (challenge_id, name, description, category, metric, threshold)"
        " VALUES (?, ?, 'desc', ?, ?, ?)",
        (challenge_id, "Test " + challenge_id, category, metric, threshold),
    )
    db.commit()


def _count_notifs(db, event_type: str) -> int:
    return db.execute(
        "SELECT COUNT(*) FROM pending_notifications WHERE event_type=?",
        (event_type,),
    ).fetchone()[0]


def _get_progress_notifs(db) -> list[dict]:
    rows = db.execute(
        "SELECT payload FROM pending_notifications WHERE event_type='challenge_progress'"
    ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


# ── 50% firing ───────────────────────────────────────────────────────────────

def test_50pct_fires_when_crossing_half(db):
    _seed_challenge(db, "ch1", "WORK", 200)
    update_weekly_progress(db, "player_default", {"WORK": 100})
    notifs = _get_progress_notifs(db)
    assert len(notifs) == 1
    assert notifs[0]["pct"] == 50
    assert notifs[0]["challenge_id"] == "ch1"


def test_50pct_does_not_fire_below_half(db):
    _seed_challenge(db, "ch1", "WORK", 200)
    update_weekly_progress(db, "player_default", {"WORK": 50})
    assert _count_notifs(db, "challenge_progress") == 0


def test_50pct_fires_exactly_at_half(db):
    _seed_challenge(db, "ch1", "WORK", 100)
    update_weekly_progress(db, "player_default", {"WORK": 50})
    assert _count_notifs(db, "challenge_progress") == 1


def test_50pct_does_not_double_fire(db):
    _seed_challenge(db, "ch1", "WORK", 200)
    # First poll: cross 50%
    update_weekly_progress(db, "player_default", {"WORK": 100})
    # Second poll: more XP (but 50% already crossed)
    update_weekly_progress(db, "player_default", {"WORK": 50})
    assert _count_notifs(db, "challenge_progress") == 1


def test_no_progress_notif_when_already_completed(db):
    _seed_challenge(db, "ch1", "WORK", 100)
    # Cross 100% in one shot — should fire challenge_complete but NOT challenge_progress (50%)
    update_weekly_progress(db, "player_default", {"WORK": 100})
    assert _count_notifs(db, "challenge_progress") == 0
    assert _count_notifs(db, "challenge_complete") == 1


def test_completion_still_fires_after_50pct(db):
    _seed_challenge(db, "ch1", "WORK", 100)
    # Cross 50% first
    update_weekly_progress(db, "player_default", {"WORK": 50})
    assert _count_notifs(db, "challenge_progress") == 1
    # Then complete it
    update_weekly_progress(db, "player_default", {"WORK": 50})
    assert _count_notifs(db, "challenge_complete") == 1


def test_payload_shape(db):
    _seed_challenge(db, "ch1", "WORK", 200)
    update_weekly_progress(db, "player_default", {"WORK": 100})
    notif = _get_progress_notifs(db)[0]
    assert "challenge_id" in notif
    assert "name" in notif
    assert notif["pct"] == 50


def test_multiple_challenges_independent(db):
    _seed_challenge(db, "ch1", "WORK", 200)
    _seed_challenge(db, "ch2", "LEARN", 200)
    # Only cross 50% on ch1
    update_weekly_progress(db, "player_default", {"WORK": 100})
    notifs = _get_progress_notifs(db)
    assert len(notifs) == 1
    assert notifs[0]["challenge_id"] == "ch1"


def test_no_notif_when_no_xp(db):
    _seed_challenge(db, "ch1", "WORK", 200)
    update_weekly_progress(db, "player_default", {})
    assert _count_notifs(db, "challenge_progress") == 0
