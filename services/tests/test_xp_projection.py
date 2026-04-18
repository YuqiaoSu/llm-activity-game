"""Tests for GET /player/xp-projection."""
import json
import math
import sqlite3
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db
from services.progression.xp import compute_level_xp_range, compute_level


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def _add_chunk_xp(db, xp: int, days_ago: int = 0) -> None:
    ts = (date.today() - timedelta(days=days_ago)).isoformat() + "T12:00:00"
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)"
        " VALUES (?, ?, 'WORK', ?, 60, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), xp, ts),
    )
    db.commit()


def _set_total_xp(db, xp: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp)"
        " VALUES ('player_default', 'WORK', ?)",
        (xp,),
    )
    db.commit()


# ── Shape and basics ──────────────────────────────────────────────────────────

def test_projection_returns_200(client):
    assert client.get("/player/xp-projection").status_code == 200


def test_projection_shape_no_activity(client):
    data = client.get("/player/xp-projection").json()
    for key in ("at_max_level", "xp_to_next_level", "avg_daily_xp", "eta_days", "eta_date"):
        assert key in data


def test_projection_eta_null_when_no_activity(client):
    data = client.get("/player/xp-projection").json()
    assert data["eta_days"] is None
    assert data["eta_date"] is None


def test_projection_avg_daily_zero_when_no_chunks(client):
    data = client.get("/player/xp-projection").json()
    assert data["avg_daily_xp"] == 0.0


# ── With activity ─────────────────────────────────────────────────────────────

def test_projection_eta_computed_with_activity(client, db):
    for _ in range(7):
        _add_chunk_xp(db, 100)
    data = client.get("/player/xp-projection").json()
    assert data["eta_days"] is not None
    assert data["eta_days"] > 0


def test_projection_avg_daily_correct(client, db):
    _add_chunk_xp(db, 700, days_ago=0)  # all in one day, 7-day avg = 100
    data = client.get("/player/xp-projection").json()
    assert data["avg_daily_xp"] == pytest.approx(100.0, abs=1.0)


def test_projection_xp_to_next_level_correct(client, db):
    total_xp = 0  # fresh player
    level = compute_level(total_xp)
    _, end = compute_level_xp_range(level)
    expected = end - total_xp if end is not None else 0
    data = client.get("/player/xp-projection").json()
    assert data["xp_to_next_level"] == expected


def test_projection_eta_date_in_future(client, db):
    _add_chunk_xp(db, 100, days_ago=0)
    data = client.get("/player/xp-projection").json()
    if data["eta_date"] is not None:
        assert data["eta_date"] >= date.today().isoformat()


def test_old_chunks_excluded_from_window(client, db):
    _add_chunk_xp(db, 10000, days_ago=8)  # outside 7-day window
    data = client.get("/player/xp-projection").json()
    assert data["avg_daily_xp"] == 0.0


def test_projection_at_max_level_flag(client, db):
    _set_total_xp(db, 999999)
    data = client.get("/player/xp-projection").json()
    # If at max level, flag is True; otherwise level < max
    level = compute_level(999999)
    _, end = compute_level_xp_range(level)
    if end is None:
        assert data["at_max_level"] is True
    else:
        assert data["at_max_level"] is False
