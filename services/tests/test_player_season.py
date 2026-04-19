"""Tests for GET /player/season — monthly XP tier."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_PLAYER = "player_default"
_THIS_MONTH = __import__("datetime").date.today().strftime("%Y-%m")


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


_seed_counter = 0


def _seed_xp(db, xp: int) -> None:
    """Insert a chunk_log row in the current month with the given XP total."""
    global _seed_counter
    _seed_counter += 1
    ts = f"{_THIS_MONTH}-01T00:00:00"
    db.execute(
        "INSERT INTO chunk_log (log_id, chunk_id, category, xp_awarded, duration_sec, processed_at)"
        " VALUES (?, ?, 'WORK', ?, 60, ?)",
        (f"log{_seed_counter}", f"chunk{_seed_counter}", xp, ts),
    )
    db.commit()


def test_season_shape(client):
    r = client.get("/player/season")
    assert r.status_code == 200
    d = r.json()
    assert "season_xp" in d
    assert "tier" in d
    assert "next_tier_at" in d
    assert "days_remaining" in d
    assert "month" in d


def test_season_zero_xp_is_bronze(client):
    r = client.get("/player/season")
    d = r.json()
    assert d["season_xp"] == 0
    assert d["tier"] == "BRONZE"


def test_season_next_tier_at_500_when_bronze(client):
    r = client.get("/player/season")
    assert r.json()["next_tier_at"] == 500


def test_season_silver_tier(client, db):
    _seed_xp(db, 800)
    r = client.get("/player/season")
    d = r.json()
    assert d["tier"] == "SILVER"
    assert d["next_tier_at"] == 2000


def test_season_gold_tier(client, db):
    _seed_xp(db, 2500)
    r = client.get("/player/season")
    d = r.json()
    assert d["tier"] == "GOLD"
    assert d["next_tier_at"] is None


def test_season_xp_matches_sum(client, db):
    _seed_xp(db, 300)
    _seed_xp(db, 150)
    r = client.get("/player/season")
    assert r.json()["season_xp"] == 450


def test_season_month_matches_current(client):
    r = client.get("/player/season")
    assert r.json()["month"] == _THIS_MONTH


def test_season_days_remaining_positive(client):
    r = client.get("/player/season")
    assert r.json()["days_remaining"] >= 1
