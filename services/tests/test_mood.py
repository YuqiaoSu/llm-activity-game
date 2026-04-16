"""Tests for companion mood computation."""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.progression.mood import compute_mood
from services.storage.db import init_db


# ── pure unit tests ────────────────────────────────────────────────────────────

def test_happy_long_streak_active():
    assert compute_mood(streak=7, is_dormant=False, dormant_days=0) == "happy"


def test_happy_very_long_streak():
    assert compute_mood(streak=30, is_dormant=False, dormant_days=0) == "happy"


def test_neutral_short_streak():
    assert compute_mood(streak=3, is_dormant=False, dormant_days=0) == "neutral"


def test_neutral_no_streak():
    assert compute_mood(streak=0, is_dormant=False, dormant_days=0) == "neutral"


def test_neutral_streak_exactly_6():
    assert compute_mood(streak=6, is_dormant=False, dormant_days=0) == "neutral"


def test_sad_dormant_short():
    assert compute_mood(streak=0, is_dormant=True, dormant_days=4) == "sad"


def test_sad_dormant_just_below_threshold():
    assert compute_mood(streak=0, is_dormant=True, dormant_days=13) == "sad"


def test_anxious_dormant_at_threshold():
    assert compute_mood(streak=0, is_dormant=True, dormant_days=14) == "anxious"


def test_anxious_dormant_long():
    assert compute_mood(streak=0, is_dormant=True, dormant_days=60) == "anxious"


def test_dormant_overrides_high_streak():
    # Even if streak is high, dormancy takes precedence (streak is stale)
    assert compute_mood(streak=20, is_dormant=True, dormant_days=5) == "sad"


# ── API integration tests ──────────────────────────────────────────────────────

@pytest.fixture
def client():
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
    app = create_app(db=conn)
    return TestClient(app)


def test_profile_includes_mood_field(client):
    resp = client.get("/player/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "mood" in data
    assert data["mood"] in ("happy", "neutral", "sad", "anxious")


def test_profile_mood_default_is_neutral(client):
    # New player: no streak, no dormancy → neutral
    resp = client.get("/player/profile")
    assert resp.status_code == 200
    assert resp.json()["mood"] == "neutral"
