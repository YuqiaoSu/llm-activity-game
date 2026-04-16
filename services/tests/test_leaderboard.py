"""Tests for GET /leaderboard/weekly."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db


def _monday_of(dt: datetime) -> datetime:
    return (dt - timedelta(days=dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _add_chunk(conn, xp: int, dur_sec: int, processed_at: str, category: str = "WORK") -> None:
    conn.execute(
        """
        INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), str(uuid.uuid4()), category, xp, dur_sec, processed_at),
    )


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    app = create_app(db=db)
    return TestClient(app)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ── basic shape ───────────────────────────────────────────────────────────────

def test_leaderboard_default_returns_8_weeks(client):
    r = client.get("/leaderboard/weekly")
    assert r.status_code == 200
    data = r.json()
    assert len(data["weeks"]) == 8


def test_leaderboard_weeks_param(client):
    r = client.get("/leaderboard/weekly?weeks=4")
    assert len(r.json()["weeks"]) == 4


def test_leaderboard_top_level_fields(client):
    data = client.get("/leaderboard/weekly").json()
    assert "personal_best_xp" in data
    assert "trend" in data
    assert "weeks" in data


def test_week_entry_shape(client):
    entry = client.get("/leaderboard/weekly").json()["weeks"][0]
    for field in ("week_start", "week_end", "total_xp", "total_active_min",
                  "is_current", "is_best", "rank"):
        assert field in entry, f"missing field: {field}"


def test_first_entry_is_current_week(client):
    entry = client.get("/leaderboard/weekly").json()["weeks"][0]
    assert entry["is_current"] is True


def test_only_one_current_week(client):
    weeks = client.get("/leaderboard/weekly").json()["weeks"]
    assert sum(1 for w in weeks if w["is_current"]) == 1


# ── XP aggregation ────────────────────────────────────────────────────────────

def test_current_week_xp_aggregated(client, db):
    now = datetime.now(timezone.utc)
    monday = _monday_of(now)
    _add_chunk(db, 50, 3000, _iso(monday + timedelta(hours=2)))
    _add_chunk(db, 30, 1800, _iso(monday + timedelta(hours=10)))
    db.commit()

    data = client.get("/leaderboard/weekly").json()
    current = next(w for w in data["weeks"] if w["is_current"])
    assert current["total_xp"] == 80
    assert current["total_active_min"] == 80  # (3000+1800)/60


def test_past_week_xp_isolated(client, db):
    now = datetime.now(timezone.utc)
    last_monday = _monday_of(now) - timedelta(weeks=1)
    _add_chunk(db, 200, 12000, _iso(last_monday + timedelta(hours=5)))
    db.commit()

    weeks = client.get("/leaderboard/weekly?weeks=3").json()["weeks"]
    prev = weeks[1]  # index 1 = last week
    assert prev["total_xp"] == 200


def test_empty_week_has_zero_xp(client):
    weeks = client.get("/leaderboard/weekly?weeks=3").json()["weeks"]
    for w in weeks:
        assert w["total_xp"] == 0


# ── is_best and rank ─────────────────────────────────────────────────────────

def test_is_best_marks_highest_xp_week(client, db):
    now = datetime.now(timezone.utc)
    last_monday = _monday_of(now) - timedelta(weeks=1)
    _add_chunk(db, 500, 30000, _iso(last_monday + timedelta(hours=6)))
    db.commit()

    weeks = client.get("/leaderboard/weekly").json()["weeks"]
    best_weeks = [w for w in weeks if w["is_best"]]
    assert len(best_weeks) == 1
    assert best_weeks[0]["total_xp"] == 500


def test_is_best_false_when_all_zero(client):
    weeks = client.get("/leaderboard/weekly").json()["weeks"]
    assert all(not w["is_best"] for w in weeks)


def test_rank_1_is_best_week(client, db):
    now = datetime.now(timezone.utc)
    _add_chunk(db, 100, 6000, _iso(_monday_of(now) + timedelta(hours=1)))
    _add_chunk(db, 300, 18000, _iso(_monday_of(now - timedelta(weeks=1)) + timedelta(hours=1)))
    db.commit()

    weeks = client.get("/leaderboard/weekly?weeks=3").json()["weeks"]
    rank1_weeks = [w for w in weeks if w["rank"] == 1]
    assert len(rank1_weeks) == 1
    assert rank1_weeks[0]["total_xp"] == 300


def test_personal_best_xp_matches_best_week(client, db):
    now = datetime.now(timezone.utc)
    _add_chunk(db, 150, 9000, _iso(_monday_of(now) + timedelta(hours=1)))
    db.commit()

    data = client.get("/leaderboard/weekly").json()
    assert data["personal_best_xp"] == 150


# ── trend ─────────────────────────────────────────────────────────────────────

def test_trend_up_when_current_beats_last(client, db):
    now = datetime.now(timezone.utc)
    _add_chunk(db, 200, 12000, _iso(_monday_of(now) + timedelta(hours=1)))
    _add_chunk(db, 100, 6000, _iso(_monday_of(now - timedelta(weeks=1)) + timedelta(hours=1)))
    db.commit()

    assert client.get("/leaderboard/weekly").json()["trend"] == "up"


def test_trend_down_when_current_trails_last(client, db):
    now = datetime.now(timezone.utc)
    _add_chunk(db, 50, 3000, _iso(_monday_of(now) + timedelta(hours=1)))
    _add_chunk(db, 200, 12000, _iso(_monday_of(now - timedelta(weeks=1)) + timedelta(hours=1)))
    db.commit()

    assert client.get("/leaderboard/weekly").json()["trend"] == "down"


def test_trend_flat_when_equal(client, db):
    now = datetime.now(timezone.utc)
    for week_offset in [0, 1]:
        _add_chunk(db, 100, 6000,
                   _iso(_monday_of(now - timedelta(weeks=week_offset)) + timedelta(hours=1)))
    db.commit()

    assert client.get("/leaderboard/weekly").json()["trend"] == "flat"


def test_trend_flat_when_no_activity(client):
    assert client.get("/leaderboard/weekly").json()["trend"] == "flat"
