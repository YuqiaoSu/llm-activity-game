from services.models.enums import Category, Rarity, PlaceState


def test_category_values():
    assert set(Category) == {
        Category.WORK, Category.GAME, Category.VIDEO,
        Category.SOCIAL, Category.EXPLORE, Category.SLEEP, Category.SPECIAL,
    }


def test_rarity_values():
    assert list(Rarity) == [
        Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.EPIC, Rarity.LEGENDARY,
    ]


def test_enums_are_strings():
    assert Category.WORK == "WORK"
    assert Rarity.COMMON == "COMMON"


def test_place_state_values():
    assert set(PlaceState) == {
        PlaceState.LOCKED, PlaceState.UNLOCKED, PlaceState.ACTIVE, PlaceState.COMPLETED,
    }
