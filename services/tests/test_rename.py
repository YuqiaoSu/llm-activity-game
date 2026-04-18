"""Tests for PATCH /player/profile (companion rename)."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import init_db


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'Lumi', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db))


def test_rename_returns_200(client):
    resp = client.patch("/player/profile", json={"name": "Sparky"})
    assert resp.status_code == 200


def test_rename_updates_name(client):
    client.patch("/player/profile", json={"name": "Sparky"})
    profile = client.get("/player/profile").json()
    assert profile["name"] == "Sparky"


def test_rename_returns_updated_profile(client):
    resp = client.patch("/player/profile", json={"name": "Nova"})
    assert resp.json()["name"] == "Nova"


def test_rename_strips_whitespace(client):
    resp = client.patch("/player/profile", json={"name": "  Blaze  "})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Blaze"


def test_rename_rejects_empty_string(client):
    resp = client.patch("/player/profile", json={"name": ""})
    assert resp.status_code == 422


def test_rename_rejects_whitespace_only(client):
    resp = client.patch("/player/profile", json={"name": "   "})
    assert resp.status_code == 422


def test_rename_rejects_too_long(client):
    resp = client.patch("/player/profile", json={"name": "A" * 25})
    assert resp.status_code == 422


def test_rename_accepts_exactly_24_chars(client):
    name = "A" * 24
    resp = client.patch("/player/profile", json={"name": name})
    assert resp.status_code == 200
    assert resp.json()["name"] == name


def test_rename_missing_name_field_rejected(client):
    resp = client.patch("/player/profile", json={})
    assert resp.status_code == 422
