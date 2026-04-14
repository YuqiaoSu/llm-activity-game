import random
from datetime import datetime, timezone
from services.models.enums import Category, Rarity
from services.models.item import DropRequirement, ItemDefinition, Effect
from services.models.place import Place, PlaceItemPool
from services.contracts.chunk import Chunk
from services.drop_engine.lottery import eligible_items, weighted_draw, DEFAULT_RARITY_WEIGHTS


def _item(item_id, label, rarity, min_dur=0) -> ItemDefinition:
    return ItemDefinition(
        item_id=item_id, name=item_id, category=Category.WORK, rarity=rarity,
        drop_requirement=DropRequirement(activity_label=label, min_duration_sec=min_dur),
        icon="x.png", description="",
    )


def _chunk(label="WORK", duration_sec=1800, confidence=0.9, time_of_day=None) -> Chunk:
    return Chunk(
        chunk_id="c1", label=label, duration_sec=duration_sec,
        confidence=confidence, started_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
        time_of_day=time_of_day,
    )


def _place(categories=None, rarities=None, explicit=None) -> Place:
    return Place(
        place_id="p1", name="Home", place_type="home",
        item_pool=PlaceItemPool(
            allowed_categories=categories,
            allowed_rarities=rarities,
            explicit_items=explicit,
        ),
    )


CATALOGUE = [
    _item("work_common", "WORK", Rarity.COMMON),
    _item("work_rare", "WORK", Rarity.RARE),
    _item("game_common", "GAME", Rarity.COMMON),
]


def test_eligible_items_no_place_filter():
    chunk = _chunk("WORK")
    place = _place()
    result = eligible_items(CATALOGUE, chunk, place)
    ids = {i.item_id for i in result}
    assert "work_common" in ids
    assert "work_rare" in ids
    assert "game_common" not in ids   # GAME label, doesn't match WORK chunk


def test_eligible_items_place_category_filter():
    special_item = ItemDefinition(
        item_id="special_item", name="S", category=Category.SPECIAL,
        rarity=Rarity.EPIC,
        drop_requirement=DropRequirement(),
        icon="s.png", description="",
    )
    cat = CATALOGUE + [special_item]
    place = _place(categories=[Category.WORK])
    chunk = _chunk("WORK")
    result = eligible_items(cat, chunk, place)
    ids = {i.item_id for i in result}
    assert "work_common" in ids
    assert "special_item" in ids    # SPECIAL bypasses category filter
    assert "game_common" not in ids


def test_eligible_items_rarity_filter():
    place = _place(rarities=[Rarity.COMMON])
    chunk = _chunk("WORK")
    result = eligible_items(CATALOGUE, chunk, place)
    assert all(i.rarity == Rarity.COMMON for i in result)


def test_weighted_draw_returns_item():
    random.seed(42)
    items = [CATALOGUE[0], CATALOGUE[1]]
    result = weighted_draw(items, DEFAULT_RARITY_WEIGHTS, drop_weight_mods={})
    assert result is not None
    assert result in items


def test_weighted_draw_empty_returns_none():
    assert weighted_draw([], DEFAULT_RARITY_WEIGHTS, {}) is None


def test_eligible_items_explicit_empty_list_blocks_all():
    """explicit_items=[] means whitelist of nothing — no items eligible."""
    place = _place(explicit=[])
    result = eligible_items(CATALOGUE, _chunk("WORK"), place)
    assert result == []


def test_weighted_draw_applies_drop_weight_mods():
    """A 1000x multiplier on COMMON should make COMMON overwhelmingly likely."""
    random.seed(99)
    items = [CATALOGUE[0], CATALOGUE[1]]  # work_common (COMMON) and work_rare (RARE)
    results = [
        weighted_draw(items, DEFAULT_RARITY_WEIGHTS, drop_weight_mods={"COMMON": 1000.0})
        for _ in range(20)
    ]
    common_count = sum(1 for r in results if r.rarity == Rarity.COMMON)
    assert common_count >= 18   # statistically near-certain with 1000x boost
