from datetime import datetime, timezone
from services.models.enums import Category, Rarity
from services.models.item import Effect, DropRequirement, ItemDefinition, InventoryItem
from services.contracts.chunk import Chunk


def _chunk(**kw) -> Chunk:
    defaults = dict(
        chunk_id="c_001", label="WORK", duration_sec=1800,
        confidence=0.92, started_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
    )
    return Chunk(**{**defaults, **kw})


def test_effect_creation():
    e = Effect(effect_type="stat_buff", target="companion", params={"luck": 2})
    assert e.effect_type == "stat_buff"
    assert e.params["luck"] == 2


def test_drop_requirement_defaults():
    req = DropRequirement()
    assert req.activity_label is None
    assert req.min_duration_sec == 0
    assert req.min_confidence == 0.0


def test_drop_requirement_matches_any_chunk():
    req = DropRequirement()
    assert req.matches(_chunk()) is True


def test_drop_requirement_label_filter():
    req = DropRequirement(activity_label="WORK")
    assert req.matches(_chunk(label="WORK")) is True
    assert req.matches(_chunk(label="GAME")) is False


def test_drop_requirement_min_duration():
    req = DropRequirement(min_duration_sec=3600)
    assert req.matches(_chunk(duration_sec=3600)) is True
    assert req.matches(_chunk(duration_sec=3599)) is False


def test_drop_requirement_min_confidence():
    req = DropRequirement(min_confidence=0.95)
    assert req.matches(_chunk(confidence=0.95)) is True
    assert req.matches(_chunk(confidence=0.94)) is False


def test_drop_requirement_time_of_day():
    req = DropRequirement(time_of_day="morning")
    assert req.matches(_chunk(time_of_day="morning")) is True
    assert req.matches(_chunk(time_of_day="night")) is False
    assert req.matches(_chunk(time_of_day=None)) is False


def test_item_definition_creation():
    item = ItemDefinition(
        item_id="focus_crystal_rare",
        name="Focus Crystal",
        category=Category.WORK,
        rarity=Rarity.RARE,
        drop_requirement=DropRequirement(activity_label="WORK", min_duration_sec=1800),
        effects=[Effect(effect_type="stat_buff", target="companion", params={"attack": 3})],
        icon="focus_crystal.png",
        description="Formed from deep concentration.",
        stackable=False,
    )
    assert item.rarity == Rarity.RARE
    assert len(item.effects) == 1


def test_inventory_item_creation():
    inv = InventoryItem(
        instance_id="inv_001",
        item_id="focus_crystal_rare",
        acquired_at=datetime(2026, 4, 14, tzinfo=timezone.utc),
        source_chunk="c_001",
    )
    assert inv.equipped is False
    assert inv.placed_in is None
