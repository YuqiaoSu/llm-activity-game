"""Tests for place set bonus detection (compute_set_bonuses)."""
import json
import sqlite3
import pytest
from services.storage.db import init_db
from services.place_service.effects import compute_set_bonuses, _DEFAULT_SET_BONUS_FACTOR


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")  # allow synthetic occupant_ids in tests
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    # Seed two item defs: same category
    for item_id, cat in [("item_a", "WORK"), ("item_b", "WORK"), ("item_c", "EXPLORE")]:
        conn.execute(
            "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
            (item_id, json.dumps({
                "item_id": item_id, "name": item_id, "rarity": "COMMON", "category": cat,
                "icon": "x.png", "effects": [], "drop_requirement": {}, "description": "",
                "stackable": False,
            })),
        )
    # Seed a place with 2 slots
    conn.execute(
        "INSERT INTO places (place_id, name, place_type, item_pool, metadata) "
        "VALUES ('forest', 'Forest', 'FIELD', '{}', '{}')"
    )
    conn.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type, metadata) "
        "VALUES ('slot_1', 'forest', 'ITEM', '{}')"
    )
    conn.execute(
        "INSERT INTO place_slots (slot_id, place_id, slot_type, metadata) "
        "VALUES ('slot_2', 'forest', 'ITEM', '{}')"
    )
    # Seed inventory instances
    for inst_id, item_id in [("inst_a", "item_a"), ("inst_b", "item_b"), ("inst_c", "item_c")]:
        conn.execute(
            "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
            "VALUES (?, 'player_default', ?, '2026-01-01', 'chunk1')",
            (inst_id, item_id),
        )
    conn.commit()
    yield conn
    conn.close()


def _fill_slots(db, slot1_inst: str | None, slot2_inst: str | None) -> None:
    db.execute("UPDATE place_slots SET occupant_id=? WHERE slot_id='slot_1'", (slot1_inst,))
    db.execute("UPDATE place_slots SET occupant_id=? WHERE slot_id='slot_2'", (slot2_inst,))
    db.commit()


# ── no bonus ──────────────────────────────────────────────────────────────────

def test_no_bonus_when_slots_empty(db):
    assert compute_set_bonuses(db) == []


def test_no_bonus_when_one_slot_empty(db):
    _fill_slots(db, "inst_a", None)
    assert compute_set_bonuses(db) == []


def test_no_bonus_when_mixed_categories(db):
    _fill_slots(db, "inst_a", "inst_c")   # WORK + EXPLORE
    assert compute_set_bonuses(db) == []


# ── bonus active ──────────────────────────────────────────────────────────────

def test_bonus_when_all_slots_same_category(db):
    _fill_slots(db, "inst_a", "inst_b")   # both WORK
    bonuses = compute_set_bonuses(db)
    assert len(bonuses) == 1
    assert bonuses[0].effect_type == "set_bonus"
    assert bonuses[0].target == "forest"
    assert bonuses[0].params["category"] == "WORK"


def test_bonus_uses_default_factor(db):
    _fill_slots(db, "inst_a", "inst_b")
    bonus = compute_set_bonuses(db)[0]
    assert bonus.params["factor"] == _DEFAULT_SET_BONUS_FACTOR


def test_bonus_respects_custom_factor(db):
    db.execute("UPDATE places SET metadata='{\"set_bonus_factor\": 2.0}' WHERE place_id='forest'")
    db.commit()
    _fill_slots(db, "inst_a", "inst_b")
    bonus = compute_set_bonuses(db)[0]
    assert bonus.params["factor"] == pytest.approx(2.0)


# ── agent integration: xp multiplier ─────────────────────────────────────────

def test_aggregate_xp_multiplier_includes_set_bonus():
    from services.sync_agent.agent import SyncAgent
    from services.models.item import Effect
    effects = [Effect(effect_type="set_bonus", target="forest", params={"factor": 1.5})]
    assert SyncAgent._aggregate_xp_multiplier(effects) == pytest.approx(1.5)


def test_aggregate_xp_multiplier_stacks_set_bonus_and_item_effect():
    from services.sync_agent.agent import SyncAgent
    from services.models.item import Effect
    effects = [
        Effect(effect_type="xp_multiplier", target="", params={"factor": 1.2}),
        Effect(effect_type="set_bonus", target="forest", params={"factor": 1.5}),
    ]
    assert SyncAgent._aggregate_xp_multiplier(effects) == pytest.approx(1.2 * 1.5)


# ── API response ──────────────────────────────────────────────────────────────

def test_places_api_includes_set_bonus_inactive(db):
    from fastapi.testclient import TestClient
    from services.api.main import create_app
    client = TestClient(create_app(db=db))
    data = client.get("/places").json()
    assert len(data) == 1
    assert data[0]["set_bonus_active"] is False
    assert data[0]["set_bonus_factor"] is None


def test_places_api_includes_set_bonus_active(db):
    from fastapi.testclient import TestClient
    from services.api.main import create_app
    _fill_slots(db, "inst_a", "inst_b")
    client = TestClient(create_app(db=db))
    data = client.get("/places").json()
    assert data[0]["set_bonus_active"] is True
    assert data[0]["set_bonus_factor"] == pytest.approx(_DEFAULT_SET_BONUS_FACTOR)
