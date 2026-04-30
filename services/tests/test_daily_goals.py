"""Tests for daily goals — ensure_daily_goals, update_daily_goal_progress, GET /goals/daily."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db
from services.progression.daily_goals import (
    ensure_daily_goals,
    update_daily_goal_progress,
    get_daily_goals,
    _today,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
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


def _add_xp(db, category: str, xp: int) -> None:
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', ?, ?) "
        "ON CONFLICT (character_id, category) DO UPDATE SET xp = xp + excluded.xp",
        (category, xp),
    )
    db.commit()


# ── ensure_daily_goals ────────────────────────────────────────────────────────

def test_ensure_creates_goals_when_none_exist(db):
    _add_xp(db, "WORK", 100)   # triggers a gap suggestion
    ensure_daily_goals(db)
    rows = db.execute("SELECT * FROM daily_goals WHERE date=?", (_today(),)).fetchall()
    assert len(rows) > 0


def test_ensure_is_idempotent(db):
    _add_xp(db, "WORK", 100)
    ensure_daily_goals(db)
    ensure_daily_goals(db)   # second call should be no-op
    rows = db.execute("SELECT * FROM daily_goals WHERE date=?", (_today(),)).fetchall()
    first_count = len(rows)
    assert first_count > 0
    # call again and confirm count doesn't grow
    ensure_daily_goals(db)
    rows2 = db.execute("SELECT * FROM daily_goals WHERE date=?", (_today(),)).fetchall()
    assert len(rows2) == first_count


def test_ensure_max_three_goals(db):
    for cat in ["WORK", "GAME", "EXPLORE", "SOCIAL"]:
        _add_xp(db, cat, 100)
    ensure_daily_goals(db)
    rows = db.execute("SELECT * FROM daily_goals WHERE date=?", (_today(),)).fetchall()
    assert len(rows) <= 3


def test_ensure_goals_have_positive_target_sec(db):
    _add_xp(db, "EXPLORE", 50)
    ensure_daily_goals(db)
    rows = db.execute("SELECT target_sec FROM daily_goals WHERE date=?", (_today(),)).fetchall()
    for r in rows:
        assert r["target_sec"] > 0


# ── update_daily_goal_progress ────────────────────────────────────────────────

def test_update_adds_progress_seconds(db):
    _add_xp(db, "WORK", 100)
    ensure_daily_goals(db)
    # Check if WORK goal exists
    row = db.execute("SELECT goal_id FROM daily_goals WHERE date=? AND category='WORK'",
                     (_today(),)).fetchone()
    if row is None:
        pytest.skip("WORK goal not generated (suggestion engine chose other categories)")
    update_daily_goal_progress(db, "WORK", 600)
    db.commit()
    updated = db.execute("SELECT progress_sec FROM daily_goals WHERE date=? AND category='WORK'",
                         (_today(),)).fetchone()
    assert updated["progress_sec"] == 600


def test_update_marks_completed_when_target_reached(db):
    _add_xp(db, "GAME", 100)
    ensure_daily_goals(db)
    row = db.execute("SELECT goal_id, target_sec FROM daily_goals WHERE date=? AND category='GAME'",
                     (_today(),)).fetchone()
    if row is None:
        pytest.skip("GAME goal not generated")
    target = row["target_sec"]
    update_daily_goal_progress(db, "GAME", target)
    db.commit()
    result = db.execute("SELECT completed FROM daily_goals WHERE date=? AND category='GAME'",
                        (_today(),)).fetchone()
    assert result["completed"] == 1


def test_update_noop_for_category_without_goal(db):
    # No goals created — update should be safe to call
    update_daily_goal_progress(db, "SLEEP", 3600)
    db.commit()
    rows = db.execute("SELECT * FROM daily_goals").fetchall()
    assert len(rows) == 0


# ── get_daily_goals ───────────────────────────────────────────────────────────

def test_get_daily_goals_returns_list(db):
    result = get_daily_goals(db)
    assert isinstance(result, list)


def test_get_daily_goals_fields(db):
    _add_xp(db, "WORK", 200)
    ensure_daily_goals(db)
    goals = get_daily_goals(db)
    if not goals:
        pytest.skip("No goals generated")
    for g in goals:
        assert "goal_id" in g
        assert "category" in g
        assert "target_min" in g
        assert "progress_min" in g
        assert "progress_pct" in g
        assert "completed" in g


def test_get_daily_goals_progress_pct_bounded(db):
    _add_xp(db, "EXPLORE", 100)
    ensure_daily_goals(db)
    goals = get_daily_goals(db)
    for g in goals:
        assert 0 <= g["progress_pct"] <= 100


# ── API endpoint ──────────────────────────────────────────────────────────────

def test_get_goals_daily_endpoint_returns_list(client):
    data = client.get("/goals/daily").json()
    assert isinstance(data, list)


def test_get_goals_daily_empty_when_no_goals(client):
    data = client.get("/goals/daily").json()
    assert data == []
