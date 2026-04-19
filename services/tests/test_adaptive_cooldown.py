"""Tests for adaptive poll cooldown."""
import json
import sqlite3
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db
from services.sync_agent.rate_limiter import adaptive_cooldown

_PLAYER = "player_default"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', ?)",
        (_PLAYER, visual),
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


# ── adaptive_cooldown unit tests ──────────────────────────────────────────────

def test_cooldown_active_player(db):
    db.execute(
        "UPDATE streak_state SET last_active_date=? WHERE player_id='default'",
        (date.today().isoformat(),),
    )
    db.commit()
    assert adaptive_cooldown(db) == 60


def test_cooldown_dormant_player(db):
    old = (date.today() - timedelta(days=10)).isoformat()
    db.execute(
        "UPDATE streak_state SET last_active_date=? WHERE player_id='default'",
        (old,),
    )
    db.commit()
    assert adaptive_cooldown(db) == 10


def test_cooldown_never_active(db):
    # last_active_date is NULL by default after init
    assert adaptive_cooldown(db) == 10


def test_cooldown_boundary_exactly_3_days(db):
    boundary = (date.today() - timedelta(days=3)).isoformat()
    db.execute(
        "UPDATE streak_state SET last_active_date=? WHERE player_id='default'",
        (boundary,),
    )
    db.commit()
    # 3 days gap is NOT > 3, so still active cooldown
    assert adaptive_cooldown(db) == 60


def test_cooldown_4_days_is_dormant(db):
    four_ago = (date.today() - timedelta(days=4)).isoformat()
    db.execute(
        "UPDATE streak_state SET last_active_date=? WHERE player_id='default'",
        (four_ago,),
    )
    db.commit()
    assert adaptive_cooldown(db) == 10


# ── cooldown_sec in API response ──────────────────────────────────────────────

def test_poll_response_includes_cooldown_sec(client):
    r = client.post("/sync/poll-now")
    # May be ON_COOLDOWN or NO_NEW_CHUNKS but cooldown_sec must be present
    assert "cooldown_sec" in r.json()


def test_poll_cooldown_sec_is_int(client):
    r = client.post("/sync/poll-now")
    assert isinstance(r.json()["cooldown_sec"], int)
