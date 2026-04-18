# game-client/scenes/RecipeBrowser.gd
extends Control

@onready var _list:       VBoxContainer = $VBox/Scroll/List
@onready var _status_lbl: Label         = $VBox/StatusLabel

const _COLOR_CAN_CRAFT   := Color(0.3, 0.9, 0.3)
const _COLOR_CANT_CRAFT  := Color(0.55, 0.55, 0.55)
const _COLOR_CATEGORY    := Color(1.0, 0.85, 0.3)
const _COLOR_PARTIAL     := Color(1.0, 0.75, 0.2)

const _RARITY_COLOR := {
	"COMMON":    Color(0.75, 0.75, 0.75),
	"UNCOMMON":  Color(0.40, 0.85, 0.40),
	"RARE":      Color(0.30, 0.60, 1.00),
	"EPIC":      Color(0.75, 0.35, 1.00),
	"LEGENDARY": Color(1.00, 0.65, 0.10),
}

const _RARITY_ORDER := ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]


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

	# Group by category → { from_rarity: entry }
	var by_cat: Dictionary = {}
	for raw in recipes:
		if not raw is Dictionary:
			continue
		var entry := raw as Dictionary
		var cat: String   = entry.get("category", "?")
		var from_r: String = entry.get("from_rarity", "?")
		if not by_cat.has(cat):
			by_cat[cat] = {}
		(by_cat[cat] as Dictionary)[from_r] = entry

	for cat in by_cat:
		var cat_lbl := Label.new()
		cat_lbl.text = "── %s ──" % cat
		cat_lbl.modulate = _COLOR_CATEGORY
		cat_lbl.add_theme_font_size_override("font_size", 13)
		_list.add_child(cat_lbl)

		var rarity_map: Dictionary = by_cat[cat] as Dictionary
		for r in _RARITY_ORDER:
			if rarity_map.has(r):
				_list.add_child(_make_ladder_rung(rarity_map[r] as Dictionary))

		var sep := HSeparator.new()
		sep.modulate = Color(1, 1, 1, 0.15)
		_list.add_child(sep)


func _make_ladder_rung(entry: Dictionary) -> Control:
	var from_r:    String = entry.get("from_rarity", "?")
	var to_r:      String = entry.get("to_rarity", "")
	var can_craft: bool   = bool(entry.get("can_craft", false))
	var have:      int    = entry.get("have_item_types", 0) as int
	var item_ids:  Array  = entry.get("item_ids", [])
	var need_more: int    = max(0, 2 - have)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)

	# Source rarity badge
	var from_col: Color = _RARITY_COLOR.get(from_r, Color.WHITE)
	var rarity_lbl := Label.new()
	rarity_lbl.text = "[%s]" % from_r
	rarity_lbl.modulate = from_col
	rarity_lbl.add_theme_font_size_override("font_size", 11)
	rarity_lbl.custom_minimum_size.x = 110

	# Arrow + destination rarity (or max-tier marker)
	var arrow_lbl := Label.new()
	arrow_lbl.add_theme_font_size_override("font_size", 11)
	arrow_lbl.custom_minimum_size.x = 110
	if to_r:
		var to_col: Color = _RARITY_COLOR.get(to_r, Color.WHITE)
		arrow_lbl.text = "→ %s" % to_r
		arrow_lbl.modulate = to_col if can_craft else _COLOR_CANT_CRAFT
	else:
		arrow_lbl.text = "★ max tier"
		arrow_lbl.modulate = _RARITY_COLOR.get(from_r, Color.WHITE)

	# Progress status
	var status_lbl := Label.new()
	status_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status_lbl.add_theme_font_size_override("font_size", 10)
	if can_craft:
		status_lbl.text = "%d type%s ready" % [have, "s" if have != 1 else ""]
		status_lbl.modulate = _COLOR_CAN_CRAFT
	elif have > 0:
		status_lbl.text = "%d/%d — need %d more" % [have, 2, need_more]
		status_lbl.modulate = _COLOR_PARTIAL
	else:
		status_lbl.text = "none yet"
		status_lbl.modulate = _COLOR_CANT_CRAFT

	# Craft button (only for non-max tiers)
	var craft_btn := Button.new()
	craft_btn.text = "Craft →"
	craft_btn.add_theme_font_size_override("font_size", 10)
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
	row.add_child(arrow_lbl)
	row.add_child(status_lbl)
	row.add_child(craft_btn)
	return row
