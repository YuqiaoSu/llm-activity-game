"""Tests for GET /inventory/tags."""
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


def _add_item(db, item_id: str, tags: list[str]) -> str:
    data = json.dumps({"name": item_id, "rarity": "COMMON", "category": "WORK"})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data))
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, tags)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'test', ?)",
        (iid, item_id, json.dumps(tags)),
    )
    db.commit()
    return iid


def test_empty_when_no_items_tagged(client, db):
    r = client.get("/inventory/tags")
    assert r.status_code == 200
    assert r.json() == {"tags": []}


def test_returns_used_tags(client, db):
    _add_item(db, "itm1", ["focus", "work"])
    r = client.get("/inventory/tags")
    tags = r.json()["tags"]
    assert "focus" in tags
    assert "work" in tags


def test_deduplicates_tags(client, db):
    _add_item(db, "itm1", ["focus"])
    _add_item(db, "itm2", ["focus"])
    r = client.get("/inventory/tags")
    assert r.json()["tags"].count("focus") == 1


def test_sorted_alphabetically(client, db):
    _add_item(db, "itm1", ["zebra", "apple", "mango"])
    tags = client.get("/inventory/tags").json()["tags"]
    assert tags == sorted(tags)


def test_tags_from_multiple_items_merged(client, db):
    _add_item(db, "itm1", ["alpha"])
    _add_item(db, "itm2", ["beta"])
    tags = client.get("/inventory/tags").json()["tags"]
    assert "alpha" in tags
    assert "beta" in tags


def test_correct_shape(client, db):
    r = client.get("/inventory/tags")
    assert r.status_code == 200
    body = r.json()
    assert "tags" in body
    assert isinstance(body["tags"], list)
