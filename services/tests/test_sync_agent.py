import sqlite3
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from services.storage.db import init_db
from services.models.enums import Category, Rarity, PlaceState
from services.models.item import ItemDefinition, DropRequirement
from services.models.place import Place, PlaceItemPool, Condition
from services.place_service.service import save_place
from services.sync_agent.rate_limiter import RateLimiter
from services.sync_agent.agent import SyncAgent, PollResult
from services.sync_agent.tracker_client import TrackerClient
from services.drop_engine.strategies import SessionStrategy


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Seed one item definition
    item = ItemDefinition(
        item_id="work_common_001", name="Work Scroll",
        category=Category.WORK, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(min_confidence=0.5),
        icon="scroll.png", description="",
    )
    conn.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item.item_id, item.model_dump_json()),
    )
    # Seed default player profile
    visual = json.dumps({"base_sprite": "lumi.png", "evolution_stage": 0,
                         "skin": None, "accessories": [], "anim_state": "idle"})
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, ?, ?)",
        ("player_default", "Lumi", visual),
    )
    # Seed sync_state row
    conn.execute("INSERT OR IGNORE INTO sync_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


def test_rate_limiter_allows_first_call():
    rl = RateLimiter(cooldown_sec=60)
    assert rl.can_trigger("p1") is True


def test_rate_limiter_blocks_within_cooldown():
    rl = RateLimiter(cooldown_sec=60)
    rl.record_trigger("p1")
    assert rl.can_trigger("p1") is False


def test_rate_limiter_allows_after_cooldown():
    rl = RateLimiter(cooldown_sec=60)
    past = datetime.now(timezone.utc) - timedelta(seconds=61)
    rl._last_trigger["p1"] = past
    assert rl.can_trigger("p1") is True


def test_sync_agent_poll_processes_chunks(db):
    chunks = [
        {
            "chunk_id": "c_001", "label": "WORK", "duration_sec": 1800,
            "confidence": 0.92, "started_at": "2026-04-14T09:00:00+00:00",
            "time_of_day": "morning",
        }
    ]
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "c_001")

    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    result = agent.poll()
    assert result == PollResult.OK

    # SessionStrategy gives 1 roll; WORK item matches WORK chunk → always 1 drop
    ledger = db.execute("SELECT * FROM reward_ledger").fetchall()
    assert len(ledger) == 1
    assert ledger[0]["item_id"] == "work_common_001"


def test_sync_agent_poll_on_cooldown_returns_cooldown(db):
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = ([], None)
    rl = RateLimiter(cooldown_sec=3600)
    rl.record_trigger("player_default")

    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
        rate_limiter=rl,
    )
    result = agent.poll(manual=True)
    assert result == PollResult.ON_COOLDOWN


def test_sync_agent_poll_advances_cursor(db):
    chunks = [
        {
            "chunk_id": "c_001", "label": "GAME", "duration_sec": 3600,
            "confidence": 0.88, "started_at": "2026-04-14T20:00:00+00:00",
        }
    ]
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "c_001")

    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    agent.poll()
    cursor = db.execute(
        "SELECT last_cursor FROM sync_state WHERE player_id='default'"
    ).fetchone()["last_cursor"]
    assert cursor == "c_001"


def test_sync_agent_poll_no_chunks_returns_no_new_chunks(db):
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = ([], None)
    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    result = agent.poll()
    assert result == PollResult.NO_NEW_CHUNKS


def test_sync_agent_skips_low_confidence_chunk(db):
    chunks = [
        {
            "chunk_id": "c_low", "label": "WORK", "duration_sec": 1800,
            "confidence": 0.1, "started_at": "2026-04-14T09:00:00+00:00",
        }
    ]
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "c_low")
    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
        min_confidence=0.5,
    )
    agent.poll()
    ledger = db.execute("SELECT * FROM reward_ledger").fetchall()
    assert len(ledger) == 0


def test_sync_agent_poll_handles_unknown_label(db):
    """poll() must return OK and not raise when chunk label is unrecognized."""
    chunks = [{
        "chunk_id": "c_bogus", "label": "BOGUS_ACTIVITY",
        "duration_sec": 900, "confidence": 0.8,
        "started_at": "2026-04-14T10:00:00+00:00",
    }]
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "c_bogus")
    agent = SyncAgent(db=db, tracker_client=mock_client, character_id="player_default")
    result = agent.poll()
    assert result == PollResult.OK   # must not raise
    # No XP should be awarded for an unknown label
    rows = db.execute("SELECT * FROM player_category_xp WHERE character_id='player_default'").fetchall()
    assert len(rows) == 0


def test_sync_agent_level_up_notification_emitted(db):
    """A LEVEL_UP notification is created when XP crosses a level threshold.

    Level 2 requires 100 XP (XP_PER_LEVEL[1]=100). A 120-min WORK chunk
    awards 120 XP → crosses level 2 → one LEVEL_UP notification.
    """
    chunks = [{
        "chunk_id": "c_levelup", "label": "WORK", "duration_sec": 7200,  # 120 min → 120 XP
        "confidence": 0.9, "started_at": "2026-04-14T09:00:00+00:00",
        "time_of_day": "morning",
    }]
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "c_levelup")
    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    agent.poll()

    notifications = db.execute(
        "SELECT * FROM pending_notifications WHERE character_id='player_default' AND event_type='level_up'"
    ).fetchall()
    assert len(notifications) == 1
    import json
    payload = json.loads(notifications[0]["payload"])
    assert payload["new_level"] == 2


def test_sync_agent_multiple_level_ups_in_one_poll(db):
    """Each level crossed gets its own notification when multiple levels are gained at once."""
    # Level 2 = 100 XP, Level 3 = 250 XP. A 260-min chunk awards 260 XP → crosses 2 and 3.
    chunks = [{
        "chunk_id": "c_multi", "label": "WORK", "duration_sec": 15600,  # 260 min → 260 XP
        "confidence": 0.9, "started_at": "2026-04-14T09:00:00+00:00",
        "time_of_day": "morning",
    }]
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "c_multi")
    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    agent.poll()

    notifications = db.execute(
        "SELECT payload FROM pending_notifications "
        "WHERE character_id='player_default' AND event_type='level_up' "
        "ORDER BY created_at ASC"
    ).fetchall()
    import json
    levels = [json.loads(n["payload"])["new_level"] for n in notifications]
    assert levels == [2, 3]


def test_sync_agent_place_unlock_triggered_on_level_up(db):
    """A LOCKED place with a player_level condition unlocks when level is reached."""
    # Seed a locked place requiring level 2
    locked_place = Place(
        place_id="cave_001", name="Crystal Cave", place_type="dungeon",
        state=PlaceState.LOCKED,
        unlock_condition=Condition(condition_type="player_level", params={"min_level": 2}),
        item_pool=PlaceItemPool(),
    )
    save_place(db, locked_place)

    # 120 XP chunk → level 2 → should unlock cave_001
    chunks = [{
        "chunk_id": "c_unlock", "label": "WORK", "duration_sec": 7200,
        "confidence": 0.9, "started_at": "2026-04-14T09:00:00+00:00",
        "time_of_day": "morning",
    }]
    mock_client = MagicMock(spec=TrackerClient)
    mock_client.fetch_chunks.return_value = (chunks, "c_unlock")
    agent = SyncAgent(
        db=db,
        tracker_client=mock_client,
        character_id="player_default",
        strategy=SessionStrategy(),
    )
    agent.poll()

    # Place should now be UNLOCKED
    row = db.execute("SELECT state FROM places WHERE place_id='cave_001'").fetchone()
    assert row["state"] == "UNLOCKED"

    # A place_unlock notification should exist
    notif = db.execute(
        "SELECT payload FROM pending_notifications "
        "WHERE character_id='player_default' AND event_type='place_unlock'"
    ).fetchone()
    assert notif is not None
    assert json.loads(notif["payload"])["place_id"] == "cave_001"
