"""Tests for item selling — GET sell-value + POST sell."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db, bootstrap_defaults
from services.progression.xp import get_total_xp
from services.api.main import app

_SELL_XP = {"COMMON": 5, "UNCOMMON": 15, "RARE": 30, "EPIC": 60, "LEGENDARY": 100}


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


def _add_item_def(db, item_id: str, rarity: str = "COMMON") -> None:
    data = json.dumps({
        "item_id": item_id, "name": item_id, "rarity": rarity,
        "category": "WORK", "description": "", "effects": [],
    })
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data)
    )
    db.commit()


def _add_instance(db, item_id: str = "itm", placed_in: str | None = None) -> str:
    iid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk, placed_in)"
        " VALUES (?, 'player_default', ?, ?, 'test', ?)",
        (iid, item_id, datetime.now(timezone.utc).isoformat(), placed_in),
    )
    db.commit()
    return iid


# ── sell-value endpoint ───────────────────────────────────────────────────────

def test_sell_value_returns_xp_for_rarity(client, db):
    _add_item_def(db, "rare_itm", "RARE")
    iid = _add_instance(db, "rare_itm")
    resp = client.get(f"/inventory/instances/{iid}/sell-value")
    assert resp.status_code == 200
    data = resp.json()
    assert data["xp_value"] == 30
    assert data["rarity"] == "RARE"


def test_sell_value_404_unknown(client):
    resp = client.get(f"/inventory/instances/{uuid.uuid4()}/sell-value")
    assert resp.status_code == 404


# ── sell endpoint ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rarity,expected_xp", list(_SELL_XP.items()))
def test_sell_awards_correct_xp_by_rarity(client, db, rarity, expected_xp):
    item_id = f"item_{rarity.lower()}"
    _add_item_def(db, item_id, rarity)
    iid = _add_instance(db, item_id)
    before = get_total_xp(db, "player_default")
    resp = client.post(f"/inventory/instances/{iid}/sell")
    assert resp.status_code == 200
    assert resp.json()["xp_awarded"] == expected_xp
    after = get_total_xp(db, "player_default")
    assert after - before == expected_xp


def test_sell_removes_instance_from_inventory(client, db):
    _add_item_def(db, "sellable")
    iid = _add_instance(db, "sellable")
    client.post(f"/inventory/instances/{iid}/sell")
    row = db.execute("SELECT 1 FROM inventory WHERE instance_id=?", (iid,)).fetchone()
    assert row is None


def test_sell_404_unknown_instance(client):
    resp = client.post(f"/inventory/instances/{uuid.uuid4()}/sell")
    assert resp.status_code == 404


def test_sell_409_placed_item(client, db):
    _add_item_def(db, "placed_itm")
    iid = _add_instance(db, "placed_itm", placed_in="some_slot")
    resp = client.post(f"/inventory/instances/{iid}/sell")
    assert resp.status_code == 409


def test_sell_fires_item_sold_notification(client, db):
    _add_item_def(db, "notif_itm", "EPIC")
    iid = _add_instance(db, "notif_itm")
    client.post(f"/inventory/instances/{iid}/sell")
    row = db.execute(
        "SELECT payload FROM pending_notifications WHERE event_type='item_sold'"
        " AND json_extract(payload, '$.instance_id') = ?",
        (iid,),
    ).fetchone()
    assert row is not None
    payload = json.loads(row["payload"])
    assert payload["xp_awarded"] == 60
    assert payload["rarity"] == "EPIC"
