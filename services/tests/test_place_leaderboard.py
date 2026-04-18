"""Tests for GET /places/leaderboard."""
import json
import sqlite3

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


def _add_place(db, place_id: str, name: str, state: str = "UNLOCKED", xp: int = 0, level: int = 1) -> None:
    db.execute(
        "INSERT INTO places (place_id, name, place_type, item_pool, metadata, state, xp, level)"
        " VALUES (?, ?, 'home', '{}', '{}', ?, ?, ?)",
        (place_id, name, state, xp, level),
    )
    db.commit()


# ── Shape ────────────────────────────────────────────────────────────────────

def test_leaderboard_returns_200(client):
    assert client.get("/places/leaderboard").status_code == 200


def test_leaderboard_empty_when_no_places(client):
    data = client.get("/places/leaderboard").json()
    assert data == []


def test_leaderboard_shape(client, db):
    _add_place(db, "p1", "Alpha", xp=100)
    data = client.get("/places/leaderboard").json()
    assert len(data) == 1
    entry = data[0]
    for key in ("rank", "place_id", "name", "level", "xp"):
        assert key in entry


# ── Ranking ──────────────────────────────────────────────────────────────────

def test_leaderboard_ordered_by_xp_desc(client, db):
    _add_place(db, "p1", "Alpha", xp=50)
    _add_place(db, "p2", "Beta",  xp=200)
    _add_place(db, "p3", "Gamma", xp=100)
    data = client.get("/places/leaderboard").json()
    assert [e["place_id"] for e in data] == ["p2", "p3", "p1"]


def test_leaderboard_rank_values(client, db):
    _add_place(db, "p1", "A", xp=300)
    _add_place(db, "p2", "B", xp=100)
    data = client.get("/places/leaderboard").json()
    assert data[0]["rank"] == 1
    assert data[1]["rank"] == 2


def test_leaderboard_xp_tie_broken_by_name(client, db):
    _add_place(db, "p1", "Zebra", xp=100)
    _add_place(db, "p2", "Apple", xp=100)
    data = client.get("/places/leaderboard").json()
    assert data[0]["name"] == "Apple"
    assert data[1]["name"] == "Zebra"


def test_leaderboard_excludes_locked_places(client, db):
    _add_place(db, "p1", "Unlocked", state="UNLOCKED", xp=100)
    _add_place(db, "p2", "Locked",   state="LOCKED",   xp=999)
    data = client.get("/places/leaderboard").json()
    assert len(data) == 1
    assert data[0]["place_id"] == "p1"


def test_leaderboard_includes_level(client, db):
    _add_place(db, "p1", "Alpha", xp=50, level=3)
    data = client.get("/places/leaderboard").json()
    assert data[0]["level"] == 3


def test_leaderboard_zero_xp_places_included(client, db):
    _add_place(db, "p1", "Alpha", xp=0)
    _add_place(db, "p2", "Beta",  xp=0)
    data = client.get("/places/leaderboard").json()
    assert len(data) == 2
