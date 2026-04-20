"""Tests for GET /inventory/crafting-history?action=upgrade|craft."""
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


_ts_counter = 0


def _insert_log(db, action: str, result_item_id: str = "itm", result_rarity: str = "COMMON"):
    global _ts_counter
    _ts_counter += 1
    log_id = str(uuid.uuid4())
    happened_at = f"2026-01-{_ts_counter:02d}T00:00:00"
    db.execute(
        "INSERT INTO crafting_log (log_id, player_id, action, source_ids, result_item_id,"
        " result_rarity, happened_at) VALUES (?, 'player_default', ?, '[]', ?, ?, ?)",
        (log_id, action, result_item_id, result_rarity, happened_at),
    )
    db.commit()
    return log_id


def test_no_filter_returns_all(client, db):
    _insert_log(db, "upgrade")
    _insert_log(db, "craft")
    r = client.get("/inventory/crafting-history")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_action_upgrade_returns_only_upgrades(client, db):
    _insert_log(db, "upgrade")
    _insert_log(db, "craft")
    r = client.get("/inventory/crafting-history?action=upgrade")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["action"] == "upgrade"


def test_action_craft_returns_only_crafts(client, db):
    _insert_log(db, "upgrade")
    _insert_log(db, "craft")
    r = client.get("/inventory/crafting-history?action=craft")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["action"] == "craft"


def test_invalid_action_returns_422(client, db):
    r = client.get("/inventory/crafting-history?action=fuse")
    assert r.status_code == 422


def test_empty_result_when_filtered_type_absent(client, db):
    _insert_log(db, "upgrade")
    r = client.get("/inventory/crafting-history?action=craft")
    assert r.status_code == 200
    assert r.json() == []


def test_limit_still_works_with_filter(client, db):
    for _ in range(5):
        _insert_log(db, "upgrade")
    r = client.get("/inventory/crafting-history?action=upgrade&limit=3")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_newest_first_ordering_with_filter(client, db):
    _insert_log(db, "craft", result_item_id="first")
    _insert_log(db, "craft", result_item_id="second")
    rows = client.get("/inventory/crafting-history?action=craft").json()
    assert rows[0]["result_item_id"] == "second"
    assert rows[1]["result_item_id"] == "first"
