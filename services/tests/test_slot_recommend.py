"""Tests for GET /places/{id}/slot-recommend."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})
_POOL = json.dumps({"rarities": [], "categories": [], "required_tags": []})


def _item_data(item_id: str, rarity: str = "COMMON", category: str = "WORK") -> str:
    return json.dumps({
        "item_id": item_id, "name": item_id, "rarity": rarity,
        "category": category, "description": "", "effects": [],
        "icon": "", "stackable": False, "set_id": None,
        "drop_requirement": {"activity_label": None, "min_duration_sec": 0,
                             "min_confidence": 0.0, "time_of_day": None},
    })


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
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES ('player_default', 'WORK', 10)"
    )
    # Seed one place and one empty slot
    conn.execute(
        "INSERT INTO places (place_id, name, state, place_type, item_pool)"
        " VALUES ('lib1', 'Library', 'UNLOCKED', 'library', ?)",
        (_POOL,),
    )
    conn.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type, accepts)"
        " VALUES ('slot1', 'lib1', 'ITEM', NULL)"
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _add_item(db, item_id: str, rarity: str = "COMMON", category: str = "WORK"):
    import uuid
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
               (item_id, _item_data(item_id, rarity, category)))
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, '2025-01-01T00:00:00', 'test')",
        (str(uuid.uuid4()), item_id),
    )
    db.commit()


def test_unknown_place_404(client):
    r = client.get("/places/nope/slot-recommend")
    assert r.status_code == 404


def test_no_inventory_returns_empty(client):
    r = client.get("/places/lib1/slot-recommend")
    assert r.status_code == 200
    assert r.json() == []


def test_all_slots_filled_returns_empty(client, db):
    import uuid
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES ('i1', ?)",
               (_item_data("i1"),))
    iid = str(uuid.uuid4())
    db.execute("INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
               " VALUES (?, 'player_default', 'i1', '2025-01-01T00:00:00', 'test')", (iid,))
    db.execute("UPDATE place_slots SET occupant_id=? WHERE slot_id='slot1'", (iid,))
    db.commit()
    r = client.get("/places/lib1/slot-recommend")
    assert r.json() == []


def test_recommendation_shape(client, db):
    _add_item(db, "itm1")
    r = client.get("/places/lib1/slot-recommend")
    assert r.status_code == 200
    recs = r.json()
    assert len(recs) >= 1
    rec = recs[0]
    assert "slot_id" in rec
    assert "recommended_instance_id" in rec
    assert "item_name" in rec
    assert "item_rarity" in rec
    assert "score" in rec


def test_higher_rarity_wins_tie(client, db):
    _add_item(db, "common1", "COMMON", "WORK")
    _add_item(db, "rare1", "RARE", "WORK")
    r = client.get("/places/lib1/slot-recommend")
    recs = r.json()
    assert recs[0]["item_name"] == "rare1"


def test_category_match_beats_rarity(client, db):
    # Slot has accepts=LEARN filter
    db.execute("UPDATE place_slots SET accepts='[\"LEARN\"]' WHERE slot_id='slot1'")
    db.commit()
    _add_item(db, "legendary_work", "LEGENDARY", "WORK")
    _add_item(db, "common_learn", "COMMON", "LEARN")
    r = client.get("/places/lib1/slot-recommend")
    recs = r.json()
    # LEGENDARY WORK doesn't match accepts=LEARN → common_learn wins
    assert recs[0]["item_name"] == "common_learn"


def test_correct_slot_id_returned(client, db):
    _add_item(db, "i1")
    r = client.get("/places/lib1/slot-recommend")
    assert r.json()[0]["slot_id"] == "slot1"


def test_already_placed_item_excluded(client, db):
    import uuid
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES ('placed', ?)",
               (_item_data("placed"),))
    placed_iid = str(uuid.uuid4())
    db.execute("INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
               " VALUES (?, 'player_default', 'placed', '2025-01-01T00:00:00', 'test')", (placed_iid,))
    # Place it in a DIFFERENT slot
    db.execute("INSERT INTO place_slots (slot_id, place_id, slot_type) VALUES ('slot2', 'lib1', 'ITEM')")
    db.execute("UPDATE place_slots SET occupant_id=? WHERE slot_id='slot2'", (placed_iid,))
    _add_item(db, "free1")
    db.commit()
    r = client.get("/places/lib1/slot-recommend")
    recs = r.json()
    # Recommendation should be free1, not placed
    assert all(rec["item_name"] != "placed" for rec in recs)
