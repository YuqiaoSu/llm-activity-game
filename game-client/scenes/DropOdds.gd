# game-client/scenes/DropOdds.gd
extends Control

@onready var _picker: OptionButton    = $VBox/CategoryPicker
@onready var _list:   VBoxContainer   = $VBox/Scroll/List

const _CATEGORIES := ["WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"]

const _RARITY_COLORS := {
	"COMMON":    Color(0.75, 0.75, 0.75),
	"UNCOMMON":  Color(0.30, 0.80, 0.30),
	"RARE":      Color(0.25, 0.55, 1.00),
	"EPIC":      Color(0.75, 0.30, 1.00),
	"LEGENDARY": Color(1.00, 0.70, 0.10),
}
const _COLOR_DIM := Color(0.50, 0.50, 0.50)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Inventory.tscn")
	)
	for cat in _CATEGORIES:
		_picker.add_item(cat.capitalize())
	_picker.item_selected.connect(_on_category_selected)
	GameAPI.drop_odds_updated.connect(_on_odds)
	_fetch_current()


func _exit_tree() -> void:
	if GameAPI.drop_odds_updated.is_connected(_on_odds):
		GameAPI.drop_odds_updated.disconnect(_on_odds)


func _fetch_current() -> void:
	var cat := _CATEGORIES[_picker.selected]
	GameAPI.fetch_drop_odds(cat)


func _on_category_selected(_idx: int) -> void:
	_fetch_current()


func _on_odds(entries: Array) -> void:
	for child in _list.get_children():
		child.queue_free()

	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "No items in this category."
		lbl.modulate = _COLOR_DIM
		_list.add_child(lbl)
		return

	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var rarity: String  = entry.get("rarity", "COMMON")
	var name: String    = entry.get("name", entry.get("item_id", "?"))
	var pct: float      = float(entry.get("probability_pct", 0.0))
	var col: Color      = _RARITY_COLORS.get(rarity, _COLOR_DIM)

	var vbox := VBoxContainer.new()

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)

	var rarity_lbl := Label.new()
	rarity_lbl.text = "[%s]" % rarity
	rarity_lbl.modulate = col
	rarity_lbl.custom_minimum_size.x = 90
	rarity_lbl.add_theme_font_size_override("font_size", 10)

	var name_lbl := Label.new()
	name_lbl.text = name
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.modulate = col

	var pct_lbl := Label.new()
	pct_lbl.text = "%.2f%%" % pct
	pct_lbl.modulate = Color.WHITE
	pct_lbl.add_theme_font_size_override("font_size", 11)

	var bar := ProgressBar.new()
	bar.max_value = 100.0
	bar.value = pct
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(0, 6)
	bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	row.add_child(rarity_lbl)
	row.add_child(name_lbl)
	row.add_child(pct_lbl)
	vbox.add_child(row)
	vbox.add_child(bar)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.08)
	vbox.add_child(sep)

	return vbox
