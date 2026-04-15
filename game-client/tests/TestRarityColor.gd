# game-client/tests/TestRarityColor.gd
extends Node

const RarityColor := preload("res://utils/RarityColor.gd")

var _passed := 0
var _failed := 0


func _ready() -> void:
    _check("COMMON is gray",      RarityColor.for_rarity("COMMON")    == Color(0.70, 0.70, 0.70))
    _check("UNCOMMON is green",   RarityColor.for_rarity("UNCOMMON")  == Color(0.18, 0.80, 0.44))
    _check("RARE is blue",        RarityColor.for_rarity("RARE")      == Color(0.27, 0.58, 1.00))
    _check("EPIC is purple",      RarityColor.for_rarity("EPIC")      == Color(0.64, 0.19, 0.85))
    _check("LEGENDARY is orange", RarityColor.for_rarity("LEGENDARY") == Color(1.00, 0.50, 0.00))
    _check("unknown is gray",     RarityColor.for_rarity("MYSTERY")   == Color(0.70, 0.70, 0.70))
    print("RarityColor: %d passed, %d failed" % [_passed, _failed])
    get_tree().quit(1 if _failed > 0 else 0)


func _check(label: String, ok: bool) -> void:
    if ok:
        _passed += 1
        print("  PASS: %s" % label)
    else:
        _failed += 1
        push_error("  FAIL: %s" % label)
