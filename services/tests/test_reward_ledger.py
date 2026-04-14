import sqlite3
import pytest
from datetime import datetime, timezone
from services.storage.db import init_db
from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition, DropRequirement
from services.reward_ledger.ledger import record_drop, get_pending_notifications


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _item(item_id="focus_crystal") -> ItemDefinition:
    return ItemDefinition(
        item_id=item_id, name="Focus Crystal", category=Category.WORK,
        rarity=Rarity.RARE, drop_requirement=DropRequirement(),
        icon="x.png", description="",
    )


def test_record_drop_inserts_inventory_row(db):
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    rows = db.execute("SELECT * FROM inventory WHERE character_id='p1'").fetchall()
    assert len(rows) == 1
    assert rows[0]["item_id"] == "focus_crystal"


def test_record_drop_idempotent(db):
    """Replaying the same (chunk_id, roll_n) must not insert a duplicate."""
    result1 = record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    result2 = record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    assert result1 is True
    assert result2 is False
    rows = db.execute("SELECT * FROM inventory WHERE character_id='p1'").fetchall()
    assert len(rows) == 1


def test_record_drop_awards_category_xp(db):
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    row = db.execute(
        "SELECT xp FROM player_category_xp WHERE character_id='p1' AND category='WORK'"
    ).fetchone()
    assert row is not None
    assert row["xp"] > 0


def test_record_drop_creates_notification(db):
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    notifs = get_pending_notifications(db, character_id="p1")
    assert len(notifs) == 1
    assert notifs[0]["event_type"] == "item_drop"


def test_get_pending_notifications_excludes_acknowledged(db):
    record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    notif_id = db.execute(
        "SELECT notification_id FROM pending_notifications WHERE character_id='p1'"
    ).fetchone()["notification_id"]
    db.execute(
        "UPDATE pending_notifications SET acknowledged=1 WHERE notification_id=?",
        (notif_id,),
    )
    db.commit()
    assert get_pending_notifications(db, character_id="p1") == []


def test_record_drop_different_roll_n_allowed(db):
    """Same chunk_id but different roll_n are distinct drops."""
    r1 = record_drop(db, chunk_id="c1", roll_n=0, item=_item(), character_id="p1")
    r2 = record_drop(db, chunk_id="c1", roll_n=1, item=_item(), character_id="p1")
    assert r1 is True
    assert r2 is True
    rows = db.execute("SELECT * FROM inventory WHERE character_id='p1'").fetchall()
    assert len(rows) == 2
