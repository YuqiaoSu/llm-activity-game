import sqlite3
import json
import pytest
from services.storage.db import init_db
from services.models.enums import Category, PlaceState, SlotType
from services.models.place import Place, PlaceItemPool, PlaceSlot, Condition
from services.place_service.service import (
    save_place, get_place, list_places, set_slot_occupant, check_unlock_condition,
)


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
