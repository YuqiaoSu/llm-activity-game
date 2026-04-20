"""Tests for GET /goals/stats."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (_VISUAL,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _add_goal(db, goal_id: str, category: str, completed: int, date: str = "2025-01-01"):
    db.execute(
        "INSERT INTO daily_goals (goal_id, player_id, date, category, target_sec,"
        " progress_sec, completed, created_at)"
        " VALUES (?, 'player_default', ?, ?, 300, 0, ?, ?)",
        (goal_id, date, category, completed, date + "T00:00:00"),
    )
    db.commit()


def test_no_goals_returns_zeros(client):
    r = client.get("/goals/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_goals_set"] == 0
    assert body["total_completed"] == 0
    assert body["completion_rate_pct"] == 0.0
    assert body["by_category"] == []


def test_response_shape(client, db):
    _add_goal(db, "g1", "WORK", 1)
    r = client.get("/goals/stats")
    body = r.json()
    assert "total_goals_set" in body
    assert "total_completed" in body
    assert "completion_rate_pct" in body
    assert "by_category" in body
    assert "current_streak" in body
    assert "best_streak" in body


def test_completion_rate_pct_correct(client, db):
    _add_goal(db, "g1", "WORK", 1, "2025-01-01")
    _add_goal(db, "g2", "WORK", 0, "2025-01-02")
    body = client.get("/goals/stats").json()
    assert body["total_goals_set"] == 2
    assert body["total_completed"] == 1
    assert body["completion_rate_pct"] == 50.0


def test_by_category_grouping(client, db):
    _add_goal(db, "g1", "WORK",  1, "2025-01-01")
    _add_goal(db, "g2", "LEARN", 1, "2025-01-01")
    _add_goal(db, "g3", "LEARN", 0, "2025-01-02")
    body = client.get("/goals/stats").json()
    cats = {c["category"]: c for c in body["by_category"]}
    assert "WORK" in cats
    assert "LEARN" in cats
    assert cats["WORK"]["completed"] == 1
    assert cats["LEARN"]["completed"] == 1
    assert cats["LEARN"]["set"] == 2
    assert cats["LEARN"]["rate_pct"] == 50.0


def test_streak_included(client, db):
    db.execute(
        "UPDATE streak_state SET current_streak=5, longest_streak=10 WHERE player_id='default'"
    )
    db.commit()
    body = client.get("/goals/stats").json()
    assert body["current_streak"] == 5
    assert body["best_streak"] == 10


def test_all_completed_100pct(client, db):
    _add_goal(db, "g1", "WORK", 1, "2025-01-01")
    _add_goal(db, "g2", "WORK", 1, "2025-01-02")
    body = client.get("/goals/stats").json()
    assert body["completion_rate_pct"] == 100.0


def test_none_completed_0pct(client, db):
    _add_goal(db, "g1", "WORK", 0, "2025-01-01")
    _add_goal(db, "g2", "WORK", 0, "2025-01-02")
    body = client.get("/goals/stats").json()
    assert body["completion_rate_pct"] == 0.0
