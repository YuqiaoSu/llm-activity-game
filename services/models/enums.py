from enum import Enum


class Category(str, Enum):
    WORK = "WORK"
    GAME = "GAME"
    VIDEO = "VIDEO"
    SOCIAL = "SOCIAL"
    EXPLORE = "EXPLORE"
    SLEEP = "SLEEP"
    SPECIAL = "SPECIAL"


class Rarity(str, Enum):
    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    EPIC = "EPIC"
    LEGENDARY = "LEGENDARY"


class CharacterType(str, Enum):
    COMPANION = "COMPANION"
    NPC = "NPC"
    ENEMY = "ENEMY"
    BOSS = "BOSS"


class SlotType(str, Enum):
    ITEM = "ITEM"
    CHARACTER = "CHARACTER"
    ANY = "ANY"


class PlaceState(str, Enum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
