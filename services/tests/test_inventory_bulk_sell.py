"""Tests for POST /inventory/bulk-sell."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db, bootstrap_defaults
from services.progression.xp import get_total_xp
from services.api.main import app


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    bootstrap_defaults(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app.state.db = db
    return TestClient(app)


def _add_item_def(db, item_id: str, rarity: str = "COMMON", category: str = "WORK") -> None:
    data = json.dumps({
        "item_id": item_id, "name": item_id, "rarity": rarity,
        "category": category, "description": "", "effects": [],
    })
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data)
    )
    db.commit()


def _add_instance(
    db,
    item_id: str,
    placed_in: str | None = None,
    expires_at: str | None = None,
) -> str:
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, placed_in, expires_at)"
        " VALUES (?, 'player_default', ?, datetime('now'), 'test', ?, ?)",
        (iid, item_id, placed_in, expires_at),
    )
    db.commit()
    return iid


# ── basic bulk sell ────────────────────────────────────────────────────────────

def test_bulk_sell_returns_correct_count_and_xp(client, db):
    _add_item_def(db, "c1", "COMMON")
    _add_item_def(db, "c2", "COMMON")
    _add_instance(db, "c1")
    _add_instance(db, "c2")
    resp = client.post("/inventory/bulk-sell", json={"rarity": "COMMON"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sold_count"] == 2
    assert data["total_xp_earned"] == 10   # 2 × 5 XP


def test_bulk_sell_awards_xp(client, db):
    _add_item_def(db, "r1", "RARE")
    _add_instance(db, "r1")
    _add_instance(db, "r1")
    before = get_total_xp(db, "player_default")
    client.post("/inventory/bulk-sell", json={"rarity": "RARE"})
    after = get_total_xp(db, "player_default")
    assert after - before == 60   # 2 × 30 XP


def test_bulk_sell_removes_inventory_rows(client, db):
    _add_item_def(db, "u1", "UNCOMMON")
    _add_instance(db, "u1")
    _add_instance(db, "u1")
    client.post("/inventory/bulk-sell", json={"rarity": "UNCOMMON"})
    remaining = db.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE item_id='u1'"
    ).fetchone()["n"]
    assert remaining == 0


def test_bulk_sell_skips_placed_items(client, db):
    _add_item_def(db, "p1", "COMMON")
    _add_instance(db, "p1", placed_in="slot_1")
    _add_instance(db, "p1")
    resp = client.post("/inventory/bulk-sell", json={"rarity": "COMMON"})
    data = resp.json()
    assert data["sold_count"] == 1   # only the unplaced one sold
    placed = db.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE item_id='p1'"
    ).fetchone()["n"]
    assert placed == 1   # placed item remains


def test_bulk_sell_skips_expired_items(client, db):
    _add_item_def(db, "e1", "COMMON")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _add_instance(db, "e1", expires_at=past)
    _add_instance(db, "e1")
    resp = client.post("/inventory/bulk-sell", json={"rarity": "COMMON"})
    data = resp.json()
    assert data["sold_count"] == 1   # expired one not sold


def test_bulk_sell_category_filter(client, db):
    _add_item_def(db, "work_c", "COMMON", "WORK")
    _add_item_def(db, "learn_c", "COMMON", "LEARN")
    _add_instance(db, "work_c")
    _add_instance(db, "learn_c")
    resp = client.post("/inventory/bulk-sell", json={"rarity": "COMMON", "category": "WORK"})
    data = resp.json()
    assert data["sold_count"] == 1
    assert data["total_xp_earned"] == 5


def test_bulk_sell_bad_rarity_returns_400(client, db):
    resp = client.post("/inventory/bulk-sell", json={"rarity": "MYTHIC"})
    assert resp.status_code == 400


def test_bulk_sell_empty_pool_returns_zero(client, db):
    resp = client.post("/inventory/bulk-sell", json={"rarity": "LEGENDARY"})
    data = resp.json()
    assert data["sold_count"] == 0
    assert data["total_xp_earned"] == 0


def test_bulk_sell_fires_notification(client, db):
    _add_item_def(db, "epic_i", "EPIC")
    _add_instance(db, "epic_i")
    client.post("/inventory/bulk-sell", json={"rarity": "EPIC"})
    note = db.execute(
        "SELECT payload FROM pending_notifications WHERE event_type='bulk_item_sold'"
    ).fetchone()
    assert note is not None
    import json as _json
    payload = _json.loads(note["payload"])
    assert payload["rarity"] == "EPIC"
    assert payload["sold_count"] == 1
    assert payload["total_xp_earned"] == 60
