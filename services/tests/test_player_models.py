from services.models.enums import Category
from services.models.character import CharacterVisual
from services.models.player import PlayerProfile


def test_player_profile_defaults():
    p = PlayerProfile(
        character_id="player_001",
        visual=CharacterVisual(base_sprite="lumi.png"),
    )
    assert p.total_xp == 0
    assert p.level == 1
    assert p.evolution_stage == 0
    assert p.category_xp == {}
    assert p.equipped_items == []


def test_player_profile_total_xp_is_sum_of_categories():
    p = PlayerProfile(
        character_id="player_001",
        visual=CharacterVisual(base_sprite="lumi.png"),
        category_xp={Category.WORK: 500, Category.GAME: 300, Category.SLEEP: 200},
        total_xp=1000,
    )
    assert p.total_xp == sum(p.category_xp.values())


def test_player_profile_total_xp_cannot_be_spoofed():
    """total_xp is always derived from category_xp, even if caller passes a different value."""
    p = PlayerProfile(
        character_id="p1",
        visual=CharacterVisual(base_sprite="x.png"),
        total_xp=9999,
        category_xp={},
    )
    assert p.total_xp == 0
