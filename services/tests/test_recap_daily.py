"""Tests for GET /recap/daily — daily activity digest endpoint."""
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_chunk(db, category: str, xp: int, dur_sec: int) -> None:
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category, xp, dur_sec, _now_iso()),
    )
    db.commit()


def _insert_drop(db, item_id: str) -> None:
    db.execute(
        "INSERT INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at) "
        "VALUES (?, ?, ?, ?, 'player_default', ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), 0, item_id, _now_iso()),
    )
    db.commit()


def _insert_goal(db, category: str, completed: bool) -> None:
    db.execute(
        "INSERT INTO daily_goals (goal_id, player_id, date, category, target_sec, progress_sec, completed, created_at) "
        "VALUES (?, 'player_default', date('now'), ?, 1800, ?, ?, ?)",
        (str(uuid.uuid4()), category, 1800 if completed else 0, 1 if completed else 0, _now_iso()),
    )
    db.commit()


# ── shape tests ───────────────────────────────────────────────────────────────

def test_daily_recap_empty_day_returns_zeros(client):
    tc, _ = client
    r = tc.get("/recap/daily")
    assert r.status_code == 200
    data = r.json()
    assert data["total_xp_earned"] == 0
    assert data["total_active_min"] == 0
    assert data["drops_earned"] == 0
    assert data["goals_completed"] == 0
    assert data["goals_total"] == 0
    assert data["top_category"] is None
    assert data["category_breakdown"] == {}


def test_daily_recap_response_shape(client):
    tc, _ = client
    r = tc.get("/recap/daily")
    data = r.json()
    for key in ("date", "total_active_min", "total_xp_earned", "category_breakdown",
                "top_category", "drops_earned", "goals_completed", "goals_total", "streak_days"):
        assert key in data


def test_daily_recap_date_is_today(client):
    tc, _ = client
    r = tc.get("/recap/daily")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert r.json()["date"] == today


# ── XP and activity ──────────────────────────────────────────────────────────

def test_daily_recap_xp_totals(client):
    tc, db = client
    _insert_chunk(db, "WORK", 50, 1800)
    _insert_chunk(db, "GAME", 30, 900)
    r = tc.get("/recap/daily")
    data = r.json()
    assert data["total_xp_earned"] == 80
    assert data["total_active_min"] == 45  # (1800 + 900) / 60


def test_daily_recap_category_breakdown(client):
    tc, db = client
    _insert_chunk(db, "WORK", 50, 1800)
    _insert_chunk(db, "GAME", 30, 600)
    r = tc.get("/recap/daily")
    bd = r.json()["category_breakdown"]
    assert bd["WORK"]["xp"] == 50
    assert bd["WORK"]["active_min"] == 30
    assert bd["GAME"]["xp"] == 30
    assert bd["GAME"]["active_min"] == 10


def test_daily_recap_top_category(client):
    tc, db = client
    _insert_chunk(db, "WORK", 100, 3600)
    _insert_chunk(db, "GAME", 40, 600)
    r = tc.get("/recap/daily")
    assert r.json()["top_category"] == "WORK"


# ── drops ────────────────────────────────────────────────────────────────────

def test_daily_recap_drops_counted(client):
    tc, db = client
    _insert_drop(db, "item_x")
    _insert_drop(db, "item_y")
    r = tc.get("/recap/daily")
    assert r.json()["drops_earned"] == 2


def test_daily_recap_drops_distinct_item_types(client):
    tc, db = client
    # Same item type twice → counts as 1 distinct
    _insert_drop(db, "item_x")
    _insert_drop(db, "item_x")
    r = tc.get("/recap/daily")
    assert r.json()["drops_earned"] == 1


# ── goals ────────────────────────────────────────────────────────────────────

def test_daily_recap_goals_counts(client):
    tc, db = client
    _insert_goal(db, "WORK", completed=True)
    _insert_goal(db, "GAME", completed=False)
    r = tc.get("/recap/daily")
    data = r.json()
    assert data["goals_total"] == 2
    assert data["goals_completed"] == 1


# ── streak ───────────────────────────────────────────────────────────────────

def test_daily_recap_streak_reflects_current(client):
    tc, db = client
    db.execute("UPDATE streak_state SET current_streak=5 WHERE player_id='default'")
    db.commit()
    r = tc.get("/recap/daily")
    assert r.json()["streak_days"] == 5
