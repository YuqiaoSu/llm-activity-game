# game-client/scenes/Places.gd
extends Control

@onready var _count_label: Label        = $VBox/Header/CountLabel
@onready var _place_list: VBoxContainer = $VBox/Scroll/PlaceList

const _COLOR_UNLOCKED := Color(0.3, 0.8, 0.3)
const _COLOR_LOCKED   := Color(0.5, 0.5, 0.5)


func _ready() -> void:
    $VBox/Header/BackButton.pressed.connect(func() -> void:
        get_tree().change_scene_to_file("res://scenes/Main.tscn")
    )
    GameAPI.places_updated.connect(_on_places)
    GameAPI.fetch_places()


func _exit_tree() -> void:
    if GameAPI.places_updated.is_connected(_on_places):
        GameAPI.places_updated.disconnect(_on_places)


func _on_places(places: Array) -> void:
    _count_label.text = "Places (%d)" % places.size()
    for child in _place_list.get_children():
        child.queue_free()
    for raw in places:
        if not raw is Dictionary:
            push_warning("Places: skipping non-Dictionary entry: %s" % str(raw))
            continue
        _place_list.add_child(_make_card(raw as Dictionary))


func _make_card(place: Dictionary) -> Control:
    var unlocked: bool = place.get("state", "LOCKED") == "UNLOCKED"

    var hbox := HBoxContainer.new()

    var dot := ColorRect.new()
    dot.custom_minimum_size = Vector2(14, 14)
    dot.color = _COLOR_UNLOCKED if unlocked else _COLOR_LOCKED

    var name_lbl := Label.new()
    name_lbl.text = place.get("name", place.get("place_id", "?"))
    name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

    var state_lbl := Label.new()
    state_lbl.text = "Unlocked" if unlocked else "Locked"
    state_lbl.modulate = _COLOR_UNLOCKED if unlocked else _COLOR_LOCKED

    var type_lbl := Label.new()
    type_lbl.text = str(place.get("place_type", "")).capitalize()

    var pool = place.get("item_pool", {})
    var cats = pool.get("allowed_categories", null) if pool is Dictionary else null
    var cats_lbl := Label.new()
    if cats is Array and (cats as Array).size() > 0:
        cats_lbl.text = " · ".join((cats as Array).map(
            func(c: Variant) -> String: return str(c).capitalize()
        ))
    else:
        cats_lbl.text = "All categories"

    hbox.add_child(dot)
    hbox.add_child(name_lbl)
    hbox.add_child(state_lbl)
    hbox.add_child(type_lbl)
    hbox.add_child(cats_lbl)
    return hbox
