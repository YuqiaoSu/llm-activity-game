"""Tests for GET /player/luck and POST /player/luck/upgrade."""
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db, bootstrap_defaults
from services.api.main import app


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    bootstrap_defaults(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app.state.db = db
    return TestClient(app)


def _give_xp(db, amount: int) -> None:
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'SPECIAL', ?)"
        " ON CONFLICT (character_id, category) DO UPDATE SET xp = xp + excluded.xp",
        (amount,),
    )
    db.commit()


# ── GET /player/luck ──────────────────────────────────────────────────────────

def test_luck_get_returns_expected_shape(client):
    resp = client.get("/player/luck")
    assert resp.status_code == 200
    data = resp.json()
    assert "luck" in data
    assert "max_luck" in data
    assert "upgrade_cost" in data
    assert "can_upgrade" in data


def test_luck_default_is_5(client):
    assert client.get("/player/luck").json()["luck"] == 5


def test_luck_max_is_20(client):
    assert client.get("/player/luck").json()["max_luck"] == 20


# ── POST /player/luck/upgrade ─────────────────────────────────────────────────

def test_luck_upgrade_increments(client, db):
    _give_xp(db, 1000)
    resp = client.post("/player/luck/upgrade")
    assert resp.status_code == 200
    assert resp.json()["luck"] == 6


def test_luck_upgrade_cost_doubles(client, db):
    _give_xp(db, 10000)
    resp1 = client.post("/player/luck/upgrade")
    cost1 = resp1.json()["xp_spent"]   # 50
    resp2 = client.post("/player/luck/upgrade")
    cost2 = resp2.json()["xp_spent"]   # 100
    assert cost2 == cost1 * 2


def test_luck_upgrade_402_insufficient_xp(client):
    resp = client.post("/player/luck/upgrade")
    assert resp.status_code == 402


def test_luck_upgrade_409_at_max(client, db):
    db.execute("UPDATE player_profile SET luck=20 WHERE character_id='player_default'")
    db.commit()
    _give_xp(db, 100000)
    resp = client.post("/player/luck/upgrade")
    assert resp.status_code == 409


def test_luck_upgrade_deducts_xp(client, db):
    from services.progression.xp import get_total_xp
    _give_xp(db, 500)
    before = get_total_xp(db, "player_default")
    resp = client.post("/player/luck/upgrade")
    spent = resp.json()["xp_spent"]
    after = get_total_xp(db, "player_default")
    assert before - after == spent
