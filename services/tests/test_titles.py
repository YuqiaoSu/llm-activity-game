"""Tests for GET /player/titles and POST /player/titles/{id}/equip."""
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


# ── GET /player/titles ───────────────────────────────────────────────────────

def test_titles_returns_list(client):
    resp = client.get("/player/titles")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_titles_list_non_empty(client):
    assert len(client.get("/player/titles").json()) > 0


def test_title_entry_shape(client):
    entry = client.get("/player/titles").json()[0]
    for key in ("title_id", "label", "description", "earned", "equipped"):
        assert key in entry


def test_newcomer_title_always_earned(client):
    titles = {t["title_id"]: t for t in client.get("/player/titles").json()}
    assert titles["newcomer"]["earned"] is True


def test_veteran_title_not_earned_at_level_1(client):
    titles = {t["title_id"]: t for t in client.get("/player/titles").json()}
    assert titles["veteran"]["earned"] is False


def test_no_title_equipped_by_default(client):
    titles = client.get("/player/titles").json()
    assert all(not t["equipped"] for t in titles)


# ── POST /player/titles/{id}/equip ───────────────────────────────────────────

def test_equip_returns_404_for_unknown_title(client):
    resp = client.post("/player/titles/no_such_title/equip")
    assert resp.status_code == 404


def test_equip_returns_409_when_not_earned(client):
    resp = client.post("/player/titles/veteran/equip")
    assert resp.status_code == 409


def test_equip_newcomer_succeeds(client):
    resp = client.post("/player/titles/newcomer/equip")
    assert resp.status_code == 200
    assert resp.json()["equipped_title"] == "newcomer"


def test_equipped_flag_set_after_equip(client):
    client.post("/player/titles/newcomer/equip")
    titles = {t["title_id"]: t for t in client.get("/player/titles").json()}
    assert titles["newcomer"]["equipped"] is True


def test_profile_returns_equipped_title(client):
    client.post("/player/titles/newcomer/equip")
    profile = client.get("/player/profile").json()
    assert profile.get("equipped_title") == "newcomer"


def test_work_xp_title_earned_when_xp_meets_threshold(client, db):
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp)"
        " VALUES ('player_default', 'WORK', 600)"
    )
    db.commit()
    titles = {t["title_id"]: t for t in client.get("/player/titles").json()}
    assert titles["focused_scholar"]["earned"] is True


def test_work_xp_title_not_earned_below_threshold(client, db):
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp)"
        " VALUES ('player_default', 'WORK', 200)"
    )
    db.commit()
    titles = {t["title_id"]: t for t in client.get("/player/titles").json()}
    assert titles["focused_scholar"]["earned"] is False
