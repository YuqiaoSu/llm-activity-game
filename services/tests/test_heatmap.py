"""Tests for GET /history/heatmap endpoint."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.api.routers.history import _intensity
from services.storage.db import init_db


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def _insert_chunk(db, xp: int, day_offset: int = 0) -> None:
    """Insert a chunk_log row N days ago from today."""
    d = (date.today() - timedelta(days=day_offset)).isoformat()
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at) "
        "VALUES (?,?,?,?,?,?)",
        (f"log_{day_offset}_{xp}", f"chunk_{day_offset}_{xp}",
         "WORK", xp, 600, f"{d}T12:00:00"),
    )
    db.commit()


# ── intensity helper unit tests ───────────────────────────────────────────────

def test_intensity_zero():
    assert _intensity(0) == 0


def test_intensity_negative():
    assert _intensity(-5) == 0


def test_intensity_tier1():
    assert _intensity(1) == 1
    assert _intensity(30) == 1


def test_intensity_tier2():
    assert _intensity(31) == 2
    assert _intensity(80) == 2


def test_intensity_tier3():
    assert _intensity(81) == 3
    assert _intensity(180) == 3


def test_intensity_tier4():
    assert _intensity(181) == 4
    assert _intensity(9999) == 4


# ── API integration tests ─────────────────────────────────────────────────────

def test_heatmap_default_returns_84_days(client, db):
    resp = client.get("/history/heatmap")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 84  # 12 weeks × 7 days


def test_heatmap_weeks_param(client, db):
    resp = client.get("/history/heatmap?weeks=4")
    assert resp.status_code == 200
    assert len(resp.json()) == 28


def test_heatmap_oldest_first(client, db):
    resp = client.get("/history/heatmap?weeks=4")
    dates = [e["date"] for e in resp.json()]
    assert dates == sorted(dates)


def test_heatmap_today_is_last_entry(client, db):
    data = client.get("/history/heatmap?weeks=1").json()
    assert data[-1]["date"] == date.today().isoformat()


def test_heatmap_empty_db_all_zeros(client, db):
    data = client.get("/history/heatmap?weeks=2").json()
    assert all(e["total_xp"] == 0 for e in data)
    assert all(e["intensity"] == 0 for e in data)


def test_heatmap_today_xp_appears(client, db):
    _insert_chunk(db, 100, day_offset=0)
    data = client.get("/history/heatmap?weeks=1").json()
    today_entry = next(e for e in data if e["date"] == date.today().isoformat())
    assert today_entry["total_xp"] == 100
    assert today_entry["intensity"] == 3


def test_heatmap_xp_accumulates_same_day(client, db):
    d = (date.today() - timedelta(days=1)).isoformat()
    for i, xp in enumerate([50, 50]):
        db.execute(
            "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at) "
            "VALUES (?,?,?,?,?,?)",
            (f"log_acc_{i}", f"chunk_acc_{i}", "WORK", xp, 600, f"{d}T{10+i}:00:00"),
        )
    db.commit()
    data = client.get("/history/heatmap?weeks=1").json()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    entry = next(e for e in data if e["date"] == yesterday)
    assert entry["total_xp"] == 100


def test_heatmap_entry_shape(client, db):
    data = client.get("/history/heatmap?weeks=1").json()
    for entry in data:
        assert "date" in entry
        assert "total_xp" in entry
        assert "intensity" in entry
        assert entry["intensity"] in (0, 1, 2, 3, 4)
