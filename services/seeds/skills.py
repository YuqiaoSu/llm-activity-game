"""Seed data for passive skills."""
import json

# Each tuple: (skill_id, name, description, xp_cost, effect_type, effect_params_json)
SEED_SKILLS: list[tuple] = [
    (
        "xp_boost_i",
        "XP Boost I",
        "Earn 10% more XP from all activities.",
        500,
        "xp_multiplier",
        json.dumps({"factor": 1.10}),
    ),
    (
        "xp_boost_ii",
        "XP Boost II",
        "Earn an additional 15% more XP from all activities.",
        1500,
        "xp_multiplier",
        json.dumps({"factor": 1.15}),
    ),
    (
        "rare_finder",
        "Rare Finder",
        "Increase RARE item drop weight by 25%.",
        800,
        "drop_weight_mod",
        json.dumps({"rarity": "RARE", "factor": 1.25}),
    ),
    (
        "epic_seeker",
        "Epic Seeker",
        "Increase EPIC item drop weight by 20%.",
        2000,
        "drop_weight_mod",
        json.dumps({"rarity": "EPIC", "factor": 1.20}),
    ),
    (
        "work_specialist",
        "Work Specialist",
        "Earn 20% more XP from WORK activities.",
        1000,
        "category_xp_bonus",
        json.dumps({"category": "WORK", "factor": 1.20}),
    ),
    (
        "extra_roll",
        "Lucky Strike",
        "Gain one extra item drop roll per activity chunk.",
        2500,
        "extra_roll",
        json.dumps({"rolls": 1}),
    ),
]
