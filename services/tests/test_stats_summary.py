"""Tests for GET /stats/summary — all-time career summary endpoint."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_chunk(db, category: str = "WORK", xp: int = 10, dur: int = 600,
                  ts: str | None = None) -> None:
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), category, xp, dur, ts or _now()),
    )
    db.commit()


def _insert_drop(db, item_id: str = "item_x") -> None:
    db.execute(
        "INSERT INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at)"
        " VALUES (?, ?, 0, ?, 'player_default', ?)",
        (str(uuid.uuid4()), str(uuid.uuid4()), item_id, _now()),
    )
    db.commit()


def _insert_xp(db, category: str, xp: int) -> None:
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp)"
        " VALUES ('player_default', ?, ?)"
        " ON CONFLICT(character_id, category) DO UPDATE SET xp = xp + excluded.xp",
        (category, xp),
    )
    db.commit()


# ── response shape ────────────────────────────────────────────────────────────

def test_summary_returns_200(client):
    tc, _ = client
    r = tc.get("/stats/summary")
    assert r.status_code == 200


def test_summary_has_required_keys(client):
    tc, _ = client
    r = tc.get("/stats/summary")
    data = r.json()
    for key in ("total_xp", "level", "total_chunks", "total_active_min",
                "peak_week_xp", "items_collected", "category_breakdown"):
        assert key in data, f"missing key: {key}"


def test_summary_category_breakdown_has_all_categories(client):
    tc, _ = client
    r = tc.get("/stats/summary")
    breakdown = r.json()["category_breakdown"]
    for cat in ("WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"):
        assert cat in breakdown


# ── values ────────────────────────────────────────────────────────────────────

def test_summary_total_chunks_counts_chunks(client):
    tc, db = client
    _insert_chunk(db)
    _insert_chunk(db)
    r = tc.get("/stats/summary")
    assert r.json()["total_chunks"] == 2


def test_summary_total_active_min(client):
    tc, db = client
    _insert_chunk(db, dur=1800)  # 30 min
    _insert_chunk(db, dur=600)   # 10 min
    r = tc.get("/stats/summary")
    assert r.json()["total_active_min"] == 40


def test_summary_items_collected_counts_distinct(client):
    tc, db = client
    _insert_drop(db, "item_a")
    _insert_drop(db, "item_a")  # duplicate — should count as 1
    _insert_drop(db, "item_b")
    r = tc.get("/stats/summary")
    assert r.json()["items_collected"] == 2


def test_summary_peak_week_xp_returns_max_week(client):
    tc, db = client
    # Two chunks in the same week = 60 XP
    _insert_chunk(db, xp=40)
    _insert_chunk(db, xp=20)
    # One chunk three weeks ago = 5 XP
    old_ts = (datetime.now(timezone.utc) - timedelta(weeks=3)).isoformat()
    _insert_chunk(db, xp=5, ts=old_ts)
    r = tc.get("/stats/summary")
    assert r.json()["peak_week_xp"] == 60


def test_summary_empty_db_returns_zeros(client):
    tc, _ = client
    r = tc.get("/stats/summary")
    data = r.json()
    assert data["total_chunks"] == 0
    assert data["total_active_min"] == 0
    assert data["peak_week_xp"] == 0
    assert data["items_collected"] == 0


def test_summary_category_breakdown_reflects_xp(client):
    tc, db = client
    _insert_xp(db, "WORK", 300)
    _insert_xp(db, "GAME", 150)
    r = tc.get("/stats/summary")
    bd = r.json()["category_breakdown"]
    assert bd["WORK"] == 300
    assert bd["GAME"] == 150
    assert bd["VIDEO"] == 0
