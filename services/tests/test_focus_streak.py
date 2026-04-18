"""Tests for focus streak — update_focus_streak, get_focus_streak, GET /player/focus-streak."""
import json
import sqlite3
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db
from services.progression.focus_streak import (
    update_focus_streak,
    get_focus_streak,
    has_focus_chunks,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def _set_focus_state(db, streak: int, last_date: str | None) -> None:
    db.execute(
        "UPDATE streak_state SET focus_streak=?, last_focus_date=? WHERE player_id='default'",
        (streak, last_date),
    )
    db.commit()


# ── has_focus_chunks helper ───────────────────────────────────────────────────

def test_has_focus_chunks_work():
    assert has_focus_chunks([{"label": "WORK", "confidence": 0.9}]) is True


def test_has_focus_chunks_learn():
    assert has_focus_chunks([{"label": "LEARN", "confidence": 0.8}]) is True


def test_has_focus_chunks_false_for_social():
    assert has_focus_chunks([{"label": "SOCIAL", "confidence": 0.9}]) is False


def test_has_focus_chunks_empty():
    assert has_focus_chunks([]) is False


# ── update_focus_streak ───────────────────────────────────────────────────────

def test_focus_streak_starts_at_1_on_first_focus(db):
    update_focus_streak(db, True)
    db.commit()
    assert get_focus_streak(db)["focus_streak"] == 1


def test_focus_streak_increments_on_consecutive_day(db):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _set_focus_state(db, 3, yesterday)
    update_focus_streak(db, True)
    db.commit()
    assert get_focus_streak(db)["focus_streak"] == 4


def test_focus_streak_resets_on_gap(db):
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()
    _set_focus_state(db, 5, two_days_ago)
    update_focus_streak(db, True)
    db.commit()
    assert get_focus_streak(db)["focus_streak"] == 1


def test_focus_streak_idempotent_same_day(db):
    today = date.today().isoformat()
    _set_focus_state(db, 3, today)
    update_focus_streak(db, True)
    db.commit()
    assert get_focus_streak(db)["focus_streak"] == 3


def test_non_focus_session_does_not_increment(db):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _set_focus_state(db, 2, yesterday)
    update_focus_streak(db, False)
    db.commit()
    assert get_focus_streak(db)["focus_streak"] == 2


# ── GET /player/focus-streak ──────────────────────────────────────────────────

def test_focus_streak_endpoint_returns_200(client):
    assert client.get("/player/focus-streak").status_code == 200


def test_focus_streak_endpoint_shape(client):
    data = client.get("/player/focus-streak").json()
    for key in ("focus_streak", "last_focus_date", "next_reward_at"):
        assert key in data


def test_focus_streak_endpoint_default_zero(client):
    data = client.get("/player/focus-streak").json()
    assert data["focus_streak"] == 0


def test_focus_streak_next_reward_at_when_below_milestone(client):
    data = client.get("/player/focus-streak").json()
    assert data["next_reward_at"] == 5


def test_focus_streak_next_reward_at_null_when_at_milestone(client, db):
    _set_focus_state(db, 5, date.today().isoformat())
    data = client.get("/player/focus-streak").json()
    assert data["next_reward_at"] is None


# ── ProfileCard UI signal wired (smoke test via GameAPI state) ────────────────

def test_focus_streak_stored_after_update(db):
    update_focus_streak(db, True)
    db.commit()
    result = get_focus_streak(db)
    assert result["focus_streak"] >= 1
    assert result["last_focus_date"] == date.today().isoformat()
