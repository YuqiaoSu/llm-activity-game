"""Tests for GET /stats/daily aggregation endpoint."""
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    import json
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


def _ts(days_ago: int, hour: int = 10) -> str:
    """ISO timestamp for `days_ago` days before now at the given hour."""
    dt = datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0)
    dt -= timedelta(days=days_ago)
    return dt.isoformat()


def _insert_chunk(db, category: str, xp: int, duration_sec: int, days_ago: int = 0) -> None:
    db.execute(
        "INSERT OR IGNORE INTO chunk_log "
        "(log_id, chunk_id, category, xp_awarded, duration_sec, processed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category, xp, duration_sec, _ts(days_ago)),
    )
    db.commit()


# ── basic shape ───────────────────────────────────────────────────────────────

def test_empty_chunk_log_returns_empty_list(client):
    r = client.get("/stats/daily")
    assert r.status_code == 200
    assert r.json() == []


def test_single_chunk_returns_one_entry(client, db):
    _insert_chunk(db, "WORK", 30, 1800, days_ago=0)
    r = client.get("/stats/daily")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["total_xp"] == 30
    assert entry["total_duration_sec"] == 1800
    assert "WORK" in entry["categories"]
    assert entry["categories"]["WORK"] == 30
    assert "date" in entry


def test_entry_shape_has_required_keys(client, db):
    _insert_chunk(db, "WORK", 10, 600, days_ago=0)
    entry = client.get("/stats/daily").json()[0]
    assert set(entry.keys()) == {"date", "total_xp", "total_duration_sec", "categories"}


# ── aggregation ───────────────────────────────────────────────────────────────

def test_multiple_chunks_same_day_aggregate(client, db):
    _insert_chunk(db, "WORK", 20, 1200, days_ago=0)
    _insert_chunk(db, "WORK", 10, 600, days_ago=0)
    r = client.get("/stats/daily")
    data = r.json()
    assert len(data) == 1
    assert data[0]["total_xp"] == 30
    assert data[0]["total_duration_sec"] == 1800
    assert data[0]["categories"]["WORK"] == 30


def test_multiple_categories_same_day(client, db):
    _insert_chunk(db, "WORK", 20, 1200, days_ago=0)
    _insert_chunk(db, "CREATIVE", 15, 900, days_ago=0)
    entry = client.get("/stats/daily").json()[0]
    assert entry["total_xp"] == 35
    assert entry["categories"]["WORK"] == 20
    assert entry["categories"]["CREATIVE"] == 15


def test_multiple_days_returns_separate_entries(client, db):
    _insert_chunk(db, "WORK", 30, 1800, days_ago=0)
    _insert_chunk(db, "WORK", 20, 1200, days_ago=1)
    r = client.get("/stats/daily")
    data = r.json()
    assert len(data) == 2
    # Newest first
    assert data[0]["total_xp"] == 30
    assert data[1]["total_xp"] == 20


def test_results_ordered_newest_first(client, db):
    for ago in [3, 1, 2]:
        _insert_chunk(db, "WORK", ago * 10, ago * 600, days_ago=ago)
    dates = [e["date"] for e in client.get("/stats/daily").json()]
    assert dates == sorted(dates, reverse=True)


# ── days parameter ────────────────────────────────────────────────────────────

def test_days_param_excludes_old_entries(client, db):
    _insert_chunk(db, "WORK", 30, 1800, days_ago=0)
    _insert_chunk(db, "WORK", 20, 1200, days_ago=8)   # outside default 7-day window
    data = client.get("/stats/daily?days=7").json()
    assert len(data) == 1
    assert data[0]["total_xp"] == 30


def test_days_param_includes_all_within_window(client, db):
    for ago in range(7):
        _insert_chunk(db, "WORK", 10, 600, days_ago=ago)
    data = client.get("/stats/daily?days=7").json()
    assert len(data) == 7
