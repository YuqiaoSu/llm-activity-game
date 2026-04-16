"""Tests for GET /collection and collection_log population via record_drop."""
import json
import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES ('player_default', 'T', ?)",
        (visual,),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    # Seed two item definitions
    for item_id, name, rarity, cat in [
        ("sword_common", "Rusty Sword", "COMMON", "WORK"),
        ("gem_rare", "Rare Gem", "RARE", "EXPLORE"),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
            (item_id, json.dumps({
                "item_id": item_id, "name": name, "rarity": rarity,
                "category": cat, "icon": "placeholder.png", "effects": [],
                "drop_requirement": {}, "description": "", "stackable": False,
            })),
        )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    from services.api.main import create_app
    return TestClient(create_app(db=db))


def _insert_collection(db, item_id: str, player_id: str = "player_default") -> None:
    db.execute(
        "INSERT OR IGNORE INTO collection_log (player_id, item_id, first_seen_at) "
        "VALUES (?, ?, '2026-04-16T00:00:00+00:00')",
        (player_id, item_id),
    )
    db.commit()


# ── endpoint shape ────────────────────────────────────────────────────────────

def test_collection_empty_returns_all_items_undiscovered(client):
    r = client.get("/collection")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(not item["discovered"] for item in data)
    assert all(item["first_seen_at"] is None for item in data)


def test_collection_entry_has_required_keys(client):
    entry = client.get("/collection").json()[0]
    assert set(entry.keys()) == {"item_id", "name", "rarity", "category",
                                 "icon", "discovered", "first_seen_at"}


def test_collection_discovered_item_shows_true(client, db):
    _insert_collection(db, "sword_common")
    data = client.get("/collection").json()
    by_id = {e["item_id"]: e for e in data}
    assert by_id["sword_common"]["discovered"] is True
    assert by_id["gem_rare"]["discovered"] is False


def test_collection_first_seen_at_populated(client, db):
    _insert_collection(db, "sword_common")
    by_id = {e["item_id"]: e for e in client.get("/collection").json()}
    assert by_id["sword_common"]["first_seen_at"] is not None
    assert by_id["gem_rare"]["first_seen_at"] is None


def test_collection_discovered_items_listed_first(client, db):
    _insert_collection(db, "gem_rare")
    data = client.get("/collection").json()
    # discovered=True items come first
    assert data[0]["discovered"] is True
    assert data[1]["discovered"] is False


# ── record_drop stamps collection_log ─────────────────────────────────────────

def test_record_drop_stamps_collection_log(db):
    from services.reward_ledger.ledger import record_drop
    from services.models.item import ItemDefinition
    item = ItemDefinition.model_validate_json(
        db.execute(
            "SELECT data FROM item_definitions WHERE item_id='sword_common'"
        ).fetchone()["data"]
    )
    record_drop(db, chunk_id=str(uuid.uuid4()), roll_n=0, item=item, character_id="player_default")
    row = db.execute(
        "SELECT * FROM collection_log WHERE player_id='player_default' AND item_id='sword_common'"
    ).fetchone()
    assert row is not None
    assert row["first_seen_at"] is not None


def test_record_drop_does_not_overwrite_first_seen_at(db):
    """Second drop of the same item must not update first_seen_at."""
    from services.reward_ledger.ledger import record_drop
    from services.models.item import ItemDefinition
    item = ItemDefinition.model_validate_json(
        db.execute(
            "SELECT data FROM item_definitions WHERE item_id='sword_common'"
        ).fetchone()["data"]
    )
    record_drop(db, chunk_id=str(uuid.uuid4()), roll_n=0, item=item, character_id="player_default")
    first = db.execute(
        "SELECT first_seen_at FROM collection_log WHERE item_id='sword_common'"
    ).fetchone()["first_seen_at"]

    record_drop(db, chunk_id=str(uuid.uuid4()), roll_n=0, item=item, character_id="player_default")
    second = db.execute(
        "SELECT first_seen_at FROM collection_log WHERE item_id='sword_common'"
    ).fetchone()["first_seen_at"]
    assert first == second


def test_collection_count_after_two_drops(db):
    from services.reward_ledger.ledger import record_drop
    from services.models.item import ItemDefinition
    for item_id in ["sword_common", "gem_rare"]:
        item = ItemDefinition.model_validate_json(
            db.execute(
                "SELECT data FROM item_definitions WHERE item_id=?", (item_id,)
            ).fetchone()["data"]
        )
        record_drop(db, chunk_id=str(uuid.uuid4()), roll_n=0, item=item, character_id="player_default")

    count = db.execute("SELECT COUNT(*) FROM collection_log").fetchone()[0]
    assert count == 2
