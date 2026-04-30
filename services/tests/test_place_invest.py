"""Tests for POST /places/{place_id}/invest (XP donation to places)."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db


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
    # Seed one unlocked place at level 1, 0 XP
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level) "
        "VALUES ('lab', 'Lab', 'STUDY', 'desc', 'UNLOCKED', '[]', 0, 1)"
    )
    # Seed a locked place
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level) "
        "VALUES ('vault', 'Vault', 'STUDY', 'desc', 'LOCKED', '[]', 0, 1)"
    )
    # Give the player 200 XP
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 200)",
        (_PLAYER,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── basic happy path ───────────────────────────────────────────────────────────

def test_invest_returns_200(client):
    r = client.post("/places/lab/invest", json={"xp": 10})
    assert r.status_code == 200


def test_invest_response_fields(client):
    r = client.post("/places/lab/invest", json={"xp": 10})
    data = r.json()
    assert data["place_id"] == "lab"
    assert data["xp_invested"] == 10
    assert "new_xp" in data
    assert "new_level" in data
    assert "levelled_up" in data


def test_invest_increases_place_xp(client, db):
    client.post("/places/lab/invest", json={"xp": 30})
    row = db.execute("SELECT xp FROM places WHERE place_id='lab'").fetchone()
    assert row["xp"] >= 30  # mood modifier may scale the value slightly


def test_invest_deducts_player_xp(client, db):
    client.post("/places/lab/invest", json={"xp": 50})
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id=? AND category='WORK'",
        (_PLAYER,),
    ).fetchone()
    assert row["xp"] == 150


def test_invest_triggers_level_up(client, db):
    # Level 2 requires 50 XP; invest enough for level-up
    r = client.post("/places/lab/invest", json={"xp": 50})
    data = r.json()
    assert data["new_level"] >= 2
    assert data["levelled_up"] is True


def test_invest_no_level_up_below_threshold(client, db):
    r = client.post("/places/lab/invest", json={"xp": 10})
    data = r.json()
    assert data["new_level"] == 1
    assert data["levelled_up"] is False


# ── error guards ───────────────────────────────────────────────────────────────

def test_invest_404_on_missing_place(client):
    r = client.post("/places/no_such_place/invest", json={"xp": 10})
    assert r.status_code == 404


def test_invest_409_on_locked_place(client):
    r = client.post("/places/vault/invest", json={"xp": 10})
    assert r.status_code == 409


def test_invest_402_on_insufficient_xp(client):
    # Player has 200 XP; request 201 (within 500 cap but over player balance)
    r = client.post("/places/lab/invest", json={"xp": 201})
    assert r.status_code == 402


def test_invest_400_on_zero_xp(client):
    r = client.post("/places/lab/invest", json={"xp": 0})
    assert r.status_code == 422  # Pydantic ge=1 validation


def test_invest_exact_xp_drains_to_zero(client, db):
    client.post("/places/lab/invest", json={"xp": 200})
    row = db.execute(
        "SELECT COALESCE(SUM(xp),0) AS total FROM player_category_xp WHERE character_id=?",
        (_PLAYER,),
    ).fetchone()
    assert row["total"] == 0
