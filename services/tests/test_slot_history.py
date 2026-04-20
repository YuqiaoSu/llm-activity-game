"""Tests for GET /places/{id}/slot-history."""
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


def _make_place(db, place_id: str = "p1") -> str:
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, category, state,"
        " item_pool, metadata)"
        " VALUES (?, 'Test Place', 'WORK', '', 'WORK', 'UNLOCKED', '{}', '{}')",
        (place_id,),
    )
    db.commit()
    return place_id


def _make_slot(db, place_id: str, slot_id: str = None) -> str:
    sid = slot_id or str(uuid.uuid4())
    db.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type) VALUES (?, ?, 'ITEM')",
        (sid, place_id),
    )
    db.commit()
    return sid


def _make_item(db, item_id: str = "sword") -> str:
    data = json.dumps({
        "item_id": item_id, "name": item_id, "rarity": "COMMON",
        "category": "WORK", "description": "", "effects": [],
        "icon": "", "stackable": False, "set_id": None,
        "drop_requirement": {"activity_label": None, "min_duration_sec": 0,
                             "min_confidence": 0.0, "time_of_day": None},
    })
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
               (item_id, data))
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, '2025-01-01T00:00:00', 'test')",
        (iid, item_id),
    )
    db.commit()
    return iid


def test_unknown_place_404(client):
    r = client.get("/places/nonexistent/slot-history")
    assert r.status_code == 404


def test_empty_history(client, db):
    place_id = _make_place(db)
    _make_slot(db, place_id)
    r = client.get(f"/places/{place_id}/slot-history")
    assert r.status_code == 200
    assert r.json() == []


def test_assignment_logged(client, db):
    place_id = _make_place(db)
    slot_id  = _make_slot(db, place_id)
    iid      = _make_item(db)

    r = client.put(f"/places/{place_id}/slots/{slot_id}", json={"instance_id": iid})
    assert r.status_code == 200

    hist = client.get(f"/places/{place_id}/slot-history").json()
    assert len(hist) == 1
    assert hist[0]["action"] == "assigned"
    assert hist[0]["instance_id"] == iid
    assert hist[0]["slot_id"] == slot_id


def test_removal_logged(client, db):
    place_id = _make_place(db)
    slot_id  = _make_slot(db, place_id)
    iid      = _make_item(db)

    client.put(f"/places/{place_id}/slots/{slot_id}", json={"instance_id": iid})
    client.put(f"/places/{place_id}/slots/{slot_id}", json={"instance_id": None})

    hist = client.get(f"/places/{place_id}/slot-history").json()
    actions = [h["action"] for h in hist]
    assert "removed" in actions
    assert "assigned" in actions


def test_newest_first_ordering(client, db):
    place_id = _make_place(db)
    slot_id  = _make_slot(db, place_id)
    iid1     = _make_item(db, "sword")
    iid2     = _make_item(db, "shield")

    client.put(f"/places/{place_id}/slots/{slot_id}", json={"instance_id": iid1})
    client.put(f"/places/{place_id}/slots/{slot_id}", json={"instance_id": iid2})

    hist = client.get(f"/places/{place_id}/slot-history").json()
    assert hist[0]["occurred_at"] >= hist[-1]["occurred_at"]


def test_response_shape(client, db):
    place_id = _make_place(db)
    slot_id  = _make_slot(db, place_id)
    iid      = _make_item(db)

    client.put(f"/places/{place_id}/slots/{slot_id}", json={"instance_id": iid})
    entry = client.get(f"/places/{place_id}/slot-history").json()[0]
    for key in ("log_id", "slot_id", "action", "item_id", "instance_id", "occurred_at"):
        assert key in entry


def test_limit_param(client, db):
    place_id = _make_place(db)
    slot_id  = _make_slot(db, place_id)
    for i in range(5):
        iid = _make_item(db, f"item_{i}")
        client.put(f"/places/{place_id}/slots/{slot_id}", json={"instance_id": iid})
    hist = client.get(f"/places/{place_id}/slot-history?limit=3").json()
    assert len(hist) <= 3


def test_isolated_to_place(client, db):
    pid1 = _make_place(db, "place_a")
    pid2 = _make_place(db, "place_b")
    s1   = _make_slot(db, pid1)
    _make_slot(db, pid2)
    iid  = _make_item(db)

    client.put(f"/places/{pid1}/slots/{s1}", json={"instance_id": iid})

    hist_b = client.get(f"/places/{pid2}/slot-history").json()
    assert hist_b == []
