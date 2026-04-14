from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from services.models.enums import Category
from services.models.character import CharacterVisual


class PlayerProfile(BaseModel):
    character_id: str
    total_xp: int = 0            # always == sum(category_xp.values())
    level: int = 1
    evolution_stage: int = 0
    category_xp: dict[Category, int] = Field(default_factory=dict)
    visual: CharacterVisual
    equipped_items: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_total_xp(self) -> "PlayerProfile":
        object.__setattr__(self, "total_xp", sum(self.category_xp.values()))
        return self
