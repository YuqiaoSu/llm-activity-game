# game-client/scenes/Collection.gd
extends Control

@onready var _list: VBoxContainer = $VBox/Scroll/List
@onready var _count_label: Label  = $VBox/Header/CountLabel

const _RARITY_COLORS := {
	"COMMON":    Color(0.75, 0.75, 0.75),
	"UNCOMMON":  Color(0.25, 0.80, 0.25),
	"RARE":      Color(0.25, 0.55, 1.00),
	"EPIC":      Color(0.65, 0.25, 1.00),
	"LEGENDARY": Color(1.00, 0.65, 0.00),
}


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.collection_updated.connect(_on_collection)
	GameAPI.fetch_collection()


func _exit_tree() -> void:
	if GameAPI.collection_updated.is_connected(_on_collection):
		GameAPI.collection_updated.disconnect(_on_collection)


func _on_collection(entries: Array) -> void:
	var total := entries.size()
	var found := 0
	for raw in entries:
		if raw is Dictionary and (raw as Dictionary).get("discovered", false):
			found += 1
	_count_label.text = "Collection  %d / %d" % [found, total]

	for child in _list.get_children():
		child.queue_free()

	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var discovered: bool = entry.get("discovered", false)
	var rarity: String   = entry.get("rarity", "COMMON")
	var color: Color     = _RARITY_COLORS.get(rarity, Color(0.7, 0.7, 0.7))

	var hbox := HBoxContainer.new()

	# Rarity dot
	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(10, 10)
	dot.color = color if discovered else Color(0.3, 0.3, 0.3)
	dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER

	# Name
	var name_lbl := Label.new()
	if discovered:
		name_lbl.text = entry.get("name", "?")
		name_lbl.modulate = color
	else:
		name_lbl.text = "??? (%s)" % rarity.capitalize()
		name_lbl.modulate = Color(0.45, 0.45, 0.45)
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	# Category badge
	var cat_lbl := Label.new()
	cat_lbl.text = str(entry.get("category", "")).capitalize()
	cat_lbl.custom_minimum_size.x = 60
	cat_lbl.modulate = Color(0.65, 0.65, 0.65) if not discovered else Color(0.85, 0.85, 0.85)
	cat_lbl.add_theme_font_size_override("font_size", 11)

	# First seen date (discovered only)
	if discovered:
		var date_lbl := Label.new()
		var ts: String = entry.get("first_seen_at", "")
		date_lbl.text = ts.left(10) if ts.length() >= 10 else ""
		date_lbl.modulate = Color(0.55, 0.55, 0.55)
		date_lbl.add_theme_font_size_override("font_size", 10)
		date_lbl.custom_minimum_size.x = 80
		hbox.add_child(dot)
		hbox.add_child(name_lbl)
		hbox.add_child(cat_lbl)
		hbox.add_child(date_lbl)
	else:
		hbox.add_child(dot)
		hbox.add_child(name_lbl)
		hbox.add_child(cat_lbl)

	return hbox
