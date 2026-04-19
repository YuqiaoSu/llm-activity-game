"""Tests for GET /places/{id}/upgrade-preview."""
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
    # Place at level 1 with 0 XP
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level)"
        " VALUES ('lab', 'Lab', 'STUDY', '', 'UNLOCKED', '{}', 0, 1)"
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def test_preview_shape(client):
    r = client.get("/places/lab/upgrade-preview?xp=0")
    assert r.status_code == 200
    d = r.json()
    for key in ("place_id", "current_xp", "projected_xp", "current_level",
                "projected_level", "would_level_up", "xp_to_next"):
        assert key in d


def test_preview_zero_xp_no_change(client):
    r = client.get("/places/lab/upgrade-preview?xp=0")
    d = r.json()
    assert d["current_xp"] == 0
    assert d["projected_xp"] == 0
    assert d["current_level"] == 1
    assert d["projected_level"] == 1
    assert d["would_level_up"] is False
    assert d["xp_to_next"] == 50   # level 2 threshold


def test_preview_no_level_up(client):
    r = client.get("/places/lab/upgrade-preview?xp=49")
    d = r.json()
    assert d["projected_xp"] == 49
    assert d["projected_level"] == 1
    assert d["would_level_up"] is False
    assert d["xp_to_next"] == 1   # 50 - 49


def test_preview_would_level_up(client):
    r = client.get("/places/lab/upgrade-preview?xp=50")
    d = r.json()
    assert d["projected_level"] == 2
    assert d["would_level_up"] is True


def test_preview_xp_to_next_after_level_up(client):
    r = client.get("/places/lab/upgrade-preview?xp=50")
    d = r.json()
    # Now at level 2 (50 XP); threshold for level 3 is 200 XP; xp_to_next = 200 - 50 = 150
    assert d["xp_to_next"] == 150


def test_preview_404_on_missing_place(client):
    r = client.get("/places/ghost/upgrade-preview?xp=10")
    assert r.status_code == 404


def test_preview_existing_xp_counts(client, db):
    db.execute("UPDATE places SET xp=100, level=2 WHERE place_id='lab'")
    db.commit()
    r = client.get("/places/lab/upgrade-preview?xp=100")
    d = r.json()
    assert d["current_xp"] == 100
    assert d["projected_xp"] == 200
    assert d["projected_level"] == 3
    assert d["would_level_up"] is True   # was level 2, now level 3
