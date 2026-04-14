import sqlite3
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from services.storage.db import init_db
from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition, DropRequirement
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
