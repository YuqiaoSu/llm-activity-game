"""Tests for inventory instance favoriting."""
import sqlite3
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db, bootstrap_defaults
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


def _add_item_def(db, item_id: str = "fav_item") -> None:
    import json
    data = json.dumps({
        "item_id": item_id, "name": "Fav Item", "rarity": "COMMON",
        "category": "WORK", "description": "", "effects": [],
    })
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)", (item_id, data)
    )
    db.commit()


def _add_instance(db, item_id: str = "fav_item") -> str:
    instance_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, ?, 'test')",
        (instance_id, item_id, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    return instance_id


def test_favorite_sets_flag(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    resp = client.patch(f"/inventory/instances/{iid}/favorite", json={"favorite": True})
    assert resp.status_code == 200
    assert resp.json()["favorite"] is True


def test_favorite_persists_in_db(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    client.patch(f"/inventory/instances/{iid}/favorite", json={"favorite": True})
    row = db.execute("SELECT favorite FROM inventory WHERE instance_id=?", (iid,)).fetchone()
    assert row["favorite"] == 1


def test_unfavorite_clears_flag(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    client.patch(f"/inventory/instances/{iid}/favorite", json={"favorite": True})
    client.patch(f"/inventory/instances/{iid}/favorite", json={"favorite": False})
    row = db.execute("SELECT favorite FROM inventory WHERE instance_id=?", (iid,)).fetchone()
    assert row["favorite"] == 0


def test_favorite_unknown_instance_returns_404(client):
    resp = client.patch(
        f"/inventory/instances/{uuid.uuid4()}/favorite", json={"favorite": True}
    )
    assert resp.status_code == 404


def test_get_inventory_includes_favorite_field(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    client.patch(f"/inventory/instances/{iid}/favorite", json={"favorite": True})
    items = client.get("/inventory").json()
    match = next((i for i in items if i["item_id"] == "fav_item"), None)
    assert match is not None
    assert match.get("favorite") in (1, True)


def test_get_inventory_favorite_zero_when_not_set(client, db):
    _add_item_def(db)
    _add_instance(db)
    items = client.get("/inventory").json()
    match = next((i for i in items if i["item_id"] == "fav_item"), None)
    assert match is not None
    assert match.get("favorite") in (0, False, None)
