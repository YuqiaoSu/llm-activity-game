from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field
from services.models.enums import Category, Rarity

if TYPE_CHECKING:
    from services.contracts.chunk import Chunk


class Effect(BaseModel):
    """A typed, extensible payload interpreted by whichever system owns `target`."""
    effect_type: str
    target: str
    params: dict[str, Any] = Field(default_factory=dict)


class DropRequirement(BaseModel):
    """Eligibility rule evaluated against a Chunk. All conditions must pass."""
    activity_label: str | None = None       # None = any label
    min_duration_sec: int = 0
    min_confidence: float = 0.0
    time_of_day: str | None = None          # None = any time
    extra: dict[str, Any] = Field(default_factory=dict)  # future: streak_active, season, event

    def matches(self, chunk: "Chunk") -> bool:
        if self.activity_label is not None and self.activity_label != chunk.label:
            return False
        if chunk.duration_sec < self.min_duration_sec:
            return False
        if chunk.confidence < self.min_confidence:
            return False
        if self.time_of_day is not None and self.time_of_day != chunk.time_of_day:
            return False
        return True


class ItemDefinition(BaseModel):
    item_id: str
    name: str
    category: Category
    rarity: Rarity
    drop_requirement: DropRequirement
    effects: list[Effect] = Field(default_factory=list)
    icon: str
    description: str
    stackable: bool = False


class InventoryItem(BaseModel):
    instance_id: str
    item_id: str
    acquired_at: datetime
    source_chunk: str
    equipped: bool = False
    placed_in: str | None = None      # PlaceSlot.slot_id or None
