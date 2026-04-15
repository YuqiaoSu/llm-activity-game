import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from services.storage.db import init_db
from services.models.enums import Category, Rarity, PlaceState, SlotType
from services.models.item import ItemDefinition, DropRequirement
from services.models.place import Place, PlaceItemPool, PlaceSlot
from services.place_service.service import save_place


@pytest.fixture
def seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    visual = json.dumps({"base_sprite": "lumi.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Lumi", visual),
    )
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, ?, ?)",
        ("player_default", "WORK", 300),
    )
    item = ItemDefinition(
        item_id="scroll_001", name="Scroll", category=Category.WORK,
        rarity=Rarity.COMMON, drop_requirement=DropRequirement(),
        icon="s.png", description="",
    )
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item.item_id, item.model_dump_json()),
    )
    conn.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES ('inv_001', 'player_default', 'scroll_001', '2026-04-14T00:00:00+00:00', 'c1')"
    )
    home = Place(
        place_id="home_001", name="Home", place_type="home",
        state=PlaceState.UNLOCKED,
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
        slots=[PlaceSlot(slot_id="s1", place_id="home_001", slot_type=SlotType.ITEM)],
    )
    save_place(conn, home)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def client(seeded_db):
    from services.api.main import create_app
    app = create_app(db=seeded_db)
    return TestClient(app)


def test_get_sync_status(client):
    r = client.get("/sync/status")
    assert r.status_code == 200
    data = r.json()
    assert "last_cursor" in data
    assert "last_sync_at" in data


def test_get_player_profile(client):
    r = client.get("/player/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["character_id"] == "player_default"
    assert data["total_xp"] == 300
    assert data["level"] >= 1
    assert "category_xp" in data
    assert "WORK" in data["category_xp"]


def test_player_profile_all_categories_present(client):
    """category_xp always contains every Category value, even those with 0 XP."""
    from services.models.enums import Category
    r = client.get("/player/profile")
    assert r.status_code == 200
    cat_xp = r.json()["category_xp"]
    for cat in Category:
        assert cat.value in cat_xp, f"{cat.value} missing from category_xp"
    # Fixture only seeds WORK; all others should default to 0
    for cat in Category:
        if cat != Category.WORK:
            assert cat_xp[cat.value] == 0, f"{cat.value} should be 0, got {cat_xp[cat.value]}"


def test_get_inventory(client):
    r = client.get("/inventory")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert item["item_id"] == "scroll_001"
    assert item["quantity"] == 1             # one instance in fixture
    assert item["name"] == "Scroll"          # enriched from item_definitions JSON
    assert item["rarity"] == "COMMON"        # enriched from item_definitions JSON
    assert item["category"] == "WORK"        # enriched from item_definitions JSON
    assert "instance_id" not in item         # grouped response, no per-instance id


def test_equip_item(client, seeded_db):
    r = client.patch("/inventory/scroll_001/equip", json={"equipped": True})
    assert r.status_code == 200
    data = r.json()
    assert data["item_id"] == "scroll_001"
    assert data["equipped"] is True
    row = seeded_db.execute(
        "SELECT equipped FROM inventory WHERE item_id='scroll_001'"
    ).fetchone()
    assert row["equipped"] == 1


def test_equip_item_idempotent(client, seeded_db):
    client.patch("/inventory/scroll_001/equip", json={"equipped": True})
    r = client.patch("/inventory/scroll_001/equip", json={"equipped": True})
    assert r.status_code == 200


def test_unequip_item(client, seeded_db):
    seeded_db.execute("UPDATE inventory SET equipped=1 WHERE item_id='scroll_001'")
    seeded_db.commit()
    r = client.patch("/inventory/scroll_001/equip", json={"equipped": False})
    assert r.status_code == 200
    assert r.json()["equipped"] is False


def test_equip_item_not_found(client):
    r = client.patch("/inventory/nonexistent_item/equip", json={"equipped": True})
    assert r.status_code == 404


def test_get_places(client):
    r = client.get("/places")
    assert r.status_code == 200
    places = r.json()
    assert len(places) == 1
    assert places[0]["place_id"] == "home_001"


def test_get_place_by_id(client):
    r = client.get("/places/home_001")
    assert r.status_code == 200
    assert r.json()["name"] == "Home"


def test_get_place_not_found(client):
    r = client.get("/places/nonexistent")
    assert r.status_code == 404


def test_get_pending_notifications_empty(client):
    r = client.get("/notifications/pending")
    assert r.status_code == 200
    assert r.json() == []


def test_ack_notification(client, seeded_db):
    import uuid
    nid = str(uuid.uuid4())
    seeded_db.execute(
        "INSERT INTO pending_notifications "
        "(notification_id, character_id, event_type, payload, created_at) "
        "VALUES (?, 'player_default', 'item_drop', '{}', '2026-04-14T00:00:00+00:00')",
        (nid,),
    )
    seeded_db.commit()
    r = client.post(f"/notifications/{nid}/ack")
    assert r.status_code == 200
    row = seeded_db.execute(
        "SELECT acknowledged FROM pending_notifications WHERE notification_id=?", (nid,)
    ).fetchone()
    assert row["acknowledged"] == 1


def test_ack_nonexistent_notification(client):
    r = client.post("/notifications/does-not-exist/ack")
    assert r.status_code == 404


def test_get_stats(client):
    r = client.get("/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_xp" in data
    assert "level" in data
    assert "evolution_stage" in data
    assert "category_xp" in data
    assert "top_category" in data
    assert "chunks_processed" in data
    assert "drops_total" in data
    assert "places_unlocked" in data
    # Fixture seeds WORK XP — top_category must be WORK (only non-zero category)
    assert data["top_category"] == "WORK"
    # The fixture seeds one place in UNLOCKED state
    assert data["places_unlocked"] == 1
    # No drops were recorded in the fixture
    assert data["drops_total"] == 0
    assert data["chunks_processed"] == 0


def test_get_history_empty(client):
    r = client.get("/history")
    assert r.status_code == 200
    assert r.json() == []


def test_get_history_after_poll(client, seeded_db, monkeypatch):
    """After a poll that processes a chunk, /history returns that chunk's log entry."""
    from services.sync_agent import tracker_client as tc_module
    chunks = [{
        "chunk_id": "hist_001", "label": "WORK", "duration_sec": 1800,
        "confidence": 0.9, "started_at": "2026-04-14T09:00:00+00:00",
        "time_of_day": "morning",
    }]
    monkeypatch.setattr(
        tc_module.TrackerClient,
        "fetch_chunks",
        lambda self, after_cursor, limit=50: (chunks, "hist_001"),
    )
    client.post("/sync/poll-now")

    r = client.get("/history")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["chunk_id"] == "hist_001"
    assert entry["category"] == "WORK"
    assert entry["xp_awarded"] == 30   # 1800 sec / 60 = 30 min × 1 XP/min
    assert entry["duration_sec"] == 1800
    assert "processed_at" in entry
    assert "drops" in entry


def test_poll_now_no_new_chunks(client, monkeypatch):
    from services.sync_agent import tracker_client as tc_module
    monkeypatch.setattr(
        tc_module.TrackerClient,
        "fetch_chunks",
        lambda self, after_cursor, limit=50: ([], None),
    )
    r = client.post("/sync/poll-now")
    assert r.status_code == 200
    assert "result" in r.json()
