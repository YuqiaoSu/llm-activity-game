"""Tests for GET /player/export (full player data snapshot)."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db


_PLAYER = "player_default"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'Lumi', ?)",
        (_PLAYER, visual),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO player_settings (player_id) VALUES ('player_default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── top-level shape ────────────────────────────────────────────────────────────

def test_export_returns_200(client):
    r = client.get("/player/export")
    assert r.status_code == 200


def test_export_has_all_top_level_keys(client):
    data = client.get("/player/export").json()
    for key in ("profile", "inventory", "achievements", "places", "skills", "weekly_xp_7d", "export_at"):
        assert key in data, f"Missing key: {key}"


def test_export_at_is_iso_string(client):
    data = client.get("/player/export").json()
    export_at: str = data["export_at"]
    assert "T" in export_at  # ISO 8601 datetime separator


# ── profile section ────────────────────────────────────────────────────────────

def test_export_profile_has_character_id(client):
    data = client.get("/player/export").json()
    assert data["profile"]["character_id"] == _PLAYER


# ── inventory section ──────────────────────────────────────────────────────────

def test_export_inventory_is_list(client):
    data = client.get("/player/export").json()
    assert isinstance(data["inventory"], list)


def test_export_inventory_contains_items(client, db):
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES ('inst1', ?, 'item1', '2026-01-01', 'c1')",
        (_PLAYER,),
    )
    db.commit()
    data = client.get("/player/export").json()
    assert any(i["instance_id"] == "inst1" for i in data["inventory"])


# ── achievements section ───────────────────────────────────────────────────────

def test_export_achievements_is_list(client):
    data = client.get("/player/export").json()
    assert isinstance(data["achievements"], list)


def test_export_achievements_has_unlocked_field(client, db):
    db.execute(
        "INSERT INTO achievements (achievement_id, name, description, condition_type, threshold)"
        " VALUES ('ach1', 'First', '', 'total_xp', 1)"
    )
    db.commit()
    data = client.get("/player/export").json()
    for ach in data["achievements"]:
        assert "unlocked" in ach


# ── places section ─────────────────────────────────────────────────────────────

def test_export_places_is_list(client, db):
    db.execute(
        "INSERT INTO places (place_id, name, place_type, description, state, item_pool, xp, level)"
        " VALUES ('home', 'Home', 'STUDY', '', 'UNLOCKED', '[]', 0, 1)"
    )
    db.commit()
    data = client.get("/player/export").json()
    assert isinstance(data["places"], list)
    assert any(p["place_id"] == "home" for p in data["places"])


# ── weekly_xp_7d section ───────────────────────────────────────────────────────

def test_export_weekly_xp_is_list(client):
    data = client.get("/player/export").json()
    assert isinstance(data["weekly_xp_7d"], list)
