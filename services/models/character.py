from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from services.models.enums import CharacterType


class CharacterVisual(BaseModel):
    base_sprite: str
    evolution_stage: int = 0
    skin: str | None = None
    accessories: list[str] = Field(default_factory=list)
    anim_state: str = "idle"


class Character(BaseModel):
    character_id: str
    name: str
    character_type: CharacterType
    level: int = 1
    xp: int = 0
    hp_max: int = 100
    hp_current: int = 100
    attack: int = 10
    defense: int = 10
    luck: int = 5
    stat_mods: dict[str, Any] = Field(default_factory=dict)  # overlay only — base stats above never change
    visual: CharacterVisual
    equipped_items: list[str] = Field(default_factory=list)  # InventoryItem.instance_ids
