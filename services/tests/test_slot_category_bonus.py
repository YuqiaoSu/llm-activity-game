"""Tests for _slot_category_bonus and its effect on award_place_xp."""
import json
import sqlite3
import uuid
import pytest

from services.storage.db import init_db
from services.place_service.upgrade import _slot_category_bonus, award_place_xp


def _make_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    return conn


def _make_place(db, place_id: str, place_type: str = "workshop") -> None:
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, category, state,"
        " item_pool, metadata)"
        " VALUES (?, 'T', ?, '', 'WORK', 'UNLOCKED', '{}', '{}')",
        (place_id, place_type),
    )
    db.commit()


def _make_slot(db, place_id: str, slot_id: str, occupant_id: str | None = None) -> None:
    db.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type, accepts, occupant_id, metadata)"
        " VALUES (?, ?, 'ITEM', NULL, ?, '{}')",
        (slot_id, place_id, occupant_id),
    )
    db.commit()


def _make_item(db, item_id: str, category: str) -> str:
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


def test_no_slots_returns_1_0():
    db = _make_db()
    _make_place(db, "p1", "workshop")
    assert _slot_category_bonus(db, "p1") == pytest.approx(1.0)
    db.close()


def test_one_matching_slot_returns_1_05():
    db = _make_db()
    _make_place(db, "p1", "workshop")  # preferred = WORK
    iid = _make_item(db, "work_item", "WORK")
    _make_slot(db, "p1", "s1", iid)
    assert _slot_category_bonus(db, "p1") == pytest.approx(1.05)
    db.close()


def test_three_matching_slots_returns_1_15():
    db = _make_db()
    _make_place(db, "p1", "workshop")
    for i in range(3):
        iid = _make_item(db, f"work_item_{i}", "WORK")
        _make_slot(db, "p1", f"s{i}", iid)
    assert _slot_category_bonus(db, "p1") == pytest.approx(1.15)
    db.close()


def test_bonus_capped_at_1_3():
    db = _make_db()
    _make_place(db, "p1", "workshop")
    for i in range(10):  # 10 × 0.05 = 0.5 → cap at 1.3
        iid = _make_item(db, f"work_item_{i}", "WORK")
        _make_slot(db, "p1", f"s{i}", iid)
    assert _slot_category_bonus(db, "p1") == pytest.approx(1.3)
    db.close()


def test_non_matching_occupant_gives_no_bonus():
    db = _make_db()
    _make_place(db, "p1", "workshop")  # preferred = WORK
    iid = _make_item(db, "social_item", "SOCIAL")
    _make_slot(db, "p1", "s1", iid)
    assert _slot_category_bonus(db, "p1") == pytest.approx(1.0)
    db.close()


def test_empty_slot_gives_no_bonus():
    db = _make_db()
    _make_place(db, "p1", "workshop")
    _make_slot(db, "p1", "s1", None)  # empty slot
    assert _slot_category_bonus(db, "p1") == pytest.approx(1.0)
    db.close()


def test_bonus_reflected_in_xp_awarded():
    db = _make_db()
    _make_place(db, "p1", "workshop")
    iid = _make_item(db, "work_item", "WORK")
    _make_slot(db, "p1", "s1", iid)

    award_place_xp(db, "p1", 100)  # 1.05× bonus → 105 XP expected
    row = db.execute("SELECT xp FROM places WHERE place_id='p1'").fetchone()
    # Mood/streak may adjust slightly; just ensure > 100 due to slot bonus
    assert row["xp"] > 100
    db.close()
