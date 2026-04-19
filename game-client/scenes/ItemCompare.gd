# game-client/scenes/ItemCompare.gd
# Side-by-side item comparison screen. Items passed via GameAPI.compare_items.
extends Control

const RarityColor := preload("res://utils/RarityColor.gd")

@onready var _panel_a: VBoxContainer = $VBox/Panels/PanelA
@onready var _panel_b: VBoxContainer = $VBox/Panels/PanelB

const _COLOR_BETTER  := Color(0.30, 0.90, 0.30)
const _COLOR_WORSE   := Color(0.90, 0.40, 0.40)
const _COLOR_EQUAL   := Color(0.65, 0.65, 0.65)
const _COLOR_MUTED   := Color(0.50, 0.50, 0.50)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Inventory.tscn")
	)

	var items: Array = GameAPI.compare_items
	if items.size() < 2:
		var lbl := Label.new()
		lbl.text = "Select two items from Inventory to compare."
		lbl.modulate = _COLOR_MUTED
		_panel_a.add_child(lbl)
		return

	_build_panel(_panel_a, items[0] as Dictionary, items[1] as Dictionary)
	_build_panel(_panel_b, items[1] as Dictionary, items[0] as Dictionary)


func _build_panel(panel: VBoxContainer, item: Dictionary, other: Dictionary) -> void:
	# ── Name + rarity ────────────────────────────────────────────────────────
	var name_lbl := Label.new()
	name_lbl.text = item.get("name", item.get("item_id", "?"))
	name_lbl.modulate = RarityColor.for_rarity(item.get("rarity", "COMMON"))
	name_lbl.add_theme_font_size_override("font_size", 14)
	panel.add_child(name_lbl)

	var rarity_lbl := Label.new()
	rarity_lbl.text = str(item.get("rarity", "COMMON")).capitalize()
	rarity_lbl.modulate = RarityColor.for_rarity(item.get("rarity", "COMMON"))
	rarity_lbl.add_theme_font_size_override("font_size", 11)
	panel.add_child(rarity_lbl)

	var cat_lbl := Label.new()
	cat_lbl.text = str(item.get("category", "—")).capitalize()
	cat_lbl.modulate = _COLOR_MUTED
	cat_lbl.add_theme_font_size_override("font_size", 11)
	panel.add_child(cat_lbl)

	# ── Description ──────────────────────────────────────────────────────────
	var desc: String = item.get("description", "")
	if not desc.is_empty():
		var desc_lbl := Label.new()
		desc_lbl.text = desc
		desc_lbl.modulate = Color(0.75, 0.75, 0.75)
		desc_lbl.add_theme_font_size_override("font_size", 10)
		desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		panel.add_child(desc_lbl)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.15)
	panel.add_child(sep)

	# ── Effects ──────────────────────────────────────────────────────────────
	var my_effects: Array  = item.get("effects", [])
	var otr_effects: Array = other.get("effects", [])

	if my_effects.is_empty():
		var no_eff := Label.new()
		no_eff.text = "No effects"
		no_eff.modulate = _COLOR_MUTED
		no_eff.add_theme_font_size_override("font_size", 11)
		panel.add_child(no_eff)
		return

	for eff_raw in my_effects:
		if not eff_raw is Dictionary:
			continue
		var eff := eff_raw as Dictionary
		var etype: String  = eff.get("effect_type", "")
		var params: Dictionary = eff.get("params", {}) as Dictionary
		var my_factor: float   = float(params.get("factor", 0.0))

		# Look for a matching effect in the other item
		var other_factor: float = 0.0
		for oeff_raw in otr_effects:
			if oeff_raw is Dictionary:
				var oeff := oeff_raw as Dictionary
				if oeff.get("effect_type", "") == etype:
					other_factor = float((oeff.get("params", {}) as Dictionary).get("factor", 0.0))
					break

		var arrow: String = "="
		var col := _COLOR_EQUAL
		if my_factor > other_factor:
			arrow = "▲"
			col = _COLOR_BETTER
		elif my_factor < other_factor:
			arrow = "▼"
			col = _COLOR_WORSE

		var row_lbl := Label.new()
		row_lbl.text = "%s %s" % [arrow, _format_effect(etype, params)]
		row_lbl.modulate = col
		row_lbl.add_theme_font_size_override("font_size", 11)
		panel.add_child(row_lbl)


func _format_effect(effect_type: String, params: Dictionary) -> String:
	match effect_type:
		"xp_multiplier":
			return "%.0f%% XP boost" % ((params.get("factor", 1.0) - 1.0) * 100.0)
		"drop_weight_mod":
			var r: String = str(params.get("rarity", "?")).capitalize()
			return "%.0f%% %s drop chance" % [(params.get("factor", 1.0) - 1.0) * 100.0, r]
		"category_xp_bonus":
			var cat: String = str(params.get("category", "?")).capitalize()
			return "%.0f%% %s XP" % [(params.get("factor", 1.0) - 1.0) * 100.0, cat]
		"extra_roll":
			return "+%d drop roll" % int(params.get("rolls", 1))
		_:
			return effect_type
