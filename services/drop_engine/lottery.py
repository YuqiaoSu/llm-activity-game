from __future__ import annotations
import random
from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition
from services.models.place import Place
from services.contracts.chunk import Chunk

DEFAULT_RARITY_WEIGHTS: dict[Rarity, float] = {
    Rarity.COMMON: 60.0,
    Rarity.UNCOMMON: 25.0,
    Rarity.RARE: 10.0,
    Rarity.EPIC: 4.0,
    Rarity.LEGENDARY: 1.0,
}


def eligible_items(
    catalogue: list[ItemDefinition],
    chunk: Chunk,
    place: Place,
) -> list[ItemDefinition]:
    """
    Return items from `catalogue` that:
    1. Pass their own DropRequirement against `chunk`.
    2. Pass the place's item_pool filters (category/rarity/explicit).
       SPECIAL-category items bypass allowed_categories.
    """
    pool = place.item_pool
    result: list[ItemDefinition] = []

    for item in catalogue:
        # 1. DropRequirement gate
        if not item.drop_requirement.matches(chunk):
            continue

        # 2. Explicit override (if set, only these IDs are eligible)
        if pool.explicit_items is not None:
            if item.item_id not in pool.explicit_items:
                continue

        # 3. Category filter (SPECIAL always passes)
        if pool.allowed_categories is not None and item.category != Category.SPECIAL:
            if item.category not in pool.allowed_categories:
                continue

        # 4. Rarity filter
        if pool.allowed_rarities is not None:
            if item.rarity not in pool.allowed_rarities:
                continue

        result.append(item)

    return result


def weighted_draw(
    items: list[ItemDefinition],
    base_weights: dict[Rarity, float],
    drop_weight_mods: dict[str, float],
) -> ItemDefinition | None:
    """Weighted random draw; `drop_weight_mods` multiplies a rarity's base weight."""
    if not items:
        return None

    weights: list[float] = []
    for item in items:
        base = base_weights.get(item.rarity, 1.0)
        mod = drop_weight_mods.get(item.rarity.value, 1.0)
        weights.append(base * mod)

    return random.choices(items, weights=weights, k=1)[0]
