"""Tests for XP decay and recovery-bonus mechanic."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.progression.decay import (
    DORMANCY_THRESHOLD_DAYS,
    apply_daily_decay,
    consume_recovery_bonus,
    get_dormancy_info,
    mark_recovery_if_dormant,
)
from services.storage.db import init_db


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)  # runs migrations including decay.migrate
    visual = json.dumps({
        "base_sprite": "x.png", "evolution_stage": 0,
        "skin": None, "accessories": [], "anim_state": "idle",
    })
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def _set_last_active(db, days_ago: int) -> None:
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    db.execute("UPDATE streak_state SET last_active_date=? WHERE player_id='default'", (d,))
    db.commit()


def _add_xp(db, category: str, xp: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp) VALUES ('player_default', ?, ?)",
        (category, xp),
    )
    db.commit()


# ── get_dormancy_info ─────────────────────────────────────────────────────────

def test_no_activity_not_dormant(db):
    # NULL last_active_date means the player is brand-new — not dormant
    info = get_dormancy_info(db)
    assert info["is_dormant"] is False
    assert info["dormant_days"] == 0


def test_recent_activity_not_dormant(db):
    _set_last_active(db, 1)
    info = get_dormancy_info(db)
    assert info["is_dormant"] is False
    assert info["dormant_days"] == 1


def test_exactly_threshold_days_is_dormant(db):
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS)
    info = get_dormancy_info(db)
    assert info["is_dormant"] is True


def test_one_day_before_threshold_is_active(db):
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS - 1)
    info = get_dormancy_info(db)
    assert info["is_dormant"] is False


def test_dormant_days_count(db):
    _set_last_active(db, 5)
    info = get_dormancy_info(db)
    assert info["dormant_days"] == 5


# ── apply_daily_decay ─────────────────────────────────────────────────────────

def test_decay_reduces_xp_when_dormant(db):
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS)
    _add_xp(db, "focus", 1000)
    applied = apply_daily_decay(db)
    assert applied == 1
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='focus'"
    ).fetchone()
    assert row["xp"] < 1000   # must have decayed
    assert row["xp"] == 950   # 5% of 1000 removed → 950


def test_decay_not_applied_when_active(db):
    _set_last_active(db, 1)
    _add_xp(db, "focus", 1000)
    applied = apply_daily_decay(db)
    assert applied == 0
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='focus'"
    ).fetchone()
    assert row["xp"] == 1000


def test_decay_idempotent_same_day(db):
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS)
    _add_xp(db, "focus", 1000)
    apply_daily_decay(db)
    xp_after_first = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='focus'"
    ).fetchone()["xp"]
    apply_daily_decay(db)
    xp_after_second = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='focus'"
    ).fetchone()["xp"]
    assert xp_after_first == xp_after_second   # second call is no-op


def test_decay_floored_at_zero(db):
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS)
    _add_xp(db, "focus", 1)
    apply_daily_decay(db)
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='focus'"
    ).fetchone()
    assert row["xp"] >= 0


# ── mark_recovery_if_dormant / consume_recovery_bonus ────────────────────────

def test_mark_recovery_sets_flag_when_dormant(db):
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS)
    marked = mark_recovery_if_dormant(db)
    assert marked is True
    info = get_dormancy_info(db)
    assert info["has_recovery_bonus"] is True


def test_mark_recovery_does_not_set_flag_when_active(db):
    _set_last_active(db, 1)
    marked = mark_recovery_if_dormant(db)
    assert marked is False


def test_consume_recovery_clears_flag(db):
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS)
    mark_recovery_if_dormant(db)
    consumed = consume_recovery_bonus(db)
    assert consumed is True
    info = get_dormancy_info(db)
    assert info["has_recovery_bonus"] is False


def test_consume_recovery_returns_false_when_no_bonus(db):
    consumed = consume_recovery_bonus(db)
    assert consumed is False


def test_mark_recovery_idempotent(db):
    """Second call when flag already set should return False (no double-set)."""
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS)
    mark_recovery_if_dormant(db)
    marked_again = mark_recovery_if_dormant(db)
    assert marked_again is False


# ── profile API returns dormancy fields ──────────────────────────────────────

def test_profile_includes_dormancy_fields(db, client):
    _set_last_active(db, 1)
    resp = client.get("/player/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert "is_dormant" in body
    assert "dormant_days" in body
    assert "has_recovery_bonus" in body


def test_profile_dormancy_reflects_state(db, client):
    _set_last_active(db, DORMANCY_THRESHOLD_DAYS)
    resp = client.get("/player/profile")
    body = resp.json()
    assert body["is_dormant"] is True
    assert body["dormant_days"] >= DORMANCY_THRESHOLD_DAYS


def test_profile_not_dormant_when_active(db, client):
    _set_last_active(db, 1)
    resp = client.get("/player/profile")
    body = resp.json()
    assert body["is_dormant"] is False
