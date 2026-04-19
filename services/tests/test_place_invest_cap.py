"""Tests for POST /places/{id}/invest daily cap (500 XP per place per day)."""
import json
import sqlite3
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db


_PLAYER = "player_default"
_CAP = 500


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
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level)"
        " VALUES ('lab', 'Lab', 'STUDY', 'desc', 'UNLOCKED', '[]', 0, 1)"
    )
    # Give the player plenty of XP
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 5000)",
        (_PLAYER,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _seed_log(db, invested: int, delta_days: int = 0) -> None:
    d = (date.today() + timedelta(days=delta_days)).isoformat()
    db.execute(
        "INSERT OR REPLACE INTO place_invest_log (player_id, place_id, invest_date, total_invested)"
        " VALUES (?, 'lab', ?, ?)",
        (_PLAYER, d, invested),
    )
    db.commit()


# ── response shape ─────────────────────────────────────────────────────────────

def test_invest_response_includes_cap_fields(client):
    r = client.post("/places/lab/invest", json={"xp": 10})
    data = r.json()
    assert "invested_today" in data
    assert "cap" in data
    assert "remaining" in data
    assert data["cap"] == _CAP


def test_first_invest_remaining_correct(client):
    r = client.post("/places/lab/invest", json={"xp": 100})
    data = r.json()
    assert data["invested_today"] == 100
    assert data["remaining"] == _CAP - 100


# ── cap enforcement ────────────────────────────────────────────────────────────

def test_invest_at_cap_is_allowed(client, db):
    _seed_log(db, _CAP - 50)
    r = client.post("/places/lab/invest", json={"xp": 50})
    assert r.status_code == 200
    assert r.json()["remaining"] == 0


def test_invest_over_cap_returns_429(client, db):
    _seed_log(db, _CAP - 10)
    r = client.post("/places/lab/invest", json={"xp": 11})
    assert r.status_code == 429


def test_invest_exactly_over_cap_returns_429(client, db):
    _seed_log(db, _CAP)
    r = client.post("/places/lab/invest", json={"xp": 1})
    assert r.status_code == 429


def test_429_detail_includes_remaining(client, db):
    _seed_log(db, 450)
    r = client.post("/places/lab/invest", json={"xp": 100})
    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["remaining"] == 50
    assert detail["invested_today"] == 450


def test_cap_is_per_day_resets_next_day(client, db):
    _seed_log(db, _CAP, delta_days=-1)  # yesterday's log — should not count today
    r = client.post("/places/lab/invest", json={"xp": 50})
    assert r.status_code == 200


def test_cumulative_invest_tracked(client, db):
    client.post("/places/lab/invest", json={"xp": 100})
    client.post("/places/lab/invest", json={"xp": 150})
    r = client.post("/places/lab/invest", json={"xp": 50})
    data = r.json()
    assert data["invested_today"] == 300
    assert data["remaining"] == 200
