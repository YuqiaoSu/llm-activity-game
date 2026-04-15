# game-client/utils/RarityColor.gd
class_name RarityColor

const _COLORS := {
    "COMMON":    Color(0.70, 0.70, 0.70),
    "UNCOMMON":  Color(0.18, 0.80, 0.44),
    "RARE":      Color(0.27, 0.58, 1.00),
    "EPIC":      Color(0.64, 0.19, 0.85),
    "LEGENDARY": Color(1.00, 0.50, 0.00),
}


static func for_rarity(rarity: String) -> Color:
    return _COLORS.get(rarity, Color(0.70, 0.70, 0.70))
