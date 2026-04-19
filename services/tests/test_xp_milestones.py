"""Tests for XP milestone rewards."""
import json
import sqlite3
import uuid
import pytest

from services.storage.db import init_db, bootstrap_defaults
from services.progression.xp import award_category_xp
from services.progression.xp_milestones import check_xp_milestones, XP_MILESTONES
from services.models.enums import Category


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    bootstrap_defaults(conn)
    yield conn
    conn.close()


def _count_milestone_notifs(db, milestone: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS n FROM pending_notifications"
        " WHERE event_type='xp_milestone' AND json_extract(payload, '$.milestone') = ?",
        (milestone,),
    ).fetchone()
    return row["n"]


def _give_xp(db, xp: int) -> tuple[int, int]:
    from services.progression.xp import get_total_xp
    before = get_total_xp(db, "player_default")
    award_category_xp(db, "player_default", Category.WORK, xp)
    after = get_total_xp(db, "player_default")
    return before, after


# ── Basic milestone crossing ──────────────────────────────────────────────────

def test_milestone_fires_when_threshold_crossed(db):
    before, after = _give_xp(db, 500)
    check_xp_milestones(db, "player_default", before, after)
    assert _count_milestone_notifs(db, 500) == 1


def test_milestone_notification_payload(db):
    before, after = _give_xp(db, 500)
    check_xp_milestones(db, "player_default", before, after)
    row = db.execute(
        "SELECT payload FROM pending_notifications WHERE event_type='xp_milestone'"
        " AND json_extract(payload, '$.milestone') = 500"
    ).fetchone()
    assert row is not None
    payload = json.loads(row["payload"])
    assert payload["milestone"] == 500
    assert payload["rarity"] == "RARE"
    assert "item_name" in payload


def test_no_milestone_when_threshold_not_reached(db):
    before, after = _give_xp(db, 400)
    check_xp_milestones(db, "player_default", before, after)
    assert _count_milestone_notifs(db, 500) == 0


def test_milestone_not_fired_for_already_passed_threshold(db):
    # Give 600 XP so old_total >= 500; should not fire 500 milestone
    before_a, after_a = _give_xp(db, 600)
    # Now at 600; passing "old=600 new=1100" should fire 1000 but not 500
    before_b, after_b = _give_xp(db, 500)
    check_xp_milestones(db, "player_default", before_b, after_b)
    assert _count_milestone_notifs(db, 500) == 0
    assert _count_milestone_notifs(db, 1000) == 1


def test_milestone_fires_exactly_once_idempotent(db):
    before, after = _give_xp(db, 500)
    check_xp_milestones(db, "player_default", before, after)
    check_xp_milestones(db, "player_default", before, after)  # second call
    assert _count_milestone_notifs(db, 500) == 1


def test_multiple_milestones_in_one_jump(db):
    # Jump from 0 to 1100 — should fire 500 and 1000
    before, after = _give_xp(db, 1100)
    check_xp_milestones(db, "player_default", before, after)
    assert _count_milestone_notifs(db, 500) == 1
    assert _count_milestone_notifs(db, 1000) == 1
    assert _count_milestone_notifs(db, 2500) == 0


def test_epic_milestone_at_5000(db):
    before, after = _give_xp(db, 5000)
    check_xp_milestones(db, "player_default", before, after)
    row = db.execute(
        "SELECT payload FROM pending_notifications WHERE event_type='xp_milestone'"
        " AND json_extract(payload, '$.milestone') = 5000"
    ).fetchone()
    assert row is not None
    payload = json.loads(row["payload"])
    assert payload["rarity"] == "EPIC"


def test_milestone_awards_inventory_item_when_items_exist(db):
    # Seed an item
    item_data = json.dumps({
        "item_id": "test_item", "name": "Test Item", "rarity": "RARE",
        "category": "WORK", "description": "", "effects": [],
    })
    db.execute("INSERT OR IGNORE INTO item_definitions (item_id, data) VALUES ('test_item', ?)", (item_data,))
    db.commit()

    before, after = _give_xp(db, 500)
    check_xp_milestones(db, "player_default", before, after)

    row = db.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE character_id='player_default' AND item_id='test_item'"
    ).fetchone()
    assert row["n"] >= 1


def test_xp_milestones_list_has_expected_thresholds():
    thresholds = [m for m, _ in XP_MILESTONES]
    assert 500 in thresholds
    assert 1000 in thresholds
    assert 5000 in thresholds
