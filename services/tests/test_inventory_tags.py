"""Tests for PATCH /inventory/instances/{id}/tags (item tagging)."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db


_PLAYER = "player_default"
_INSTANCE = "inst-tag-01"
_ITEM = "herb_sprig"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', ?)",
        (_PLAYER, visual),
    )
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        (_ITEM, json.dumps({"name": "Herb", "rarity": "COMMON", "category": "NATURE",
                             "icon": None, "description": "", "effects": []})),
    )
    conn.execute(
        "INSERT INTO inventory (instance_id, item_id, character_id, acquired_at, source_chunk) "
        "VALUES (?, ?, ?, '2026-01-01', 'test')",
        (_INSTANCE, _ITEM, _PLAYER),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── happy path ─────────────────────────────────────────────────────────────────

def test_patch_tags_returns_200(client):
    r = client.patch(f"/inventory/instances/{_INSTANCE}/tags", json={"tags": ["fav", "rare"]})
    assert r.status_code == 200


def test_patch_tags_response_contains_tags(client):
    r = client.patch(f"/inventory/instances/{_INSTANCE}/tags", json={"tags": ["fav", "rare"]})
    data = r.json()
    assert data["instance_id"] == _INSTANCE
    assert data["tags"] == ["fav", "rare"]


def test_patch_tags_persists_to_db(client, db):
    client.patch(f"/inventory/instances/{_INSTANCE}/tags", json={"tags": ["keep"]})
    row = db.execute("SELECT tags FROM inventory WHERE instance_id=?", (_INSTANCE,)).fetchone()
    assert json.loads(row["tags"]) == ["keep"]


def test_patch_tags_empty_list_clears(client, db):
    client.patch(f"/inventory/instances/{_INSTANCE}/tags", json={"tags": ["a", "b"]})
    client.patch(f"/inventory/instances/{_INSTANCE}/tags", json={"tags": []})
    row = db.execute("SELECT tags FROM inventory WHERE instance_id=?", (_INSTANCE,)).fetchone()
    assert json.loads(row["tags"]) == []


def test_patch_tags_strips_whitespace(client):
    r = client.patch(f"/inventory/instances/{_INSTANCE}/tags", json={"tags": ["  hello  "]})
    assert r.json()["tags"] == ["hello"]


def test_patch_tags_ignores_empty_strings(client):
    r = client.patch(f"/inventory/instances/{_INSTANCE}/tags", json={"tags": ["", "ok", ""]})
    assert r.json()["tags"] == ["ok"]


def test_inventory_get_exposes_tags_field(client, db):
    client.patch(f"/inventory/instances/{_INSTANCE}/tags", json={"tags": ["mytag"]})
    items = client.get("/inventory").json()
    item = next((i for i in items if i["item_id"] == _ITEM), None)
    assert item is not None
    assert "tags" in item
    assert "mytag" in item["tags"]


# ── validation errors ──────────────────────────────────────────────────────────

def test_patch_tags_rejects_more_than_3(client):
    r = client.patch(f"/inventory/instances/{_INSTANCE}/tags",
                     json={"tags": ["a", "b", "c", "d"]})
    assert r.status_code == 422


def test_patch_tags_rejects_tag_over_12_chars(client):
    r = client.patch(f"/inventory/instances/{_INSTANCE}/tags",
                     json={"tags": ["thirteenchars"]})  # 13 chars
    assert r.status_code == 422


def test_patch_tags_accepts_exactly_12_chars(client):
    r = client.patch(f"/inventory/instances/{_INSTANCE}/tags",
                     json={"tags": ["123456789012"]})  # exactly 12
    assert r.status_code == 200


def test_patch_tags_404_on_missing_instance(client):
    r = client.patch("/inventory/instances/no-such-id/tags", json={"tags": ["x"]})
    assert r.status_code == 404
