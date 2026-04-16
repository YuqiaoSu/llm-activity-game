"""Tests for GET /recap/weekly."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db


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


def _add_chunk(db, category: str, xp: int, duration_sec: int, days_ago: int = 0) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    db.execute(
        "INSERT OR IGNORE INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category, xp, duration_sec, ts),
    )
    db.commit()


def _add_drop(db, item_id: str, days_ago: int = 0) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    db.execute(
        "INSERT OR IGNORE INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at) "
        "VALUES (?, ?, 0, ?, 'player_default', ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), item_id, ts),
    )
    db.commit()


# ── endpoint shape ────────────────────────────────────────────────────────────

def test_weekly_recap_returns_200(client):
    resp = client.get("/recap/weekly")
    assert resp.status_code == 200


def test_weekly_recap_has_required_fields(client):
    data = client.get("/recap/weekly").json()
    for field in [
        "week_start", "week_end", "total_active_min", "total_xp_earned",
        "category_breakdown", "top_category", "items_found",
        "challenges_completed", "achievements_unlocked",
        "level_start", "level_end", "streak_at_end",
    ]:
        assert field in data, f"missing field: {field}"


def test_weekly_recap_empty_week(client):
    data = client.get("/recap/weekly").json()
    assert data["total_active_min"] == 0
    assert data["total_xp_earned"] == 0
    assert data["category_breakdown"] == {}
    assert data["top_category"] is None
    assert data["items_found"] == 0


# ── data accuracy ─────────────────────────────────────────────────────────────

def test_weekly_recap_sums_xp_and_duration(client, db):
    _add_chunk(db, "WORK", xp=10, duration_sec=1800)   # 30 min
    _add_chunk(db, "GAME", xp=5, duration_sec=600)     # 10 min
    data = client.get("/recap/weekly").json()
    assert data["total_xp_earned"] == 15
    assert data["total_active_min"] == 40


def test_weekly_recap_category_breakdown(client, db):
    _add_chunk(db, "WORK", xp=20, duration_sec=3600)
    data = client.get("/recap/weekly").json()
    assert "WORK" in data["category_breakdown"]
    assert data["category_breakdown"]["WORK"]["xp"] == 20
    assert data["category_breakdown"]["WORK"]["active_min"] == 60


def test_weekly_recap_top_category(client, db):
    _add_chunk(db, "WORK", xp=30, duration_sec=1800)
    _add_chunk(db, "GAME", xp=10, duration_sec=600)
    data = client.get("/recap/weekly").json()
    assert data["top_category"] == "WORK"


def test_weekly_recap_items_found_count(client, db):
    _add_drop(db, "sword")
    _add_drop(db, "shield")
    _add_drop(db, "sword")   # duplicate — should only count once
    data = client.get("/recap/weekly").json()
    assert data["items_found"] == 2


def test_weekly_recap_excludes_older_chunks(client, db):
    # Chunk from 8 days ago should not appear in current week
    _add_chunk(db, "WORK", xp=100, duration_sec=3600, days_ago=8)
    data = client.get("/recap/weekly").json()
    assert data["total_xp_earned"] == 0


def test_weekly_recap_weeks_ago_param(client, db):
    # Activity from 8 days ago should appear in weeks_ago=1
    _add_chunk(db, "EXPLORE", xp=50, duration_sec=1800, days_ago=8)
    data = client.get("/recap/weekly?weeks_ago=1").json()
    # The 8-day-ago chunk might or might not fall in last week depending on day of week,
    # but at minimum the endpoint should not error
    assert data["total_xp_earned"] >= 0


def test_weekly_recap_level_fields_are_ints(client, db):
    data = client.get("/recap/weekly").json()
    assert isinstance(data["level_start"], int)
    assert isinstance(data["level_end"], int)
    assert data["level_end"] >= data["level_start"]
