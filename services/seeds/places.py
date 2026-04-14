"""Seed the starting Home place — UNLOCKED, no occupants."""
from services.models.enums import Category, PlaceState, SlotType
from services.models.place import Place, PlaceItemPool, PlaceSlot

SEED_PLACES: list[Place] = [
    Place(
        place_id="home_study",
        name="The Study",
        place_type="home",
        description="A quiet room lit by a single lamp. Work happens here.",
        category=Category.WORK,
        state=PlaceState.UNLOCKED,
        item_pool=PlaceItemPool(
            allowed_categories=[Category.WORK, Category.SPECIAL],
        ),
        slots=[
            PlaceSlot(
                slot_id="study_slot_desk",
                place_id="home_study",
                slot_type=SlotType.ITEM,
                metadata={"label": "Desk", "position": {"x": 0.3, "y": 0.5}},
            ),
            PlaceSlot(
                slot_id="study_slot_shelf",
                place_id="home_study",
                slot_type=SlotType.ITEM,
                metadata={"label": "Shelf", "position": {"x": 0.7, "y": 0.3}},
            ),
        ],
        metadata={"theme": "study", "music": "calm_focus"},
    ),
]
