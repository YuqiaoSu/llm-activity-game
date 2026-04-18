"""Tests for GET /challenges/history?weeks=N — weekly challenge completion history."""
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
    # Seed 2 challenges
    conn.executemany(
        "INSERT INTO weekly_challenges (challenge_id, name, description, category, metric, threshold)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("chal_a", "Challenge A", "Desc A", "WORK", "xp", 100),
            ("chal_b", "Challenge B", "Desc B", "GAME", "xp", 50),
        ],
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app = create_app()
    app.state.db = db
    return TestClient(app)


def _insert_progress(db, week_start: str, challenge_id: str, completed: bool) -> None:
    db.execute(
        """
        INSERT INTO player_weekly_progress
            (player_id, challenge_id, week_start, progress, completed, reward_given)
        VALUES ('player_default', ?, ?, ?, ?, 0)
        ON CONFLICT DO NOTHING
        """,
        (challenge_id, week_start, 100 if completed else 0, 1 if completed else 0),
    )
    db.commit()


# ── basic behaviour ───────────────────────────────────────────────────────────

def test_returns_list(client):
    resp = client.get("/challenges/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_empty_when_no_history(client):
    assert client.get("/challenges/history").json() == []


def test_entry_shape(client, db):
    _insert_progress(db, "2026-04-14", "chal_a", True)
    entry = client.get("/challenges/history").json()[0]
    for key in ("week_start", "completed_count", "total_count", "all_complete"):
        assert key in entry


def test_week_start_matches_inserted(client, db):
    _insert_progress(db, "2026-04-14", "chal_a", False)
    data = client.get("/challenges/history").json()
    assert data[0]["week_start"] == "2026-04-14"


# ── counting ─────────────────────────────────────────────────────────────────

def test_completed_count_when_one_done(client, db):
    _insert_progress(db, "2026-04-14", "chal_a", True)
    _insert_progress(db, "2026-04-14", "chal_b", False)
    data = client.get("/challenges/history").json()
    assert data[0]["completed_count"] == 1


def test_completed_count_when_none_done(client, db):
    _insert_progress(db, "2026-04-14", "chal_a", False)
    data = client.get("/challenges/history").json()
    assert data[0]["completed_count"] == 0


def test_total_count_equals_seeded_challenges(client, db):
    _insert_progress(db, "2026-04-14", "chal_a", True)
    data = client.get("/challenges/history").json()
    assert data[0]["total_count"] == 2


# ── all_complete flag ────────────────────────────────────────────────────────

def test_all_complete_false_when_partial(client, db):
    _insert_progress(db, "2026-04-14", "chal_a", True)
    _insert_progress(db, "2026-04-14", "chal_b", False)
    data = client.get("/challenges/history").json()
    assert data[0]["all_complete"] is False


def test_all_complete_true_when_all_done(client, db):
    _insert_progress(db, "2026-04-14", "chal_a", True)
    _insert_progress(db, "2026-04-14", "chal_b", True)
    data = client.get("/challenges/history").json()
    assert data[0]["all_complete"] is True


# ── multiple weeks ────────────────────────────────────────────────────────────

def test_multiple_weeks_returned_newest_first(client, db):
    _insert_progress(db, "2026-04-07", "chal_a", True)
    _insert_progress(db, "2026-04-14", "chal_a", True)
    data = client.get("/challenges/history").json()
    assert len(data) == 2
    assert data[0]["week_start"] > data[1]["week_start"]


def test_weeks_param_limits_results(client, db):
    for week in ["2026-03-31", "2026-04-07", "2026-04-14"]:
        _insert_progress(db, week, "chal_a", True)
    data = client.get("/challenges/history?weeks=2").json()
    assert len(data) == 2
