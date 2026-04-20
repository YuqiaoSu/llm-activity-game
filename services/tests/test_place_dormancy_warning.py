"""Tests for days_since_visit field in GET /places."""
import json
import sqlite3
import pytest
from datetime import date, timedelta
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


def _add_place(db, place_id="p1", last_visit_date=None):
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, category, state,"
        " item_pool, metadata, last_visit_date)"
        " VALUES (?, 'T', 'workshop', '', 'WORK', 'UNLOCKED', '{}', '{}', ?)",
        (place_id, last_visit_date),
    )
    db.commit()


def test_field_present_in_get_places(client, db):
    _add_place(db)
    r = client.get("/places")
    assert r.status_code == 200
    place = next(p for p in r.json() if p["place_id"] == "p1")
    assert "days_since_visit" in place


def test_null_when_never_visited(client, db):
    _add_place(db, last_visit_date=None)
    r = client.get("/places")
    place = next(p for p in r.json() if p["place_id"] == "p1")
    assert place["days_since_visit"] is None


def test_zero_when_visited_today(client, db):
    today = date.today().isoformat()
    _add_place(db, last_visit_date=today)
    r = client.get("/places")
    place = next(p for p in r.json() if p["place_id"] == "p1")
    assert place["days_since_visit"] == 0


def test_seven_when_visited_seven_days_ago(client, db):
    seven_ago = (date.today() - timedelta(days=7)).isoformat()
    _add_place(db, last_visit_date=seven_ago)
    r = client.get("/places")
    place = next(p for p in r.json() if p["place_id"] == "p1")
    assert place["days_since_visit"] == 7


def test_distinct_per_place(client, db):
    today = date.today().isoformat()
    three_ago = (date.today() - timedelta(days=3)).isoformat()
    _add_place(db, "p1", last_visit_date=today)
    _add_place(db, "p2", last_visit_date=three_ago)
    places = {p["place_id"]: p for p in client.get("/places").json()}
    assert places["p1"]["days_since_visit"] == 0
    assert places["p2"]["days_since_visit"] == 3


def test_no_change_to_visit_endpoint(client, db):
    _add_place(db)
    r = client.post("/places/p1/visit")
    assert r.status_code == 200
    assert "streak_days" in r.json()
