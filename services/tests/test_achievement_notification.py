"""Tests for enriched achievement_unlock notification payload."""
import json
import sqlite3
import pytest

from services.storage.db import init_db
from services.progression.achievements import check_achievements
from services.progression.achievement_milestones import check_and_unlock_milestones
from services.reward_ledger.ledger import insert_achievement_notification, get_pending_notifications


_PLAYER = "player_default"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'T', '{}')",
        (_PLAYER,),
    )
    conn.execute("INSERT OR IGNORE INTO streak_state (player_id) VALUES ('default')")
    conn.commit()
    yield conn
    conn.close()


def _get_achievement_payloads(conn: sqlite3.Connection) -> list[dict]:
    rows = get_pending_notifications(conn, _PLAYER)
    return [
        json.loads(r["payload"])
        for r in rows
        if r["event_type"] == "achievement_unlock"
    ]


# ── insert_achievement_notification ───────────────────────────────────────────

def test_notification_payload_has_name(db):
    insert_achievement_notification(db, _PLAYER, "test_ach", "Test Badge")
    db.commit()
    payloads = _get_achievement_payloads(db)
    assert len(payloads) == 1
    assert payloads[0]["name"] == "Test Badge"


def test_notification_payload_has_description(db):
    insert_achievement_notification(
        db, _PLAYER, "test_ach", "Test Badge",
        description="You did a thing.",
    )
    db.commit()
    payloads = _get_achievement_payloads(db)
    assert payloads[0]["description"] == "You did a thing."


def test_notification_chain_next_present(db):
    insert_achievement_notification(
        db, _PLAYER, "bronze", "Bronze Badge",
        description="Starter badge.",
        chain_next="Silver Badge",
    )
    db.commit()
    payloads = _get_achievement_payloads(db)
    assert payloads[0]["chain_next"] == "Silver Badge"


def test_notification_chain_next_null_for_leaf(db):
    insert_achievement_notification(
        db, _PLAYER, "gold", "Gold Badge",
        description="Final badge.",
        chain_next=None,
    )
    db.commit()
    payloads = _get_achievement_payloads(db)
    assert payloads[0]["chain_next"] is None


# ── check_achievements integration ────────────────────────────────────────────

def test_check_achievements_enriches_payload(db):
    """Achievement unlocked via check_achievements includes name and description."""
    db.execute(
        "INSERT INTO achievements (achievement_id, name, description, condition_type, threshold)"
        " VALUES ('xp_100', 'Century', 'Earn 100 XP.', 'total_xp', 100)"
    )
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 100)",
        (_PLAYER,),
    )
    db.commit()

    newly = check_achievements(db, _PLAYER)
    db.commit()

    assert "xp_100" in newly
    payloads = _get_achievement_payloads(db)
    assert any(p["name"] == "Century" and p["description"] == "Earn 100 XP." for p in payloads)


def test_check_achievements_chain_next_set(db):
    """chain_next is the child achievement name when one exists."""
    db.execute(
        "INSERT INTO achievements (achievement_id, name, description, condition_type, threshold)"
        " VALUES ('xp_100', 'Century', 'Earn 100 XP.', 'total_xp', 100)"
    )
    db.execute(
        "INSERT INTO achievements"
        " (achievement_id, name, description, condition_type, threshold, parent_achievement_id)"
        " VALUES ('xp_500', 'Five Hundred', 'Earn 500 XP.', 'total_xp', 500, 'xp_100')"
    )
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 100)",
        (_PLAYER,),
    )
    db.commit()

    check_achievements(db, _PLAYER)
    db.commit()

    payloads = _get_achievement_payloads(db)
    century_payload = next(p for p in payloads if p.get("achievement_id") == "xp_100")
    assert century_payload["chain_next"] == "Five Hundred"


def test_check_achievements_no_chain_next_for_leaf(db):
    """chain_next is null when the achievement has no child."""
    db.execute(
        "INSERT INTO achievements (achievement_id, name, description, condition_type, threshold)"
        " VALUES ('xp_100', 'Century', 'Earn 100 XP.', 'total_xp', 100)"
    )
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 100)",
        (_PLAYER,),
    )
    db.commit()

    check_achievements(db, _PLAYER)
    db.commit()

    payloads = _get_achievement_payloads(db)
    century_payload = next(p for p in payloads if p.get("achievement_id") == "xp_100")
    assert century_payload["chain_next"] is None


# ── check_and_unlock_milestones integration ───────────────────────────────────

def test_milestone_notification_has_description(db):
    """Milestone unlock notification includes the description from _MILESTONES."""
    db.execute(
        "INSERT INTO player_category_xp (character_id, category, xp) VALUES (?, 'WORK', 1000)",
        (_PLAYER,),
    )
    db.execute(
        "INSERT INTO player_profile (character_id, name, visual) VALUES (?, 'P', '{}')"
        " ON CONFLICT DO NOTHING",
        (_PLAYER,),
    )
    db.commit()

    newly = check_and_unlock_milestones(db, _PLAYER)
    db.commit()

    assert "xp_1000" in newly
    payloads = _get_achievement_payloads(db)
    xp_payload = next(p for p in payloads if p.get("achievement_id") == "xp_1000")
    assert xp_payload["description"] == "Accumulate 1,000 total XP."
