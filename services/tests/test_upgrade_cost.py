"""Tests for GET /inventory/upgrade-cost."""
import json
import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient

from services.storage.db import init_db

_VISUAL = json.dumps({"base_sprite": "x.png", "evolution_stage": 0,
                      "skin": None, "accessories": [], "anim_state": "idle"})


def _item_data(item_id: str, rarity: str, category: str = "WORK") -> str:
    return json.dumps({
        "item_id": item_id, "name": item_id, "rarity": rarity,
        "category": category, "description": "", "effects": [],
        "icon": "", "stackable": False, "set_id": None,
        "drop_requirement": {"activity_label": None, "min_duration_sec": 0,
                             "min_confidence": 0.0, "time_of_day": None},
    })


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


def _add_common(db, item_id: str, category: str = "WORK", n: int = 1):
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES (?, ?)",
               (item_id, _item_data(item_id, "COMMON", category)))
    for _ in range(n):
        db.execute(
            "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
            " VALUES (?, 'player_default', ?, '2025-01-01T00:00:00', 'test')",
            (str(uuid.uuid4()), item_id),
        )
    db.commit()


def test_unknown_rarity_422(client):
    r = client.get("/inventory/upgrade-cost?target_rarity=MYSTICAL&category=WORK")
    assert r.status_code == 422


def test_common_returns_zero(client):
    r = client.get("/inventory/upgrade-cost?target_rarity=COMMON&category=WORK")
    assert r.status_code == 200
    body = r.json()
    assert body["items_needed"] == 0
    assert body["shortfall"] == 0
    assert body["xp_equivalent"] == 0


def test_uncommon_needs_two(client):
    body = client.get("/inventory/upgrade-cost?target_rarity=UNCOMMON&category=WORK").json()
    assert body["items_needed"] == 2


def test_epic_needs_eight(client):
    body = client.get("/inventory/upgrade-cost?target_rarity=EPIC&category=WORK").json()
    assert body["items_needed"] == 8


def test_legendary_needs_sixteen(client):
    body = client.get("/inventory/upgrade-cost?target_rarity=LEGENDARY&category=WORK").json()
    assert body["items_needed"] == 16


def test_owned_reduces_shortfall(client, db):
    _add_common(db, "c1", "WORK", n=3)
    body = client.get("/inventory/upgrade-cost?target_rarity=EPIC&category=WORK").json()
    # needs 8, owns 3 → shortfall 5
    assert body["items_owned"] == 3
    assert body["shortfall"] == 5


def test_fully_covered_shortfall_zero(client, db):
    _add_common(db, "c1", "WORK", n=16)
    body = client.get("/inventory/upgrade-cost?target_rarity=LEGENDARY&category=WORK").json()
    assert body["shortfall"] == 0
    assert body["xp_equivalent"] == 0


def test_xp_equivalent_uses_common_sell_value(client):
    # UNCOMMON needs 2, 0 owned → shortfall 2, xp = 2 × 5 = 10
    body = client.get("/inventory/upgrade-cost?target_rarity=UNCOMMON&category=WORK").json()
    assert body["xp_equivalent"] == 10


def test_response_shape(client):
    body = client.get("/inventory/upgrade-cost?target_rarity=RARE&category=LEARN").json()
    for key in ("target_rarity", "category", "items_needed", "items_owned",
                "shortfall", "xp_equivalent"):
        assert key in body
