"""Tests for GET /player/daily-tip."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

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
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def test_daily_tip_shape(client):
    r = client.get("/player/daily-tip")
    assert r.status_code == 200
    d = r.json()
    assert "tip" in d
    assert "tip_index" in d


def test_daily_tip_is_string(client):
    d = client.get("/player/daily-tip").json()
    assert isinstance(d["tip"], str)
    assert len(d["tip"]) > 0


def test_daily_tip_index_in_range(client):
    d = client.get("/player/daily-tip").json()
    assert 0 <= d["tip_index"] <= 19


def test_daily_tip_deterministic(client):
    r1 = client.get("/player/daily-tip").json()
    r2 = client.get("/player/daily-tip").json()
    assert r1["tip"] == r2["tip"]
    assert r1["tip_index"] == r2["tip_index"]


def test_daily_tip_tip_matches_index(client):
    from services.api.routers.player import _TIPS
    d = client.get("/player/daily-tip").json()
    assert d["tip"] == _TIPS[d["tip_index"]]
