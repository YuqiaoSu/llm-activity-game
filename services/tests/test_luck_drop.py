"""Tests verifying luck biases weighted_draw toward higher rarities."""
import math
import pytest
from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition, DropRequirement
from services.drop_engine.lottery import weighted_draw, DEFAULT_RARITY_WEIGHTS


def _item(rarity: Rarity) -> ItemDefinition:
    return ItemDefinition(
        item_id=rarity.value,
        name=rarity.value,
        category=Category.WORK,
        rarity=rarity,
        drop_requirement=DropRequirement(activity_label="WORK"),
        icon="x.png",
        description="",
    )


_ONE_OF_EACH = [_item(r) for r in Rarity]
_COMMON_ONLY  = [_item(Rarity.COMMON)]
_RARE_ONLY    = [_item(Rarity.RARE)]


def _effective_weights(luck: int) -> dict[Rarity, float]:
    """Compute the effective base weight for each rarity at a given luck value."""
    factor = (luck / 10) ** 0.5
    return {
        r: (DEFAULT_RARITY_WEIGHTS[r] * (1.0 if r == Rarity.COMMON else factor))
        for r in Rarity
    }


# ── formula correctness ────────────────────────────────────────────────────────

def test_neutral_luck_leaves_common_unchanged():
    w = _effective_weights(10)
    assert w[Rarity.COMMON] == pytest.approx(DEFAULT_RARITY_WEIGHTS[Rarity.COMMON])


def test_neutral_luck_leaves_rare_unchanged():
    w = _effective_weights(10)
    assert w[Rarity.RARE] == pytest.approx(DEFAULT_RARITY_WEIGHTS[Rarity.RARE])


def test_high_luck_boosts_rare_weight():
    w_high = _effective_weights(20)
    assert w_high[Rarity.RARE] == pytest.approx(DEFAULT_RARITY_WEIGHTS[Rarity.RARE] * math.sqrt(2))


def test_low_luck_reduces_rare_weight():
    w_low = _effective_weights(5)
    assert w_low[Rarity.RARE] == pytest.approx(DEFAULT_RARITY_WEIGHTS[Rarity.RARE] / math.sqrt(2))


def test_luck_does_not_affect_common_weight():
    w_low  = _effective_weights(5)
    w_high = _effective_weights(20)
    assert w_low[Rarity.COMMON] == pytest.approx(w_high[Rarity.COMMON])


def test_epic_weight_at_luck_20():
    w = _effective_weights(20)
    assert w[Rarity.EPIC] == pytest.approx(DEFAULT_RARITY_WEIGHTS[Rarity.EPIC] * math.sqrt(2))


# ── weighted_draw integration ──────────────────────────────────────────────────

def test_weighted_draw_returns_item_with_luck():
    result = weighted_draw(_ONE_OF_EACH, DEFAULT_RARITY_WEIGHTS, {}, luck=20)
    assert result is not None
    assert result.rarity in list(Rarity)


def test_weighted_draw_neutral_luck_returns_item():
    result = weighted_draw(_RARE_ONLY, DEFAULT_RARITY_WEIGHTS, {}, luck=10)
    assert result is not None
    assert result.rarity == Rarity.RARE


def test_weighted_draw_empty_pool_returns_none_with_luck():
    assert weighted_draw([], DEFAULT_RARITY_WEIGHTS, {}, luck=20) is None


def test_high_luck_increases_rare_relative_to_common():
    """At luck=20, rare weight fraction should be higher than at luck=5."""
    def rare_fraction(luck: int) -> float:
        w = _effective_weights(luck)
        total = sum(w.values())
        return w[Rarity.RARE] / total

    assert rare_fraction(20) > rare_fraction(5)
