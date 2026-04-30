"""Tests for GET /places/{id}/slot-stats."""
import json
import sqlite3
import uuid
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


def _add_place(db, place_id="p1", place_type="workshop"):
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, category, state,"
        " item_pool, metadata) VALUES (?, 'T', ?, '', 'WORK', 'UNLOCKED', '{}', '{}')",
        (place_id, place_type),
    )
    db.commit()


def _add_slot(db, place_id, slot_id, occupant_id=None):
    db.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type, accepts, occupant_id, metadata)"
        " VALUES (?, ?, 'ITEM', NULL, ?, '{}')",
        (slot_id, place_id, occupant_id),
    )
    db.commit()


def _add_item(db, item_id, category="WORK"):
    data = json.dumps({"name": item_id, "rarity": "COMMON", "category": category})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data))
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'test')",
        (iid, item_id),
    )
    db.commit()
    return iid


def test_correct_shape(client, db):
    _add_place(db)
    _add_slot(db, "p1", "s1")
    r = client.get("/places/p1/slot-stats")
    assert r.status_code == 200
    body = r.json()
    for key in ("total_slots", "filled_slots", "empty_slots", "fill_pct", "matching_pct"):
        assert key in body


def test_zero_slots(client, db):
    _add_place(db)
    r = client.get("/places/p1/slot-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_slots"] == 0
    assert body["fill_pct"] == 0.0


def test_all_empty(client, db):
    _add_place(db)
    _add_slot(db, "p1", "s1")
    _add_slot(db, "p1", "s2")
    body = client.get("/places/p1/slot-stats").json()
    assert body["filled_slots"] == 0
    assert body["empty_slots"] == 2
    assert body["fill_pct"] == 0.0


def test_all_filled(client, db):
    _add_place(db, place_type="workshop")  # preferred WORK
    iid1 = _add_item(db, "w1", "WORK")
    iid2 = _add_item(db, "w2", "WORK")
    _add_slot(db, "p1", "s1", iid1)
    _add_slot(db, "p1", "s2", iid2)
    body = client.get("/places/p1/slot-stats").json()
    assert body["filled_slots"] == 2
    assert body["empty_slots"] == 0
    assert body["fill_pct"] == 100.0


def test_matching_pct_50(client, db):
    _add_place(db, place_type="workshop")  # preferred WORK
    iid_work   = _add_item(db, "w1", "WORK")
    iid_social = _add_item(db, "s1", "SOCIAL")
    _add_slot(db, "p1", "s1", iid_work)
    _add_slot(db, "p1", "s2", iid_social)
    body = client.get("/places/p1/slot-stats").json()
    assert body["matching_pct"] == 50.0


def test_404_on_unknown_place(client, db):
    r = client.get("/places/nonexistent/slot-stats")
    assert r.status_code == 404
