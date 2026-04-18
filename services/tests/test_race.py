"""Tests for GET /leaderboard/race — per-category weekly XP race vs ghost."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db


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
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app = create_app(db=db)
    return TestClient(app), db


def _insert_chunk(db, category: str, xp: int) -> None:
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)"
        " VALUES (?, ?, ?, ?, 600, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category, xp, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


# ── shape tests ───────────────────────────────────────────────────────────────

def test_race_response_shape(client):
    tc, _ = client
    r = tc.get("/leaderboard/race?other_id=ghost_casual")
    assert r.status_code == 200
    data = r.json()
    for key in ("other_name", "other_id", "categories", "you_wins", "other_wins"):
        assert key in data


def test_race_categories_all_present(client):
    tc, _ = client
    r = tc.get("/leaderboard/race?other_id=ghost_casual")
    cats = [e["category"] for e in r.json()["categories"]]
    for cat in ("WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"):
        assert cat in cats


def test_race_category_entry_shape(client):
    tc, _ = client
    r = tc.get("/leaderboard/race?other_id=ghost_casual")
    entry = r.json()["categories"][0]
    for key in ("category", "your_xp", "their_xp", "leader"):
        assert key in entry


# ── 404 for unknown ghost ─────────────────────────────────────────────────────

def test_race_unknown_ghost_returns_404(client):
    tc, _ = client
    r = tc.get("/leaderboard/race?other_id=nobody")
    assert r.status_code == 404


# ── leader logic ──────────────────────────────────────────────────────────────

def test_race_you_lead_when_more_xp_in_category(client):
    tc, db = client
    # ghost_casual has GAME=60 this week; player earns 100
    _insert_chunk(db, "GAME", 100)
    r = tc.get("/leaderboard/race?other_id=ghost_casual")
    game_entry = next(e for e in r.json()["categories"] if e["category"] == "GAME")
    assert game_entry["leader"] == "you"
    assert game_entry["your_xp"] == 100


def test_race_other_leads_when_ghost_has_more(client):
    tc, _ = client
    # ghost_grinder has WORK=500; player has 0
    r = tc.get("/leaderboard/race?other_id=ghost_grinder")
    work_entry = next(e for e in r.json()["categories"] if e["category"] == "WORK")
    assert work_entry["leader"] == "other"
    assert work_entry["their_xp"] == 500


def test_race_tie_when_equal_xp(client):
    tc, db = client
    # ghost_casual has GAME=60; give player exactly 60
    _insert_chunk(db, "GAME", 60)
    r = tc.get("/leaderboard/race?other_id=ghost_casual")
    game_entry = next(e for e in r.json()["categories"] if e["category"] == "GAME")
    assert game_entry["leader"] == "tie"


def test_race_you_wins_count(client):
    tc, db = client
    # ghost_casual: GAME=60, SOCIAL=30, VIDEO=10, WORK=5, EXPLORE=5
    # Earn enough to beat all ghost_casual categories
    for cat, xp in [("GAME", 100), ("SOCIAL", 50), ("VIDEO", 20),
                    ("WORK", 10), ("EXPLORE", 10)]:
        _insert_chunk(db, cat, xp)
    r = tc.get("/leaderboard/race?other_id=ghost_casual")
    data = r.json()
    assert data["you_wins"] == 5  # beat 5 non-zero categories; SLEEP+SPECIAL are tie at 0


def test_race_other_name_matches_ghost(client):
    tc, _ = client
    r = tc.get("/leaderboard/race?other_id=ghost_focus")
    assert r.json()["other_name"] == "FocusBot"
    assert r.json()["other_id"] == "ghost_focus"


def test_race_empty_week_all_categories_other_or_tie(client):
    tc, _ = client
    # Player has 0 XP this week; ghost_grinder leads most categories
    r = tc.get("/leaderboard/race?other_id=ghost_grinder")
    data = r.json()
    assert data["you_wins"] == 0
    assert data["other_wins"] > 0
