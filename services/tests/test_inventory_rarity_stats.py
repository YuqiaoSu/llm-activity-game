"""Tests for GET /inventory/rarity-stats."""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
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


def _add_item(db, item_id: str, rarity: str = "COMMON", expires_at: str | None = None) -> str:
    data = json.dumps({"name": item_id, "rarity": rarity, "category": "WORK"})
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data))
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, expires_at)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'test', ?)",
        (iid, item_id, expires_at),
    )
    db.commit()
    return iid


def test_empty_returns_empty_list(client, db):
    r = client.get("/inventory/rarity-stats")
    assert r.status_code == 200
    assert r.json() == []


def test_counts_correct(client, db):
    _add_item(db, "c1", "COMMON")
    _add_item(db, "c2", "COMMON")
    _add_item(db, "r1", "RARE")
    r = client.get("/inventory/rarity-stats")
    by_rarity = {row["rarity"]: row for row in r.json()}
    assert by_rarity["COMMON"]["count"] == 2
    assert by_rarity["RARE"]["count"] == 1


def test_pct_sums_to_100(client, db):
    _add_item(db, "c1", "COMMON")
    _add_item(db, "u1", "UNCOMMON")
    _add_item(db, "r1", "RARE")
    rows = client.get("/inventory/rarity-stats").json()
    total_pct = sum(row["pct"] for row in rows)
    assert abs(total_pct - 100.0) < 0.2


def test_expired_items_excluded(client, db):
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    _add_item(db, "expired", "EPIC", expires_at=past)
    r = client.get("/inventory/rarity-stats")
    by_rarity = {row["rarity"]: row for row in r.json()}
    assert "EPIC" not in by_rarity


def test_multiple_rarities_present(client, db):
    _add_item(db, "c1", "COMMON")
    _add_item(db, "l1", "LEGENDARY")
    rows = client.get("/inventory/rarity-stats").json()
    rarities = [r["rarity"] for r in rows]
    assert "COMMON" in rarities
    assert "LEGENDARY" in rarities


def test_correct_shape(client, db):
    _add_item(db, "c1", "COMMON")
    rows = client.get("/inventory/rarity-stats").json()
    assert len(rows) == 1
    row = rows[0]
    assert "rarity" in row
    assert "count" in row
    assert "pct" in row
