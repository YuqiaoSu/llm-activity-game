from services.models.enums import CharacterType
from services.models.character import CharacterVisual, Character


def test_character_visual_defaults():
    v = CharacterVisual(base_sprite="companion_base.png")
    assert v.evolution_stage == 0
    assert v.skin is None
    assert v.accessories == []
    assert v.anim_state == "idle"


def test_character_creation():
    c = Character(
        character_id="player_001",
        name="Lumi",
        character_type=CharacterType.COMPANION,
        visual=CharacterVisual(base_sprite="lumi_base.png"),
    )
    assert c.level == 1
    assert c.luck == 5
    assert c.stat_mods == {}
    assert c.equipped_items == []


def test_character_stat_mods_are_separate_from_base():
    c = Character(
        character_id="p", name="X", character_type=CharacterType.COMPANION,
        attack=10, luck=5,
        stat_mods={"attack": 3},
        visual=CharacterVisual(base_sprite="x.png"),
    )
    assert c.attack == 10
    assert c.stat_mods["attack"] == 3
