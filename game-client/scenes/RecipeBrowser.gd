# game-client/scenes/RecipeBrowser.gd
extends Control

@onready var _list:       VBoxContainer = $VBox/Scroll/List
@onready var _status_lbl: Label         = $VBox/StatusLabel

const _COLOR_CAN_CRAFT   := Color(0.3, 0.9, 0.3)
const _COLOR_CANT_CRAFT  := Color(0.55, 0.55, 0.55)
const _COLOR_CATEGORY    := Color(1.0, 0.85, 0.3)

const _RARITY_COLOR := {
	"COMMON":    Color(0.75, 0.75, 0.75),
	"UNCOMMON":  Color(0.40, 0.85, 0.40),
	"RARE":      Color(0.30, 0.60, 1.00),
	"EPIC":      Color(0.75, 0.35, 1.00),
	"LEGENDARY": Color(1.00, 0.65, 0.10),
}


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.recipes_updated.connect(_on_recipes)
	GameAPI.craft_completed.connect(_on_craft_result)
	GameAPI.fetch_recipes()


func _exit_tree() -> void:
	if GameAPI.recipes_updated.is_connected(_on_recipes):
		GameAPI.recipes_updated.disconnect(_on_recipes)
	if GameAPI.craft_completed.is_connected(_on_craft_result):
		GameAPI.craft_completed.disconnect(_on_craft_result)


func _on_craft_result(ok: bool, data: Dictionary) -> void:
	if ok:
		var new_item: String = data.get("result_item_id", "?")
		var rarity: String   = data.get("result_rarity", "")
		_status_lbl.text = "✓ Crafted: %s (%s)" % [new_item, rarity]
		_status_lbl.modulate = _COLOR_CAN_CRAFT
	else:
		var detail: String = data.get("detail", "Craft failed")
		_status_lbl.text = "✗ %s" % detail
		_status_lbl.modulate = Color(1.0, 0.4, 0.4)
	# Refresh so can_craft flags update
	GameAPI.fetch_recipes()


func _on_recipes(recipes: Array) -> void:
	for child in _list.get_children():
		child.queue_free()

	if recipes.is_empty():
		var lbl := Label.new()
		lbl.text = "No recipes available. Collect items to unlock crafting."
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD
		_list.add_child(lbl)
		return

	# Group by category
	var by_cat: Dictionary = {}
	for raw in recipes:
		if not raw is Dictionary:
			continue
		var entry := raw as Dictionary
		var cat: String = entry.get("category", "?")
		if not by_cat.has(cat):
			by_cat[cat] = []
		by_cat[cat].append(entry)

	for cat in by_cat:
		var cat_lbl := Label.new()
		cat_lbl.text = "── %s ──" % cat
		cat_lbl.modulate = _COLOR_CATEGORY
		cat_lbl.add_theme_font_size_override("font_size", 13)
		_list.add_child(cat_lbl)

		for entry in by_cat[cat] as Array:
			_list.add_child(_make_recipe_row(entry as Dictionary))

		var sep := HSeparator.new()
		sep.modulate = Color(1, 1, 1, 0.15)
		_list.add_child(sep)


func _make_recipe_row(entry: Dictionary) -> Control:
	var from_r:   String = entry.get("from_rarity", "?")
	var to_r:     String = entry.get("to_rarity", "")
	var can_craft: bool  = bool(entry.get("can_craft", false))
	var have:     int    = entry.get("have_item_types", 0) as int
	var item_ids: Array  = entry.get("item_ids", [])

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)

	# Rarity arrow label
	var from_col: Color = _RARITY_COLOR.get(from_r, Color.WHITE)
	var to_col:   Color = _RARITY_COLOR.get(to_r, Color.WHITE) if to_r else Color.GRAY

	var rarity_lbl := Label.new()
	if to_r:
		rarity_lbl.text = "%s → %s" % [from_r, to_r]
	else:
		rarity_lbl.text = "%s (max)" % from_r
	rarity_lbl.modulate = from_col if can_craft else _COLOR_CANT_CRAFT
	rarity_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	# Availability count
	var have_lbl := Label.new()
	have_lbl.text = "(%d types)" % have
	have_lbl.modulate = _COLOR_CAN_CRAFT if can_craft else _COLOR_CANT_CRAFT
	have_lbl.add_theme_font_size_override("font_size", 10)

	# Craft button
	var craft_btn := Button.new()
	craft_btn.text = "Craft 2×"
	craft_btn.disabled = not can_craft or item_ids.size() < 2 or to_r.is_empty()
	if not craft_btn.disabled:
		var id_a: String = item_ids[0] as String
		var id_b: String = item_ids[1] as String
		craft_btn.pressed.connect(func() -> void:
			_status_lbl.text = "Crafting…"
			_status_lbl.modulate = Color(1, 1, 1)
			GameAPI.craft_items(id_a, id_b)
		)

	row.add_child(rarity_lbl)
	row.add_child(have_lbl)
	row.add_child(craft_btn)
	return row
