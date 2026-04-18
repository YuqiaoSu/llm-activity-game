"""Tests for GET /leaderboard/compare — friend comparison stub."""
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


def _insert_xp(db, category: str, xp: int) -> None:
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', ?, ?)"
        " ON CONFLICT (character_id, category) DO UPDATE SET xp = xp + excluded.xp",
        (category, xp),
    )
    db.commit()


def _insert_chunk(db, category: str, xp: int) -> None:
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at) "
        "VALUES (?, ?, ?, ?, 600, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category, xp, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


# ── shape tests ───────────────────────────────────────────────────────────────

def test_compare_response_shape(client):
    tc, _ = client
    r = tc.get("/leaderboard/compare?other_id=ghost_casual")
    assert r.status_code == 200
    data = r.json()
    for key in ("you", "other", "winner", "available"):
        assert key in data
    for key in ("player_id", "name", "level", "total_xp", "weekly_xp", "streak_days"):
        assert key in data["you"]
        assert key in data["other"]


def test_compare_available_lists_all_ghosts(client):
    tc, _ = client
    r = tc.get("/leaderboard/compare?other_id=ghost_casual")
    avail = r.json()["available"]
    ids = [a["player_id"] for a in avail]
    assert "ghost_casual" in ids
    assert "ghost_focus" in ids
    assert "ghost_grinder" in ids


# ── 404 for unknown ghost ─────────────────────────────────────────────────────

def test_compare_unknown_other_returns_404(client):
    tc, _ = client
    r = tc.get("/leaderboard/compare?other_id=nobody")
    assert r.status_code == 404


# ── winner logic ──────────────────────────────────────────────────────────────

def test_compare_winner_you_when_more_xp(client):
    tc, db = client
    # ghost_casual has total_xp=850; give player 2000
    _insert_xp(db, "WORK", 2000)
    r = tc.get("/leaderboard/compare?other_id=ghost_casual")
    assert r.json()["winner"] == "you"


def test_compare_winner_other_when_less_xp(client):
    tc, _ = client
    # ghost_grinder has total_xp=9800; player starts at 0
    r = tc.get("/leaderboard/compare?other_id=ghost_grinder")
    assert r.json()["winner"] == "other"


def test_compare_winner_tie_when_equal_xp(client):
    tc, db = client
    # ghost_casual has total_xp=850
    _insert_xp(db, "WORK", 850)
    r = tc.get("/leaderboard/compare?other_id=ghost_casual")
    assert r.json()["winner"] == "tie"


# ── player data accuracy ──────────────────────────────────────────────────────

def test_compare_you_total_xp_reflects_real_data(client):
    tc, db = client
    _insert_xp(db, "WORK", 300)
    _insert_xp(db, "GAME", 200)
    r = tc.get("/leaderboard/compare?other_id=ghost_focus")
    assert r.json()["you"]["total_xp"] == 500


def test_compare_you_name_reflects_profile(client):
    tc, _ = client
    r = tc.get("/leaderboard/compare?other_id=ghost_focus")
    assert r.json()["you"]["name"] == "Tester"


def test_compare_you_weekly_xp_counts_chunks(client):
    tc, db = client
    _insert_chunk(db, "WORK", 150)
    _insert_chunk(db, "GAME", 50)
    r = tc.get("/leaderboard/compare?other_id=ghost_casual")
    assert r.json()["you"]["weekly_xp"] == 200


def test_compare_other_matches_ghost_data(client):
    tc, _ = client
    r = tc.get("/leaderboard/compare?other_id=ghost_focus")
    other = r.json()["other"]
    assert other["player_id"] == "ghost_focus"
    assert other["name"] == "FocusBot"
    assert other["level"] == 8
    assert other["total_xp"] == 3200
