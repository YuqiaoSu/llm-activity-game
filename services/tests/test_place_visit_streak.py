"""Tests for place visit streak (POST /places/{id}/visit streak_days field)."""
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


def _make_place(db, place_id: str = "p1") -> str:
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, category, state,"
        " item_pool, metadata)"
        " VALUES (?, 'Test Place', 'WORK', '', 'WORK', 'UNLOCKED', '{}', '{}')",
        (place_id,),
    )
    db.commit()
    return place_id


def _set_last_visit(db, place_id: str, days_ago: int) -> None:
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    db.execute(
        "UPDATE places SET last_visit_date=? WHERE place_id=?", (d, place_id)
    )
    db.commit()


def test_first_visit_sets_streak_1(client, db):
    _make_place(db)
    r = client.post("/places/p1/visit")
    assert r.status_code == 200
    assert r.json()["streak_days"] == 1


def test_same_day_visit_keeps_streak(client, db):
    _make_place(db)
    client.post("/places/p1/visit")
    # simulate today already set
    _set_last_visit(db, "p1", 0)
    db.execute("UPDATE places SET visit_streak=3 WHERE place_id='p1'")
    db.commit()
    r = client.post("/places/p1/visit")
    assert r.json()["streak_days"] == 3


def test_next_day_visit_increments(client, db):
    _make_place(db)
    _set_last_visit(db, "p1", 1)
    db.execute("UPDATE places SET visit_streak=2 WHERE place_id='p1'")
    db.commit()
    r = client.post("/places/p1/visit")
    assert r.json()["streak_days"] == 3


def test_gap_resets_streak_to_1(client, db):
    _make_place(db)
    _set_last_visit(db, "p1", 5)
    db.execute("UPDATE places SET visit_streak=10 WHERE place_id='p1'")
    db.commit()
    r = client.post("/places/p1/visit")
    assert r.json()["streak_days"] == 1


def test_streak_in_response(client, db):
    _make_place(db)
    r = client.post("/places/p1/visit")
    body = r.json()
    assert "streak_days" in body
    assert isinstance(body["streak_days"], int)


def test_isolated_per_place(client, db):
    _make_place(db, "place_a")
    _make_place(db, "place_b")
    _set_last_visit(db, "place_a", 1)
    db.execute("UPDATE places SET visit_streak=5 WHERE place_id='place_a'")
    db.commit()
    r_a = client.post("/places/place_a/visit")
    r_b = client.post("/places/place_b/visit")
    assert r_a.json()["streak_days"] == 6
    assert r_b.json()["streak_days"] == 1


def test_streak_in_get_places(client, db):
    _make_place(db)
    _set_last_visit(db, "p1", 1)
    db.execute("UPDATE places SET visit_streak=4 WHERE place_id='p1'")
    db.commit()
    places = client.get("/places").json()
    p = next((x for x in places if x["place_id"] == "p1"), None)
    assert p is not None
    assert p["visit_streak"] == 4
