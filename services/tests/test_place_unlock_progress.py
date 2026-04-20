"""Tests for unlock_progress field in GET /places."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (_VISUAL,),
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


def _add_place(db, place_id, state="UNLOCKED", unlock_condition=None):
    cond_json = json.dumps(unlock_condition) if unlock_condition else None
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, category, state,"
        " item_pool, metadata, unlock_condition)"
        " VALUES (?, 'T', 'workshop', '', 'WORK', ?, '{}', '{}', ?)",
        (place_id, state, cond_json),
    )
    db.commit()


def _set_player_xp(db, xp: int):
    db.execute(
        "INSERT OR REPLACE INTO player_category_xp (character_id, category, xp)"
        " VALUES ('player_default', 'WORK', ?)",
        (xp,),
    )
    db.commit()


def test_field_present_for_locked_places(client, db):
    _add_place(db, "p1", state="LOCKED",
               unlock_condition={"condition_type": "player_level", "params": {"min_level": 5}})
    places = {p["place_id"]: p for p in client.get("/places").json()}
    assert "unlock_progress" in places["p1"]
    assert places["p1"]["unlock_progress"] is not None


def test_null_for_unlocked_places(client, db):
    _add_place(db, "p1", state="UNLOCKED")
    places = {p["place_id"]: p for p in client.get("/places").json()}
    assert places["p1"]["unlock_progress"] is None


def test_pct_zero_at_level_1_needing_level_5(client, db):
    _add_place(db, "p1", state="LOCKED",
               unlock_condition={"condition_type": "player_level", "params": {"min_level": 5}})
    # Player has 0 XP → level 1; 1/5 = 20%
    places = {p["place_id"]: p for p in client.get("/places").json()}
    prog = places["p1"]["unlock_progress"]
    assert prog["current_level"] == 1
    assert prog["required_level"] == 5
    assert prog["pct"] == 20


def test_pct_60_at_level_3_needing_level_5(client, db):
    _add_place(db, "p1", state="LOCKED",
               unlock_condition={"condition_type": "player_level", "params": {"min_level": 5}})
    # Level 3 requires 200 XP (threshold for level 3 = 2²×50 = 200)
    _set_player_xp(db, 200)
    places = {p["place_id"]: p for p in client.get("/places").json()}
    prog = places["p1"]["unlock_progress"]
    assert prog["current_level"] == 3
    assert prog["pct"] == 60


def test_pct_100_when_player_meets_requirement(client, db):
    _add_place(db, "p1", state="LOCKED",
               unlock_condition={"condition_type": "player_level", "params": {"min_level": 3}})
    _set_player_xp(db, 450)  # level 4
    places = {p["place_id"]: p for p in client.get("/places").json()}
    prog = places["p1"]["unlock_progress"]
    assert prog["pct"] == 100


def test_correct_shape(client, db):
    _add_place(db, "p1", state="LOCKED",
               unlock_condition={"condition_type": "player_level", "params": {"min_level": 5}})
    places = {p["place_id"]: p for p in client.get("/places").json()}
    prog = places["p1"]["unlock_progress"]
    assert "current_level" in prog
    assert "required_level" in prog
    assert "pct" in prog
