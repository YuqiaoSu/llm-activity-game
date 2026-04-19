"""Tests for GET /inventory?tag=X (tag-based inventory filter)."""
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
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', ?)",
        (_PLAYER, visual),
    )
    # Two item types
    for iid in ("herb_sprig", "iron_ore"):
        conn.execute(
            "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
            (iid, json.dumps({"name": iid, "rarity": "COMMON", "category": "NATURE",
                               "icon": None, "description": "", "effects": []})),
        )
    # herb_sprig instance tagged ["rare-find", "nature"]
    conn.execute(
        "INSERT INTO inventory (instance_id, item_id, character_id, acquired_at, source_chunk, tags)"
        " VALUES ('inst-herb', 'herb_sprig', ?, '2026-01-01', 'test', ?)",
        (_PLAYER, json.dumps(["rare-find", "nature"])),
    )
    # iron_ore instance with no tags
    conn.execute(
        "INSERT INTO inventory (instance_id, item_id, character_id, acquired_at, source_chunk)"
        " VALUES ('inst-iron', 'iron_ore', ?, '2026-01-01', 'test')",
        (_PLAYER,),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


# ── basic filter ───────────────────────────────────────────────────────────────

def test_no_tag_returns_all(client):
    r = client.get("/inventory")
    assert r.status_code == 200
    ids = [i["item_id"] for i in r.json()]
    assert "herb_sprig" in ids
    assert "iron_ore" in ids


def test_tag_filter_matches_tagged_item(client):
    r = client.get("/inventory?tag=rare-find")
    assert r.status_code == 200
    ids = [i["item_id"] for i in r.json()]
    assert "herb_sprig" in ids
    assert "iron_ore" not in ids


def test_tag_filter_excludes_untagged(client):
    r = client.get("/inventory?tag=nature")
    ids = [i["item_id"] for i in r.json()]
    assert "iron_ore" not in ids


def test_tag_filter_case_insensitive(client):
    r = client.get("/inventory?tag=RARE-FIND")
    ids = [i["item_id"] for i in r.json()]
    assert "herb_sprig" in ids


def test_tag_no_match_returns_empty(client):
    r = client.get("/inventory?tag=nonexistent-tag")
    assert r.status_code == 200
    assert r.json() == []


def test_empty_tag_param_returns_all(client):
    r = client.get("/inventory?tag=")
    ids = [i["item_id"] for i in r.json()]
    assert len(ids) == 2


def test_tag_whitespace_stripped(client):
    r = client.get("/inventory?tag=  rare-find  ")
    ids = [i["item_id"] for i in r.json()]
    assert "herb_sprig" in ids
