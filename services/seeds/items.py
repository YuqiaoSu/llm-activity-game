"""Seed ItemDefinitions — one per rarity per representative category."""
from services.models.enums import Category, Rarity
from services.models.item import ItemDefinition, DropRequirement, Effect

SEED_ITEMS: list[ItemDefinition] = [
    # WORK
    ItemDefinition(
        item_id="focus_crystal_common", name="Focus Crystal",
        category=Category.WORK, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(activity_label="WORK", min_duration_sec=600),
        icon="focus_crystal_common.png",
        description="A small shard of concentrated effort.",
    ),
    ItemDefinition(
        item_id="focus_crystal_rare", name="Radiant Focus Crystal",
        category=Category.WORK, rarity=Rarity.RARE,
        drop_requirement=DropRequirement(activity_label="WORK", min_duration_sec=3600, min_confidence=0.85),
        effects=[Effect(effect_type="stat_buff", target="companion", params={"attack": 3})],
        icon="focus_crystal_rare.png",
        description="Forged from hours of deep work.",
    ),
    # GAME
    ItemDefinition(
        item_id="lucky_die_common", name="Lucky Die",
        category=Category.GAME, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(activity_label="GAME", min_duration_sec=600),
        icon="lucky_die.png",
        description="The sort of die you always roll first.",
    ),
    ItemDefinition(
        item_id="lucky_die_epic", name="Unstoppable Die",
        category=Category.GAME, rarity=Rarity.EPIC,
        drop_requirement=DropRequirement(activity_label="GAME", min_duration_sec=7200, min_confidence=0.9),
        effects=[Effect(effect_type="stat_buff", target="companion", params={"luck": 5})],
        icon="lucky_die_epic.png",
        description="Has never rolled a 1.",
    ),
    # SLEEP
    ItemDefinition(
        item_id="moonstone_common", name="Moonstone",
        category=Category.SLEEP, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(activity_label="SLEEP", min_duration_sec=14400, time_of_day="night"),
        icon="moonstone.png",
        description="Glows faintly with the memory of good rest.",
    ),
    ItemDefinition(
        item_id="dreamweave_legendary", name="Dreamweave Shard",
        category=Category.SLEEP, rarity=Rarity.LEGENDARY,
        drop_requirement=DropRequirement(
            activity_label="SLEEP", min_duration_sec=28800, min_confidence=0.95, time_of_day="night"
        ),
        effects=[
            Effect(effect_type="companion_skin", target="companion", params={"skin": "dream_form"}),
        ],
        icon="dreamweave_legendary.png",
        description="A fragment of a perfect dream. Extremely rare.",
    ),
    # EXPLORE
    ItemDefinition(
        item_id="waystone_uncommon", name="Waystone",
        category=Category.EXPLORE, rarity=Rarity.UNCOMMON,
        drop_requirement=DropRequirement(activity_label="EXPLORE", min_duration_sec=900),
        icon="waystone.png",
        description="Still warm from distant roads.",
    ),
    # SOCIAL
    ItemDefinition(
        item_id="resonance_gem_uncommon", name="Resonance Gem",
        category=Category.SOCIAL, rarity=Rarity.UNCOMMON,
        drop_requirement=DropRequirement(activity_label="SOCIAL", min_duration_sec=600),
        icon="resonance_gem.png",
        description="Vibrates when held near people.",
    ),
    # VIDEO
    ItemDefinition(
        item_id="lightframe_common", name="Lightframe",
        category=Category.VIDEO, rarity=Rarity.COMMON,
        drop_requirement=DropRequirement(activity_label="VIDEO", min_duration_sec=1800),
        icon="lightframe.png",
        description="Captured from a moment of pure visual wonder.",
    ),
    # SPECIAL
    ItemDefinition(
        item_id="celestial_coin_rare", name="Celestial Coin",
        category=Category.SPECIAL, rarity=Rarity.RARE,
        drop_requirement=DropRequirement(min_confidence=0.8),   # any label, any place
        effects=[Effect(effect_type="home_unlock", target="home_system", params={"room": "vault"})],
        icon="celestial_coin.png",
        description="Appears without warning. Always meaningful.",
    ),
    # ── slot-effect items (usable in place slots) ──────────────────────────
    ItemDefinition(
        item_id="focus_amplifier_uncommon", name="Focus Amplifier",
        category=Category.WORK, rarity=Rarity.UNCOMMON,
        drop_requirement=DropRequirement(activity_label="WORK", min_duration_sec=1800),
        effects=[Effect(effect_type="xp_multiplier", target="slot", params={"factor": 1.5})],
        icon="focus_amplifier.png",
        description="Place this in a slot to earn 50% more XP from all activities.",
    ),
    ItemDefinition(
        item_id="fortune_chip_uncommon", name="Fortune Chip",
        category=Category.GAME, rarity=Rarity.UNCOMMON,
        drop_requirement=DropRequirement(activity_label="GAME", min_duration_sec=1800),
        effects=[Effect(effect_type="drop_weight_mod", target="slot", params={"rarity": "RARE", "factor": 2.0})],
        icon="fortune_chip.png",
        description="Place this in a slot to double the weight of RARE item drops.",
    ),
    # ── category-specific XP bonus items ──────────────────────────────────────
    ItemDefinition(
        item_id="work_totem_rare", name="Work Totem",
        category=Category.WORK, rarity=Rarity.RARE,
        drop_requirement=DropRequirement(activity_label="WORK", min_duration_sec=3600),
        effects=[Effect(effect_type="category_xp_bonus", target="slot",
                        params={"category": "WORK", "factor": 1.3})],
        icon="work_totem.png",
        description="Place this in a slot to earn 30% more XP from WORK activity.",
    ),
    ItemDefinition(
        item_id="game_totem_rare", name="Game Totem",
        category=Category.GAME, rarity=Rarity.RARE,
        drop_requirement=DropRequirement(activity_label="GAME", min_duration_sec=3600),
        effects=[Effect(effect_type="category_xp_bonus", target="slot",
                        params={"category": "GAME", "factor": 1.3})],
        icon="game_totem.png",
        description="Place this in a slot to earn 30% more XP from GAME activity.",
    ),
    ItemDefinition(
        item_id="explore_totem_epic", name="Explorer's Totem",
        category=Category.EXPLORE, rarity=Rarity.EPIC,
        drop_requirement=DropRequirement(activity_label="EXPLORE", min_duration_sec=3600),
        effects=[Effect(effect_type="category_xp_bonus", target="slot",
                        params={"category": "EXPLORE", "factor": 1.5})],
        icon="explore_totem.png",
        description="Place this in a slot to earn 50% more XP from EXPLORE activity.",
    ),
]
