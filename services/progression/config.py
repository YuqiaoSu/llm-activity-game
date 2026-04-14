# XP_PER_LEVEL[i] = cumulative XP required to reach level (i+1)
# Level 1 = 0 XP (index 0), Level 2 = 100 XP (index 1), etc.
XP_PER_LEVEL: list[int] = [
    0,       # level 1
    100,     # level 2
    250,     # level 3
    500,     # level 4
    900,     # level 5
    1_400,   # level 6
    2_000,   # level 7
    2_750,   # level 8
    3_600,   # level 9
    4_600,   # level 10
]

# EVOLUTION_STAGES: {stage: (min_level, max_level)}
EVOLUTION_STAGES: dict[int, tuple[int, int]] = {
    0: (1, 5),    # Hatchling
    1: (6, 15),   # Growing
    2: (16, 30),  # Mature
    3: (31, 999), # Legendary
}

# XP awarded per minute of classified activity in a chunk
XP_PER_MINUTE: int = 1
