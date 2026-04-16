"""Tests for slot-type filtering: accepts validation and occupant_matches_theme."""
from __future__ import annotations

import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db


def _seed_item(conn, item_id: str, category: str = "WORK") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, json.dumps({
            "item_id": item_id, "name": item_id.replace("_", " ").title(),
            "rarity": "COMMON", "category": category,
            "icon": "", "effects": [], "drop_requirement": {}, "description": "",
        })),
    )


def _seed_instance(conn, instance_id: str, item_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO inventory "
        "(instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES (?, 'player_default', ?, '2026-01-01', 'c1')",
        (instance_id, item_id),
    )


def _seed_place_with_slot(conn, place_id: str, slot_id: str, accepts=None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO places "
        "(place_id, name, place_type, state, item_pool, metadata) "
        "VALUES (?, ?, 'home', 'UNLOCKED', '{}', '{}')",
        (place_id, place_id.title()),
    )
    accepts_json = json.dumps(accepts) if accepts is not None else None
    conn.execute(
        "INSERT OR IGNORE INTO place_slots "
        "(slot_id, place_id, slot_type, accepts, metadata) "
        "VALUES (?, ?, 'ITEM', ?, '{}')",
        (slot_id, place_id, accepts_json),
    )


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")

    # Two items in different categories
    _seed_item(conn, "work_item", "WORK")
    _seed_item(conn, "game_item", "GAME")
    _seed_instance(conn, "work_inst", "work_item")
    _seed_instance(conn, "game_inst", "game_item")

    # Place with a WORK-only slot
    _seed_place_with_slot(conn, "office", "office_slot", accepts=["WORK"])
    # Place with a no-filter slot
    _seed_place_with_slot(conn, "home", "home_slot", accepts=None)

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    app = create_app(db=db)
    return TestClient(app)


# ── assign_slot accepts validation ───────────────────────────────────────────

def test_assign_matching_category_succeeds(client):
    r = client.put("/places/office/slots/office_slot", json={"instance_id": "work_inst"})
    assert r.status_code == 200


def test_assign_wrong_category_rejected(client):
    r = client.put("/places/office/slots/office_slot", json={"instance_id": "game_inst"})
    assert r.status_code == 400
    assert "WORK" in r.json()["detail"]


def test_assign_any_category_to_unfiltered_slot(client):
    r = client.put("/places/home/slots/home_slot", json={"instance_id": "game_inst"})
    assert r.status_code == 200


def test_remove_occupant_always_allowed(client):
    # First assign, then remove
    client.put("/places/office/slots/office_slot", json={"instance_id": "work_inst"})
    r = client.put("/places/office/slots/office_slot", json={"instance_id": None})
    assert r.status_code == 200


# ── occupant_matches_theme enrichment ─────────────────────────────────────────

def test_matching_occupant_has_theme_true(client, db):
    db.execute(
        "UPDATE place_slots SET occupant_id='work_inst' WHERE slot_id='office_slot'"
    )
    db.commit()
    r = client.get("/places/office")
    slot = r.json()["slots"][0]
    assert slot["occupant_matches_theme"] is True


def test_mismatched_occupant_has_theme_false(client, db):
    # Force a mismatched occupant directly in the DB (bypassing API validation)
    db.execute(
        "UPDATE place_slots SET occupant_id='game_inst' WHERE slot_id='office_slot'"
    )
    db.commit()
    r = client.get("/places/office")
    slot = r.json()["slots"][0]
    assert slot["occupant_matches_theme"] is False


def test_unfiltered_slot_occupant_always_matches(client, db):
    db.execute(
        "UPDATE place_slots SET occupant_id='game_inst' WHERE slot_id='home_slot'"
    )
    db.commit()
    r = client.get("/places/home")
    slot = r.json()["slots"][0]
    assert slot["occupant_matches_theme"] is True


def test_empty_slot_matches_theme_false(client):
    r = client.get("/places/office")
    slot = r.json()["slots"][0]
    assert slot["occupant_id"] is None
    assert slot["occupant_matches_theme"] is False


def test_accepts_field_present_in_slot_response(client):
    r = client.get("/places/office")
    slot = r.json()["slots"][0]
    assert slot["accepts"] == ["WORK"]


def test_places_list_includes_slot_accepts(client):
    r = client.get("/places")
    office = next(p for p in r.json() if p["place_id"] == "office")
    slot = office["slots"][0]
    assert slot["accepts"] == ["WORK"]


# ── case-insensitive matching ──────────────────────────────────────────────────

def test_category_check_is_case_insensitive(client, db):
    # Add a slot with lowercase accepts
    db.execute(
        "INSERT OR IGNORE INTO place_slots "
        "(slot_id, place_id, slot_type, accepts, metadata) "
        "VALUES ('lower_slot', 'home', 'ITEM', '[\"work\"]', '{}')"
    )
    db.commit()
    r = client.put("/places/home/slots/lower_slot", json={"instance_id": "work_inst"})
    assert r.status_code == 200
