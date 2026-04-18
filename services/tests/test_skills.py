"""Tests for GET /skills and POST /skills/{id}/unlock."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db
from services.progression.xp import get_total_xp


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


def _seed_skill(db, skill_id: str, name: str = "Test", xp_cost: int = 100,
                effect_type: str = "xp_multiplier",
                effect_params: dict | None = None) -> None:
    db.execute(
        "INSERT INTO skills (skill_id, name, description, xp_cost, effect_type, effect_params)"
        " VALUES (?, ?, 'desc', ?, ?, ?)",
        (skill_id, name, xp_cost, effect_type, json.dumps(effect_params or {"factor": 1.1})),
    )
    db.commit()


def _give_xp(db, xp: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp)"
        " VALUES ('player_default', 'WORK', ?)",
        (xp,),
    )
    db.commit()


# ── GET /skills ───────────────────────────────────────────────────────────────

def test_get_skills_returns_200(client):
    assert client.get("/skills").status_code == 200


def test_get_skills_empty_when_none_seeded(client):
    assert client.get("/skills").json() == []


def test_get_skills_shape(client, db):
    _seed_skill(db, "s1")
    data = client.get("/skills").json()
    assert len(data) == 1
    entry = data[0]
    for key in ("skill_id", "name", "description", "xp_cost", "effect_type", "effect_params",
                "unlocked", "can_unlock"):
        assert key in entry


def test_get_skills_can_unlock_true_when_enough_xp(client, db):
    _seed_skill(db, "s1", xp_cost=100)
    _give_xp(db, 200)
    data = client.get("/skills").json()
    assert data[0]["can_unlock"] is True


def test_get_skills_can_unlock_false_when_insufficient_xp(client, db):
    _seed_skill(db, "s1", xp_cost=500)
    _give_xp(db, 100)
    data = client.get("/skills").json()
    assert data[0]["can_unlock"] is False


def test_get_skills_unlocked_false_initially(client, db):
    _seed_skill(db, "s1")
    _give_xp(db, 200)
    data = client.get("/skills").json()
    assert data[0]["unlocked"] is False


# ── POST /skills/{id}/unlock ──────────────────────────────────────────────────

def test_unlock_skill_returns_200(client, db):
    _seed_skill(db, "s1", xp_cost=100)
    _give_xp(db, 200)
    assert client.post("/skills/s1/unlock").status_code == 200


def test_unlock_skill_response_shape(client, db):
    _seed_skill(db, "s1", xp_cost=100)
    _give_xp(db, 200)
    data = client.post("/skills/s1/unlock").json()
    assert data["skill_id"] == "s1"
    assert data["xp_spent"] == 100


def test_unlock_skill_deducts_xp(client, db):
    _seed_skill(db, "s1", xp_cost=100)
    _give_xp(db, 200)
    client.post("/skills/s1/unlock")
    assert get_total_xp(db, "player_default") == 100


def test_unlock_skill_shows_unlocked_in_list(client, db):
    _seed_skill(db, "s1", xp_cost=100)
    _give_xp(db, 200)
    client.post("/skills/s1/unlock")
    data = client.get("/skills").json()
    assert data[0]["unlocked"] is True
    assert data[0]["can_unlock"] is False


def test_unlock_skill_404_for_unknown(client):
    assert client.post("/skills/nonexistent/unlock").status_code == 404


def test_unlock_skill_409_when_already_unlocked(client, db):
    _seed_skill(db, "s1", xp_cost=100)
    _give_xp(db, 500)
    client.post("/skills/s1/unlock")
    assert client.post("/skills/s1/unlock").status_code == 409


def test_unlock_skill_402_when_insufficient_xp(client, db):
    _seed_skill(db, "s1", xp_cost=1000)
    _give_xp(db, 50)
    assert client.post("/skills/s1/unlock").status_code == 402
