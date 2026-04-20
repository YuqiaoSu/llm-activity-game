"""Tests for POST /places/{id}/visit and GET /places/{id}/visits."""
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


def _make_place(db, place_id: str = "p1") -> str:
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, category, state,"
        " item_pool, metadata)"
        " VALUES (?, 'Test Place', 'WORK', '', 'WORK', 'UNLOCKED', '{}', '{}')",
        (place_id,),
    )
    db.commit()
    return place_id


def test_visit_unknown_place_404(client):
    r = client.post("/places/nonexistent/visit")
    assert r.status_code == 404


def test_visits_unknown_place_404(client):
    r = client.get("/places/nonexistent/visits")
    assert r.status_code == 404


def test_records_visit(client, db):
    _make_place(db)
    r = client.post("/places/p1/visit")
    assert r.status_code == 200
    body = r.json()
    assert body["place_id"] == "p1"
    assert "log_id" in body
    assert "visited_at" in body


def test_empty_visits(client, db):
    _make_place(db)
    visits = client.get("/places/p1/visits").json()
    assert visits == []


def test_multiple_visits_accumulate(client, db):
    _make_place(db)
    client.post("/places/p1/visit")
    client.post("/places/p1/visit")
    client.post("/places/p1/visit")
    visits = client.get("/places/p1/visits").json()
    assert len(visits) == 3


def test_newest_first_ordering(client, db):
    _make_place(db)
    client.post("/places/p1/visit")
    client.post("/places/p1/visit")
    visits = client.get("/places/p1/visits").json()
    assert visits[0]["visited_at"] >= visits[-1]["visited_at"]


def test_limit_param(client, db):
    _make_place(db)
    for _ in range(5):
        client.post("/places/p1/visit")
    visits = client.get("/places/p1/visits?limit=2").json()
    assert len(visits) <= 2


def test_response_shape(client, db):
    _make_place(db)
    client.post("/places/p1/visit")
    entry = client.get("/places/p1/visits").json()[0]
    for key in ("log_id", "place_id", "visited_at"):
        assert key in entry


def test_isolated_to_place(client, db):
    _make_place(db, "place_a")
    _make_place(db, "place_b")
    client.post("/places/place_a/visit")
    visits_b = client.get("/places/place_b/visits").json()
    assert visits_b == []
