"""Tests for challenge events API and XP multiplier application."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db
from services.sync_agent.agent import SyncAgent
from services.sync_agent.rate_limiter import RateLimiter
from services.sync_agent.tracker_client import TrackerClient


# ── helpers ────────────────────────────────────────────────────────────────────

def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _insert_event(
    conn,
    event_id: str,
    category: str,
    multiplier: float,
    starts_at: str,
    ends_at: str,
    label: str = "Test Event",
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO challenge_events "
        "(event_id, label, category, multiplier, starts_at, ends_at) VALUES (?,?,?,?,?,?)",
        (event_id, label, category, multiplier, starts_at, ends_at),
    )
    conn.commit()


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
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default','T',?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


# ── API tests — GET /events/active ────────────────────────────────────────────

def test_active_events_empty_by_default(client):
    resp = client.get("/events/active")
    assert resp.status_code == 200
    assert resp.json() == []


def test_active_events_returns_in_window_event(client, db):
    now = _now()
    _insert_event(db, "ev1", "WORK", 2.0,
                  _iso(now - timedelta(hours=1)),
                  _iso(now + timedelta(hours=1)))
    resp = client.get("/events/active")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["event_id"] == "ev1"
    assert data[0]["multiplier"] == 2.0


def test_active_events_excludes_future(client, db):
    now = _now()
    _insert_event(db, "ev_future", "WORK", 2.0,
                  _iso(now + timedelta(hours=2)),
                  _iso(now + timedelta(hours=5)))
    resp = client.get("/events/active")
    assert resp.json() == []


def test_active_events_excludes_past(client, db):
    now = _now()
    _insert_event(db, "ev_past", "WORK", 2.0,
                  _iso(now - timedelta(hours=5)),
                  _iso(now - timedelta(hours=1)))
    resp = client.get("/events/active")
    assert resp.json() == []


def test_active_events_multiple_in_window(client, db):
    now = _now()
    _insert_event(db, "ev_a", "WORK", 1.5,
                  _iso(now - timedelta(hours=1)), _iso(now + timedelta(hours=1)))
    _insert_event(db, "ev_b", "SOCIAL", 2.0,
                  _iso(now - timedelta(hours=1)), _iso(now + timedelta(hours=1)))
    data = client.get("/events/active").json()
    assert len(data) == 2


# ── API tests — GET /events ───────────────────────────────────────────────────

def test_all_events_returns_all(client, db):
    now = _now()
    _insert_event(db, "past", "GAME", 1.5,
                  _iso(now - timedelta(days=3)), _iso(now - timedelta(days=1)))
    _insert_event(db, "active", "WORK", 2.0,
                  _iso(now - timedelta(hours=1)), _iso(now + timedelta(hours=1)))
    _insert_event(db, "future", "SOCIAL", 1.5,
                  _iso(now + timedelta(days=1)), _iso(now + timedelta(days=3)))
    data = client.get("/events").json()
    assert len(data) == 3


def test_all_events_response_fields(client, db):
    now = _now()
    _insert_event(db, "ev1", "WORK", 2.5,
                  _iso(now - timedelta(hours=1)), _iso(now + timedelta(hours=1)),
                  label="Power Hour")
    data = client.get("/events").json()
    ev = data[0]
    assert ev["event_id"] == "ev1"
    assert ev["label"] == "Power Hour"
    assert ev["category"] == "WORK"
    assert ev["multiplier"] == 2.5
    assert "starts_at" in ev
    assert "ends_at" in ev


# ── XP multiplier integration tests ──────────────────────────────────────────

def _make_agent(db) -> SyncAgent:
    mock_tracker = MagicMock(spec=TrackerClient)
    return SyncAgent(
        db=db,
        tracker_client=mock_tracker,
        character_id="player_default",
        rate_limiter=RateLimiter(cooldown_sec=0),
    )


def _make_chunk(category: str = "WORK", duration_min: int = 10) -> dict:
    return {
        "chunk_id": str(uuid.uuid4()),
        "started_at": _iso(_now() - timedelta(minutes=duration_min)),
        "duration_sec": duration_min * 60,
        "label": category,
        "confidence": 0.9,
        "time_of_day": "morning",
    }


def test_active_event_multiplier_applied(db):
    """XP for matching category is multiplied when an active event exists."""
    now = _now()
    _insert_event(db, "ev_work", "WORK", 2.0,
                  _iso(now - timedelta(hours=1)), _iso(now + timedelta(hours=1)))

    agent = _make_agent(db)
    agent.tracker_client.fetch_chunks.return_value = ([_make_chunk("WORK", 10)], "cursor1")
    agent.poll()

    xp_row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='WORK'"
    ).fetchone()
    # Base: 10 min × 1 XP/min = 10 XP. With 2× multiplier → 20 XP.
    assert xp_row is not None
    assert xp_row["xp"] == 20


def test_no_event_no_multiplier(db):
    """Without events, XP is unaffected."""
    agent = _make_agent(db)
    agent.tracker_client.fetch_chunks.return_value = ([_make_chunk("WORK", 10)], "cursor1")
    agent.poll()

    xp_row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category='WORK'"
    ).fetchone()
    assert xp_row is not None
    assert xp_row["xp"] == 10


def test_all_category_event_applies_to_every_chunk(db):
    """An event with category='ALL' boosts XP regardless of chunk category."""
    now = _now()
    _insert_event(db, "ev_all", "ALL", 1.5,
                  _iso(now - timedelta(hours=1)), _iso(now + timedelta(hours=1)))

    agent = _make_agent(db)
    agent.tracker_client.fetch_chunks.return_value = (
        [_make_chunk("SOCIAL", 10), _make_chunk("GAME", 10)],
        "cursor1",
    )
    agent.poll()

    for cat in ("SOCIAL", "GAME"):
        xp_row = db.execute(
            "SELECT xp FROM player_category_xp WHERE character_id='player_default' AND category=?",
            (cat,),
        ).fetchone()
        # 10 min × 1 × 1.5 = 15
        assert xp_row is not None, f"Missing XP row for {cat}"
        assert xp_row["xp"] == 15
