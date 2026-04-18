"""Tests for GET /sync/multipliers — active XP multiplier preview."""
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
    app = create_app()
    app.state.db = db
    return TestClient(app)


def _set_streak(db, days: int) -> None:
    from datetime import date
    today = date.today().isoformat()
    db.execute(
        "UPDATE streak_state SET current_streak=?, last_active_date=? WHERE player_id='default'",
        (days, today),
    )
    db.commit()


def _set_recovery_bonus(db, value: bool) -> None:
    db.execute(
        "UPDATE streak_state SET has_recovery_bonus=? WHERE player_id='default'",
        (1 if value else 0,),
    )
    db.commit()


def _insert_event(db, label: str, category: str = "ALL", multiplier: float = 1.5,
                  active: bool = True) -> None:
    now = datetime.now(timezone.utc)
    if active:
        starts = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        ends = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    else:
        starts = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
        ends = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    db.execute(
        "INSERT INTO challenge_events (event_id, label, category, multiplier, starts_at, ends_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (label, label, category, multiplier, starts, ends),
    )
    db.commit()


# ── basic shape ──────────────────────────────────────────────────────────────

def test_returns_list(client):
    resp = client.get("/sync/multipliers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_empty_when_no_bonuses_active(client):
    """With no streak, no recovery, no events, expect empty list."""
    assert client.get("/sync/multipliers").json() == []


def test_entry_shape(client, db):
    _set_streak(db, 5)
    entry = client.get("/sync/multipliers").json()[0]
    for key in ("source", "multiplier", "description", "category"):
        assert key in entry


# ── streak bonus ─────────────────────────────────────────────────────────────

def test_streak_bonus_absent_below_threshold(client, db):
    _set_streak(db, 2)
    sources = [e["source"] for e in client.get("/sync/multipliers").json()]
    assert "streak" not in sources


def test_streak_bonus_present_at_threshold(client, db):
    _set_streak(db, 3)
    sources = [e["source"] for e in client.get("/sync/multipliers").json()]
    assert "streak" in sources


def test_streak_bonus_multiplier_is_1_1(client, db):
    _set_streak(db, 7)
    entries = {e["source"]: e for e in client.get("/sync/multipliers").json()}
    assert abs(entries["streak"]["multiplier"] - 1.1) < 0.001


# ── recovery bonus ───────────────────────────────────────────────────────────

def test_recovery_bonus_absent_by_default(client):
    sources = [e["source"] for e in client.get("/sync/multipliers").json()]
    assert "recovery" not in sources


def test_recovery_bonus_present_when_flag_set(client, db):
    _set_recovery_bonus(db, True)
    sources = [e["source"] for e in client.get("/sync/multipliers").json()]
    assert "recovery" in sources


def test_recovery_bonus_multiplier_is_1_5(client, db):
    _set_recovery_bonus(db, True)
    entries = {e["source"]: e for e in client.get("/sync/multipliers").json()}
    assert abs(entries["recovery"]["multiplier"] - 1.5) < 0.001


# ── active events ────────────────────────────────────────────────────────────

def test_active_event_appears(client, db):
    _insert_event(db, "Focus Weekend", "WORK", 2.0)
    sources = [e["source"] for e in client.get("/sync/multipliers").json()]
    assert "event" in sources


def test_expired_event_does_not_appear(client, db):
    _insert_event(db, "Old Event", active=False)
    sources = [e["source"] for e in client.get("/sync/multipliers").json()]
    assert "event" not in sources


def test_event_category_for_specific_category(client, db):
    _insert_event(db, "Work Boost", "WORK", 1.5)
    events = [e for e in client.get("/sync/multipliers").json() if e["source"] == "event"]
    assert any(e["category"] == "WORK" for e in events)


def test_event_category_none_for_all(client, db):
    _insert_event(db, "Global Boost", "ALL", 1.2)
    events = [e for e in client.get("/sync/multipliers").json() if e["source"] == "event"]
    assert any(e["category"] is None for e in events)


def test_event_multiplier_value(client, db):
    _insert_event(db, "Big Bonus", multiplier=3.0)
    events = [e for e in client.get("/sync/multipliers").json() if e["source"] == "event"]
    assert any(abs(e["multiplier"] - 3.0) < 0.001 for e in events)
