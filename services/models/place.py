from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from services.models.enums import Category, Rarity, SlotType, PlaceState
from services.models.item import Effect


class Condition(BaseModel):
    condition_type: str
    params: dict[str, Any] = Field(default_factory=dict)


class PlaceItemPool(BaseModel):
    allowed_categories: list[Category] | None = None    # None = all
    allowed_rarities: list[Rarity] | None = None         # None = all
    explicit_items: list[str] | None = None              # overrides category filter
    drop_weight_mods: dict[str, float] = Field(default_factory=dict)  # rarity string → multiplier


class PlaceSlot(BaseModel):
    slot_id: str
    place_id: str
    slot_type: SlotType
    accepts: list[str] | None = None    # category/character_type filter; None = no filter
    occupant_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    metadata: dict[str, Any] = Field(default_factory=dict)
    slots: list[PlaceSlot] = Field(default_factory=list)
    connected_to: list[str] = Field(default_factory=list)
    parent_place: str | None = None
    active_effects: list[Effect] = Field(default_factory=list)  # rebuilt whenever a slot occupant changes
    xp: int = 0
    level: int = 1
