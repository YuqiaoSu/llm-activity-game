"""Tests for GET /history/calendar."""
import json
import sqlite3
import uuid
from datetime import date, timedelta

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


def _add_chunk(db, xp: int, days_ago: int = 0) -> None:
    ts = (date.today() - timedelta(days=days_ago)).isoformat() + "T12:00:00"
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)"
        " VALUES (?, ?, 'WORK', ?, 60, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), xp, ts),
    )
    db.commit()


# ── Shape ─────────────────────────────────────────────────────────────────────

def test_calendar_returns_200(client):
    assert client.get("/history/calendar").status_code == 200


def test_calendar_entry_shape(client, db):
    _add_chunk(db, 100)
    data = client.get("/history/calendar").json()
    assert len(data) > 0
    entry = data[-1]  # last entry = today
    for key in ("date", "xp", "active", "intensity"):
        assert key in entry


def test_calendar_includes_today(client, db):
    _add_chunk(db, 50)
    data = client.get("/history/calendar").json()
    dates = [e["date"] for e in data]
    assert date.today().isoformat() in dates


# ── XP and active flag ────────────────────────────────────────────────────────

def test_calendar_active_true_when_xp(client, db):
    _add_chunk(db, 100)
    data = client.get("/history/calendar").json()
    today_entry = next(e for e in data if e["date"] == date.today().isoformat())
    assert today_entry["active"] is True
    assert today_entry["xp"] == 100


def test_calendar_active_false_when_no_xp(client):
    data = client.get("/history/calendar").json()
    today_entry = next((e for e in data if e["date"] == date.today().isoformat()), None)
    if today_entry is not None:
        assert today_entry["active"] is False
        assert today_entry["xp"] == 0


def test_calendar_xp_aggregates_multiple_chunks(client, db):
    _add_chunk(db, 40)
    _add_chunk(db, 60)
    data = client.get("/history/calendar").json()
    today_entry = next(e for e in data if e["date"] == date.today().isoformat())
    assert today_entry["xp"] == 100


def test_calendar_zero_fill_inactive_days(client, db):
    _add_chunk(db, 100, days_ago=5)
    data = client.get("/history/calendar").json()
    inactive = [e for e in data if e["date"] != (date.today() - timedelta(days=5)).isoformat()]
    assert all(e["xp"] == 0 for e in inactive)


def test_calendar_months_param_expands_window(client, db):
    data_1 = client.get("/history/calendar?months=1").json()
    data_2 = client.get("/history/calendar?months=2").json()
    assert len(data_2) > len(data_1)


def test_calendar_oldest_first(client, db):
    _add_chunk(db, 10, days_ago=3)
    _add_chunk(db, 20, days_ago=1)
    data = client.get("/history/calendar").json()
    dates = [e["date"] for e in data]
    assert dates == sorted(dates)


def test_calendar_intensity_nonzero_with_xp(client, db):
    _add_chunk(db, 200)
    data = client.get("/history/calendar").json()
    today_entry = next(e for e in data if e["date"] == date.today().isoformat())
    assert today_entry["intensity"] > 0
