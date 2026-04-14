import sqlite3
import json
import pytest
from services.storage.db import init_db
from services.models.enums import Category, PlaceState, SlotType
from services.models.place import Place, PlaceItemPool, PlaceSlot, Condition
from services.models.enums import Rarity
from services.models.item import Effect, DropRequirement, ItemDefinition
from services.place_service.service import (
    save_place, get_place, list_places, set_slot_occupant, check_unlock_condition,
)
from services.place_service.effects import rebuild_active_effects


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _home_place(state=PlaceState.LOCKED) -> Place:
    return Place(
        place_id="home_001",
        name="Study",
        place_type="home",
        category=Category.WORK,
        state=state,
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
        slots=[
            PlaceSlot(slot_id="s_1", place_id="home_001", slot_type=SlotType.ITEM),
        ],
    )


def test_save_and_get_place(db):
    save_place(db, _home_place())
    place = get_place(db, "home_001")
    assert place is not None
    assert place.name == "Study"
    assert place.category == Category.WORK
    assert len(place.slots) == 1


def test_get_nonexistent_place_returns_none(db):
    assert get_place(db, "no_such_place") is None


def test_list_places(db):
    save_place(db, _home_place())
    places = list_places(db)
    assert len(places) == 1
    assert places[0].place_id == "home_001"


def test_set_slot_occupant(db):
    save_place(db, _home_place())
    set_slot_occupant(db, slot_id="s_1", occupant_id="inv_001")
    place = get_place(db, "home_001")
    assert place.slots[0].occupant_id == "inv_001"


def test_set_slot_occupant_clear(db):
    save_place(db, _home_place())
    set_slot_occupant(db, slot_id="s_1", occupant_id="inv_001")
    set_slot_occupant(db, slot_id="s_1", occupant_id=None)
    place = get_place(db, "home_001")
    assert place.slots[0].occupant_id is None


def test_check_unlock_condition_player_level_met(db):
    place = _home_place()
    place = place.model_copy(update={
        "unlock_condition": Condition(condition_type="player_level", params={"min_level": 3})
    })
    save_place(db, place)
    assert check_unlock_condition(db, place, player_level=5) is True


def test_check_unlock_condition_player_level_not_met(db):
    place = _home_place()
    place = place.model_copy(update={
        "unlock_condition": Condition(condition_type="player_level", params={"min_level": 10})
    })
    save_place(db, place)
    assert check_unlock_condition(db, place, player_level=5) is False


def test_check_unlock_no_condition(db):
    save_place(db, _home_place())
    place = get_place(db, "home_001")
    assert check_unlock_condition(db, place, player_level=1) is True


def test_save_place_roundtrip_preserves_item_pool(db):
    place = _home_place()
    save_place(db, place)
    loaded = get_place(db, "home_001")
    assert loaded.item_pool.allowed_categories == [Category.WORK]


def test_rebuild_active_effects_empty_slot_contributes_nothing(db):
    place = _home_place(state=PlaceState.UNLOCKED)
    save_place(db, place)
    place = get_place(db, "home_001")
    effects = rebuild_active_effects(db, place)
    assert effects == []
    rows = db.execute("SELECT * FROM place_active_effects WHERE place_id='home_001'").fetchall()
    assert len(rows) == 0


def test_rebuild_active_effects_occupied_slot_contributes_effects(db):
    item = ItemDefinition(
        item_id="buff_crystal", name="Buff Crystal",
        category=Category.WORK, rarity=Rarity.RARE,
        drop_requirement=DropRequirement(),
        effects=[Effect(effect_type="stat_buff", target="companion", params={"luck": 3})],
        icon="x.png", description="",
    )
    db.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item.item_id, item.model_dump_json()),
    )
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES ('inv_001', 'player_default', 'buff_crystal', '2026-04-14T00:00:00+00:00', 'c1')"
    )
    db.commit()
    save_place(db, _home_place(state=PlaceState.UNLOCKED))
    set_slot_occupant(db, slot_id="s_1", occupant_id="inv_001")
    place = get_place(db, "home_001")
    effects = rebuild_active_effects(db, place)
    assert len(effects) == 1
    assert effects[0].effect_type == "stat_buff"
    rows = db.execute("SELECT * FROM place_active_effects WHERE place_id='home_001'").fetchall()
    assert len(rows) == 1


def test_rebuild_active_effects_is_idempotent(db):
    item = ItemDefinition(
        item_id="buff_crystal2", name="Buff Crystal 2",
        category=Category.WORK, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(),
        effects=[Effect(effect_type="home_unlock", target="home_system", params={})],
        icon="x.png", description="",
    )
    db.execute(
        "INSERT INTO item_definitions (item_id, data) VALUES (?, ?)",
        (item.item_id, item.model_dump_json()),
    )
    db.execute(
        "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
        "VALUES ('inv_002', 'player_default', 'buff_crystal2', '2026-04-14T00:00:00+00:00', 'c2')"
    )
    db.commit()
    save_place(db, _home_place(state=PlaceState.UNLOCKED))
    set_slot_occupant(db, slot_id="s_1", occupant_id="inv_002")
    place = get_place(db, "home_001")
    rebuild_active_effects(db, place)
    rebuild_active_effects(db, place)
    rows = db.execute("SELECT * FROM place_active_effects WHERE place_id='home_001'").fetchall()
    assert len(rows) == 1
