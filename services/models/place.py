from __future__ import annotations
from pydantic import BaseModel
from services.models.enums import Category, Rarity, SlotType, PlaceState
from services.models.item import Effect


class Condition(BaseModel):
    condition_type: str
    params: dict = {}


class PlaceItemPool(BaseModel):
    allowed_categories: list[Category] | None = None    # None = all
    allowed_rarities: list[Rarity] | None = None         # None = all
    explicit_items: list[str] | None = None              # overrides category filter
    drop_weight_mods: dict[str, float] = {}              # rarity string → multiplier


class PlaceSlot(BaseModel):
    slot_id: str
    place_id: str
    slot_type: SlotType
    accepts: list[str] | None = None    # category/character_type filter; None = no filter
    occupant_id: str | None = None
    metadata: dict = {}


class Place(BaseModel):
    place_id: str
    name: str
    place_type: str
    description: str = ""
    icon: str | None = None
    category: Category | None = None
    item_pool: PlaceItemPool
    state: PlaceState = PlaceState.LOCKED
    unlock_condition: Condition | None = None
    metadata: dict = {}
    slots: list[PlaceSlot] = []
    connected_to: list[str] = []
    parent_place: str | None = None
    active_effects: list[Effect] = []   # rebuilt whenever a slot occupant changes
