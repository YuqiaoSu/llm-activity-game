"""Seed places: one UNLOCKED starter + three progressively-locked places."""
from services.models.enums import Category, PlaceState, SlotType
from services.models.place import Condition, Place, PlaceItemPool, PlaceSlot

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
    Place(
        place_id="workshop",
        name="The Workshop",
        place_type="workshop",
        description="A cluttered workbench. Reach level 3 to unlock it.",
        category=Category.WORK,
        state=PlaceState.LOCKED,
        unlock_condition=Condition(condition_type="player_level", params={"min_level": 3}),
        item_pool=PlaceItemPool(allowed_categories=[Category.WORK]),
        slots=[
            PlaceSlot(
                slot_id="workshop_slot_bench",
                place_id="workshop",
                slot_type=SlotType.ITEM,
                metadata={"label": "Workbench", "position": {"x": 0.4, "y": 0.6}},
            ),
        ],
        metadata={"theme": "workshop"},
    ),
    Place(
        place_id="arcade",
        name="The Arcade",
        place_type="arcade",
        description="Flashing lights and high scores. Requires level 5.",
        category=Category.GAME,
        state=PlaceState.LOCKED,
        unlock_condition=Condition(condition_type="player_level", params={"min_level": 5}),
        item_pool=PlaceItemPool(allowed_categories=[Category.GAME, Category.SPECIAL]),
        slots=[
            PlaceSlot(
                slot_id="arcade_slot_cabinet",
                place_id="arcade",
                slot_type=SlotType.ITEM,
                metadata={"label": "Cabinet", "position": {"x": 0.5, "y": 0.5}},
            ),
            PlaceSlot(
                slot_id="arcade_slot_trophy",
                place_id="arcade",
                slot_type=SlotType.ITEM,
                metadata={"label": "Trophy Case", "position": {"x": 0.75, "y": 0.3}},
            ),
        ],
        metadata={"theme": "arcade"},
    ),
    Place(
        place_id="observatory",
        name="The Observatory",
        place_type="outdoors",
        description="Stars and open sky. Unlocks at level 8.",
        category=Category.EXPLORE,
        state=PlaceState.LOCKED,
        unlock_condition=Condition(condition_type="player_level", params={"min_level": 8}),
        item_pool=PlaceItemPool(allowed_categories=[Category.EXPLORE, Category.SPECIAL]),
        slots=[
            PlaceSlot(
                slot_id="observatory_slot_scope",
                place_id="observatory",
                slot_type=SlotType.ITEM,
                metadata={"label": "Telescope", "position": {"x": 0.5, "y": 0.4}},
            ),
        ],
        metadata={"theme": "observatory"},
    ),
]
