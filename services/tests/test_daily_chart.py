"""Tests for GET /history/daily endpoint."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({
        "base_sprite": "x.png", "evolution_stage": 0,
        "skin": None, "accessories": [], "anim_state": "idle",
    })
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.commit()
    yield conn
    conn.close()


def _insert_chunk(db, chunk_id: str, category: str, xp: int, duration_sec: int, processed_at: str) -> None:
    db.execute(
        """
        INSERT OR IGNORE INTO chunk_log
            (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (chunk_id + "_log", chunk_id, category, xp, duration_sec, processed_at),
    )
    db.commit()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def test_empty_returns_empty_list(client):
    resp = client.get("/history/daily?days=14")
    assert resp.status_code == 200
    assert resp.json() == []


def test_single_chunk_appears_in_day(db, client):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT12:00:00+00:00")
    _insert_chunk(db, "c1", "WORK", 30, 1800, today)

    resp = client.get("/history/daily?days=14")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["total_xp"] == 30
    assert entries[0]["by_category"]["WORK"] == 30
    assert entries[0]["total_duration_sec"] == 1800


def test_multiple_categories_same_day_aggregated(db, client):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT10:00:00+00:00")
    _insert_chunk(db, "c1", "WORK", 20, 600, today)
    _insert_chunk(db, "c2", "GAME", 15, 900, today)

    resp = client.get("/history/daily?days=14")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["total_xp"] == 35
    assert entries[0]["by_category"]["WORK"] == 20
    assert entries[0]["by_category"]["GAME"] == 15


def test_different_days_returned_as_separate_entries(db, client):
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=1)
    _insert_chunk(db, "c1", "WORK", 10, 600,
                  today.strftime("%Y-%m-%dT10:00:00+00:00"))
    _insert_chunk(db, "c2", "WORK", 20, 1200,
                  yesterday.strftime("%Y-%m-%dT10:00:00+00:00"))

    resp = client.get("/history/daily?days=14")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 2
    # Newest first
    assert entries[0]["total_xp"] == 10
    assert entries[1]["total_xp"] == 20


def test_chunks_outside_days_range_excluded(db, client):
    old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
        "%Y-%m-%dT10:00:00+00:00"
    )
    _insert_chunk(db, "c_old", "WORK", 99, 3600, old_ts)

    resp = client.get("/history/daily?days=14")
    assert resp.status_code == 200
    assert resp.json() == []


def test_missing_categories_filled_with_zero(db, client):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT10:00:00+00:00")
    _insert_chunk(db, "c1", "WORK", 10, 600, today)

    resp = client.get("/history/daily?days=14")
    entries = resp.json()
    assert entries[0]["by_category"]["GAME"] == 0
    assert entries[0]["by_category"]["SLEEP"] == 0


def test_default_days_is_14(db, client):
    """Calling /history/daily without ?days param should default to 14."""
    resp = client.get("/history/daily")
    assert resp.status_code == 200


def test_custom_days_param(db, client):
    resp = client.get("/history/daily?days=7")
    assert resp.status_code == 200


def test_days_too_large_returns_422(client):
    resp = client.get("/history/daily?days=999")
    assert resp.status_code == 422


def test_days_zero_returns_422(client):
    resp = client.get("/history/daily?days=0")
    assert resp.status_code == 422
