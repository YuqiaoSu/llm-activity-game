"""Tests for inventory instance notes."""
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


def _add_item_def(db, item_id: str = "test_item") -> None:
    import json
    data = json.dumps({
        "item_id": item_id, "name": "Test Item", "rarity": "COMMON",
        "category": "WORK", "description": "", "effects": [],
    })
    db.execute(
        "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item_id, data),
    )
    db.commit()


def _add_instance(db, item_id: str = "test_item") -> str:
    instance_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
        " VALUES (?, 'player_default', ?, ?, 'test')",
        (instance_id, item_id, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    return instance_id


# ── PATCH endpoint ────────────────────────────────────────────────────────────

def test_patch_note_sets_note(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    resp = client.patch(f"/inventory/instances/{iid}/note", json={"note": "my note"})
    assert resp.status_code == 200
    assert resp.json()["note"] == "my note"
    assert resp.json()["instance_id"] == iid


def test_patch_note_persists_in_db(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    client.patch(f"/inventory/instances/{iid}/note", json={"note": "persisted"})
    row = db.execute("SELECT note FROM inventory WHERE instance_id=?", (iid,)).fetchone()
    assert row["note"] == "persisted"


def test_patch_note_clear_sets_null(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    client.patch(f"/inventory/instances/{iid}/note", json={"note": "first"})
    client.patch(f"/inventory/instances/{iid}/note", json={"note": ""})
    row = db.execute("SELECT note FROM inventory WHERE instance_id=?", (iid,)).fetchone()
    assert row["note"] is None


def test_patch_note_unknown_instance_returns_404(client, db):
    resp = client.patch(
        f"/inventory/instances/{uuid.uuid4()}/note", json={"note": "hi"}
    )
    assert resp.status_code == 404


def test_patch_note_too_long_returns_422(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    resp = client.patch(
        f"/inventory/instances/{iid}/note", json={"note": "x" * 51}
    )
    assert resp.status_code == 422


def test_patch_note_exactly_50_chars_allowed(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    resp = client.patch(
        f"/inventory/instances/{iid}/note", json={"note": "a" * 50}
    )
    assert resp.status_code == 200


# ── GET /inventory surfaces note ──────────────────────────────────────────────

def test_get_inventory_includes_note_field(client, db):
    _add_item_def(db)
    iid = _add_instance(db)
    client.patch(f"/inventory/instances/{iid}/note", json={"note": "visible"})
    items = client.get("/inventory").json()
    match = next((i for i in items if i["item_id"] == "test_item"), None)
    assert match is not None
    assert match.get("note") == "visible"


def test_get_inventory_note_null_when_not_set(client, db):
    _add_item_def(db)
    _add_instance(db)
    items = client.get("/inventory").json()
    match = next((i for i in items if i["item_id"] == "test_item"), None)
    assert match is not None
    assert match.get("note") is None
