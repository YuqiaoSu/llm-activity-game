"""Tests for GET /places/{id}/slot-recommend?locked_only=true."""
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
    db.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type, accepts, occupant_id, metadata)"
        " VALUES ('s1', ?, 'ITEM', NULL, NULL, '{}')",
        (place_id,),
    )
    db.commit()


def _add_item(db, item_id, category="WORK", locked=0):
    data = json.dumps({"name": item_id, "rarity": "COMMON", "category": category})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data))
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, locked)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'test', ?)",
        (iid, item_id, locked),
    )
    db.commit()
    return iid


def test_locked_only_false_returns_all_items(client, db):
    _add_place(db)
    _add_item(db, "unlocked_item", locked=0)
    _add_item(db, "locked_item", locked=1)
    r = client.get("/places/p1/slot-recommend?locked_only=false")
    assert r.status_code == 200
    assert len(r.json()) == 1  # 1 slot, 1 best recommendation


def test_locked_only_true_excludes_unlocked_items(client, db):
    _add_place(db)
    unlocked_iid = _add_item(db, "unlocked_item", locked=0)
    locked_iid = _add_item(db, "locked_item", locked=1)
    r = client.get("/places/p1/slot-recommend?locked_only=true")
    assert r.status_code == 200
    recs = r.json()
    assert len(recs) == 1
    assert recs[0]["recommended_instance_id"] == locked_iid


def test_locked_only_false_is_default(client, db):
    _add_place(db)
    _add_item(db, "unlocked_item", locked=0)
    r1 = client.get("/places/p1/slot-recommend")
    r2 = client.get("/places/p1/slot-recommend?locked_only=false")
    assert r1.json() == r2.json()


def test_locked_item_scored_correctly(client, db):
    _add_place(db, place_type="workshop")  # preferred WORK
    iid = _add_item(db, "locked_work_item", category="WORK", locked=1)
    r = client.get("/places/p1/slot-recommend?locked_only=true")
    assert r.status_code == 200
    recs = r.json()
    assert recs[0]["recommended_instance_id"] == iid


def test_empty_result_when_no_locked_items(client, db):
    _add_place(db)
    _add_item(db, "unlocked_item", locked=0)
    r = client.get("/places/p1/slot-recommend?locked_only=true")
    assert r.status_code == 200
    assert r.json() == []


def test_locked_only_param_defaults_to_false(client, db):
    _add_place(db)
    _add_item(db, "unlocked_item", locked=0)
    r = client.get("/places/p1/slot-recommend")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_correct_shape_with_locked_only(client, db):
    _add_place(db)
    _add_item(db, "locked_item", locked=1)
    r = client.get("/places/p1/slot-recommend?locked_only=true")
    assert r.status_code == 200
    rec = r.json()[0]
    assert "slot_id" in rec
    assert "recommended_instance_id" in rec
    assert "item_name" in rec
    assert "score" in rec
