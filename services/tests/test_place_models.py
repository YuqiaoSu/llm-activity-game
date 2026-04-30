from services.models.enums import Category, SlotType, PlaceState
from services.models.place import Condition, PlaceItemPool, PlaceSlot, Place


def test_place_item_pool_defaults():
    pool = PlaceItemPool()
    assert pool.allowed_categories is None
    assert pool.allowed_rarities is None
    assert pool.explicit_items is None
    assert pool.drop_weight_mods == {}


def test_place_slot_creation():
    slot = PlaceSlot(slot_id="s_001", place_id="home_001", slot_type=SlotType.ITEM)
    assert slot.occupant_id is None
    assert slot.accepts is None


def test_place_creation_minimal():
    place = Place(
        place_id="home_001",
        name="Study",
        place_type="home",
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
    )
    assert place.state == PlaceState.LOCKED
    assert place.category is None
    assert place.slots == []
    assert place.connected_to == []
    assert place.active_effects == []


def test_place_with_category_and_slots():
    place = Place(
        place_id="home_001",
        name="Study",
        place_type="home",
        category=Category.WORK,
        state=PlaceState.UNLOCKED,
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
        slots=[
            PlaceSlot(slot_id="s_1", place_id="home_001", slot_type=SlotType.ITEM),
            PlaceSlot(slot_id="s_2", place_id="home_001", slot_type=SlotType.CHARACTER),
        ],
    )
    assert len(place.slots) == 2
    assert place.category == Category.WORK


def test_condition_open_params():
    cond = Condition(condition_type="player_level", params={"min_level": 5})
    assert cond.params["min_level"] == 5
