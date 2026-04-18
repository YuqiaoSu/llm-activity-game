"""Tests for GET /challenges/leaderboard?challenge_id=X."""
import json
import sqlite3

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
    # Seed one challenge with threshold=100
    conn.execute(
        """
        INSERT INTO weekly_challenges
            (challenge_id, name, description, category, metric, threshold)
        VALUES ('chal_test', 'Test Challenge', 'Do the thing', 'WORK', 'xp', 100)
        """
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app = create_app()
    app.state.db = db
    return TestClient(app)


def _set_progress(db, challenge_id: str, progress: int) -> None:
    from services.progression.weekly_challenges import get_week_start
    from datetime import datetime, timezone
    week_start = get_week_start(datetime.now(timezone.utc))
    db.execute(
        """
        INSERT INTO player_weekly_progress
            (player_id, challenge_id, week_start, progress, completed, reward_given)
        VALUES ('player_default', ?, ?, ?, 0, 0)
        ON CONFLICT (player_id, challenge_id, week_start)
        DO UPDATE SET progress=excluded.progress
        """,
        (challenge_id, week_start, progress),
    )
    db.commit()


# ── basic shape ──────────────────────────────────────────────────────────────

def test_returns_404_for_unknown_challenge(client):
    resp = client.get("/challenges/leaderboard?challenge_id=no_such")
    assert resp.status_code == 404


def test_response_contains_challenge_id(client):
    resp = client.get("/challenges/leaderboard?challenge_id=chal_test")
    assert resp.status_code == 200
    assert resp.json()["challenge_id"] == "chal_test"


def test_response_contains_threshold(client):
    resp = client.get("/challenges/leaderboard?challenge_id=chal_test")
    assert resp.json()["threshold"] == 100


def test_player_score_is_zero_with_no_progress(client):
    resp = client.get("/challenges/leaderboard?challenge_id=chal_test")
    assert resp.json()["player_score"] == 0


def test_player_score_matches_recorded_progress(client, db):
    _set_progress(db, "chal_test", 42)
    resp = client.get("/challenges/leaderboard?challenge_id=chal_test")
    assert resp.json()["player_score"] == 42


# ── ghost players ────────────────────────────────────────────────────────────

def test_ghosts_list_has_three_entries(client):
    ghosts = client.get("/challenges/leaderboard?challenge_id=chal_test").json()["ghosts"]
    assert len(ghosts) == 3


def test_ghost_entry_shape(client):
    ghost = client.get("/challenges/leaderboard?challenge_id=chal_test").json()["ghosts"][0]
    for key in ("player_id", "name", "score", "rank"):
        assert key in ghost


def test_ghost_scores_are_proportional_to_threshold(client):
    """Grinder score > Focus score > Casual score."""
    ghosts_by_id = {
        g["player_id"]: g
        for g in client.get("/challenges/leaderboard?challenge_id=chal_test").json()["ghosts"]
    }
    assert ghosts_by_id["ghost_grinder"]["score"] > ghosts_by_id["ghost_focus"]["score"]
    assert ghosts_by_id["ghost_focus"]["score"] > ghosts_by_id["ghost_casual"]["score"]


def test_ghost_scores_capped_at_threshold(client):
    """Grinder fraction=1.10 → score must not exceed threshold."""
    ghosts = client.get("/challenges/leaderboard?challenge_id=chal_test").json()["ghosts"]
    threshold = client.get("/challenges/leaderboard?challenge_id=chal_test").json()["threshold"]
    for g in ghosts:
        assert g["score"] <= threshold


# ── ranking ──────────────────────────────────────────────────────────────────

def test_total_entries_is_four(client):
    assert client.get("/challenges/leaderboard?challenge_id=chal_test").json()["total_entries"] == 4


def test_your_rank_last_when_no_progress(client):
    """With 0 progress the player should rank behind all ghosts (rank 4 or tied last)."""
    data = client.get("/challenges/leaderboard?challenge_id=chal_test").json()
    max_ghost_rank = max(g["rank"] for g in data["ghosts"])
    assert data["your_rank"] >= max_ghost_rank


def test_your_rank_first_when_above_all_ghosts(client, db):
    """Player with threshold progress (100) beats all ghosts and ranks 1st."""
    _set_progress(db, "chal_test", 100)
    data = client.get("/challenges/leaderboard?challenge_id=chal_test").json()
    assert data["your_rank"] == 1
