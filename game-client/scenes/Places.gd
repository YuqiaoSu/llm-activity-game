# game-client/scenes/Places.gd
extends Control

@onready var _count_label: Label        = $VBox/Header/CountLabel
@onready var _place_list: VBoxContainer = $VBox/Scroll/PlaceList

const _COLOR_UNLOCKED := Color(0.3, 0.8, 0.3)
const _COLOR_LOCKED   := Color(0.5, 0.5, 0.5)
const _COLOR_SLOT_EMPTY  := Color(0.55, 0.55, 0.55)
const _COLOR_SLOT_FILLED := Color(0.9, 0.75, 0.2)

# Inventory cache keyed by item_id — populated when first needed
var _inventory: Array[Dictionary] = []
var _leaderboard_container: VBoxContainer = null


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.places_updated.connect(_on_places)
	GameAPI.inventory_updated.connect(_on_inventory_cache)
	GameAPI.slot_assigned.connect(_on_slot_assigned)
	GameAPI.place_leaderboard_updated.connect(_on_place_leaderboard)
	GameAPI.fetch_places()
	GameAPI.fetch_place_leaderboard()
	# Pre-load inventory so the slot picker is ready without a round-trip delay
	GameAPI.fetch_inventory()


func _exit_tree() -> void:
	if GameAPI.places_updated.is_connected(_on_places):
		GameAPI.places_updated.disconnect(_on_places)
	if GameAPI.inventory_updated.is_connected(_on_inventory_cache):
		GameAPI.inventory_updated.disconnect(_on_inventory_cache)
	if GameAPI.slot_assigned.is_connected(_on_slot_assigned):
		GameAPI.slot_assigned.disconnect(_on_slot_assigned)
	if GameAPI.place_leaderboard_updated.is_connected(_on_place_leaderboard):
		GameAPI.place_leaderboard_updated.disconnect(_on_place_leaderboard)


func _on_inventory_cache(items: Array) -> void:
	_inventory = []
	for raw in items:
		if raw is Dictionary:
			_inventory.append(raw as Dictionary)


func _on_slot_assigned(_place: Dictionary) -> void:
	# Refresh both places and inventory after any slot change
	GameAPI.fetch_places()
	GameAPI.fetch_inventory()


func _on_places(places: Array) -> void:
	_count_label.text = "Places (%d)" % places.size()
	for child in _place_list.get_children():
		child.queue_free()
	for raw in places:
		if not raw is Dictionary:
			push_warning("Places: skipping non-Dictionary entry: %s" % str(raw))
			continue
		_place_list.add_child(_make_card(raw as Dictionary))


func _on_place_leaderboard(entries: Array) -> void:
	# Remove old leaderboard section if present
	if _leaderboard_container != null and is_instance_valid(_leaderboard_container):
		_leaderboard_container.queue_free()
		_leaderboard_container = null

	if entries.is_empty():
		return

	var section := VBoxContainer.new()
	_leaderboard_container = section

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.15)
	section.add_child(sep)

	var header := Label.new()
	header.text = "Top Places"
	header.add_theme_font_size_override("font_size", 13)
	header.modulate = Color(0.85, 0.85, 0.85)
	section.add_child(header)

	var max_xp: int = 1
	for raw in entries:
		var xp: int = (raw as Dictionary).get("xp", 0) as int
		if xp > max_xp:
			max_xp = xp

	for raw in entries:
		if not raw is Dictionary:
			continue
		var entry := raw as Dictionary
		var rank: int  = entry.get("rank", 0) as int
		var name_: String = entry.get("name", "?")
		var level: int = entry.get("level", 1) as int
		var xp: int    = entry.get("xp", 0) as int

		var hbox := HBoxContainer.new()

		var rank_lbl := Label.new()
		rank_lbl.text = "#%d" % rank
		rank_lbl.custom_minimum_size.x = 24
		rank_lbl.modulate = Color(1.0, 0.84, 0.0) if rank == 1 else Color(0.75, 0.75, 0.75)

		var name_lbl := Label.new()
		name_lbl.text = "%s  Lv.%d" % [name_, level]
		name_lbl.custom_minimum_size.x = 120

		var bar_bg := ColorRect.new()
		bar_bg.custom_minimum_size = Vector2(80, 10)
		bar_bg.color = Color(0.2, 0.2, 0.2)

		var bar_fill := ColorRect.new()
		var fill_w: float = max(2.0, float(xp) / float(max_xp) * 80.0)
		bar_fill.custom_minimum_size = Vector2(fill_w, 10)
		bar_fill.color = Color(0.30, 0.65, 1.00)

		var xp_lbl := Label.new()
		xp_lbl.text = "  %d XP" % xp
		xp_lbl.modulate = Color(0.6, 0.8, 1.0)
		xp_lbl.add_theme_font_size_override("font_size", 11)

		var bar_h := HBoxContainer.new()
		bar_h.add_child(bar_fill)
		bar_bg.add_child(bar_h)

		hbox.add_child(rank_lbl)
		hbox.add_child(name_lbl)
		hbox.add_child(bar_bg)
		hbox.add_child(xp_lbl)
		section.add_child(hbox)

	_place_list.add_child(section)


func _make_card(place: Dictionary) -> Control:
	var unlocked: bool = place.get("state", "LOCKED") == "UNLOCKED"

	var vbox := VBoxContainer.new()

	# ── header row ──────────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(14, 14)
	dot.color = _COLOR_UNLOCKED if unlocked else _COLOR_LOCKED

	var name_lbl := Label.new()
	name_lbl.text = place.get("name", place.get("place_id", "?"))
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var state_lbl := Label.new()
	if unlocked:
		state_lbl.text = "Unlocked"
		state_lbl.modulate = _COLOR_UNLOCKED
	else:
		var cond = place.get("unlock_condition", null)
		if cond is Dictionary:
			var ctype: String = (cond as Dictionary).get("condition_type", "")
			var params: Dictionary = (cond as Dictionary).get("params", {}) as Dictionary
			match ctype:
				"player_level":
					state_lbl.text = "Locked · Level %d required" % params.get("min_level", "?")
				_:
					state_lbl.text = "Locked"
		else:
			state_lbl.text = "Locked"
		state_lbl.modulate = _COLOR_LOCKED

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
	vbox.add_child(hbox)

	# ── set bonus badge ──────────────────────────────────────────────────────
	if place.get("set_bonus_active", false):
		var bonus_lbl := Label.new()
		var factor: float = place.get("set_bonus_factor", 1.25)
		bonus_lbl.text = "  ★ Set Bonus active: %.2f× XP" % factor
		bonus_lbl.modulate = Color(1.0, 0.85, 0.1)   # gold
		bonus_lbl.add_theme_font_size_override("font_size", 11)
		vbox.add_child(bonus_lbl)

	# ── place level / XP (only for unlocked places) ─────────────────────────
	if unlocked:
		var place_level: int  = place.get("level", 1) as int
		var place_xp: int     = place.get("xp", 0) as int
		var next_threshold: int = place_level * place_level * 50  # (level)^2 × 50
		var lvl_lbl := Label.new()
		lvl_lbl.text = "  Lv.%d  ·  %d / %d XP" % [place_level, place_xp, next_threshold]
		lvl_lbl.modulate = Color(0.55, 0.85, 1.0)
		lvl_lbl.add_theme_font_size_override("font_size", 10)
		vbox.add_child(lvl_lbl)

	# ── donated perks (only for unlocked places that have received donations) ──
	if unlocked:
		var perks: Array = place.get("perks", [])
		if perks.size() > 0:
			var perk_hdr := Label.new()
			perk_hdr.text = "  Perks:"
			perk_hdr.modulate = Color(1.0, 0.8, 0.3)   # amber
			perk_hdr.add_theme_font_size_override("font_size", 10)
			vbox.add_child(perk_hdr)
			for raw_perk in perks:
				if not raw_perk is Dictionary:
					continue
				var perk := raw_perk as Dictionary
				var pname: String  = perk.get("item_name", perk.get("item_id", "?"))
				var prarity: String = str(perk.get("item_rarity", "")).capitalize()
				var boost: float   = float(perk.get("boost_factor", 0.10)) * 100.0
				var perk_lbl := Label.new()
				perk_lbl.text = "    🎁 %s [%s] · +%.0f%% XP" % [pname, prarity, boost]
				perk_lbl.modulate = Color(1.0, 0.85, 0.5)
				perk_lbl.add_theme_font_size_override("font_size", 10)
				vbox.add_child(perk_lbl)

	# ── slot rows (only for unlocked places with slots) ─────────────────────
	var slots: Array = place.get("slots", [])
	if unlocked and slots.size() > 0:
		var sep := HSeparator.new()
		sep.modulate = Color(1, 1, 1, 0.15)
		vbox.add_child(sep)
		for raw_slot in slots:
			if raw_slot is Dictionary:
				vbox.add_child(_make_slot_row(place, raw_slot as Dictionary))

	# ── separator at card bottom ─────────────────────────────────────────────
	var bottom_sep := HSeparator.new()
	vbox.add_child(bottom_sep)
	return vbox


func _make_slot_row(place: Dictionary, slot: Dictionary) -> Control:
	var place_id: String = place.get("place_id", "")
	var slot_id: String  = slot.get("slot_id", "")
	var occupant_id      = slot.get("occupant_id", null)  # Variant: String or null

	var row := VBoxContainer.new()

	# ── slot header ──────────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(10, 10)
	dot.color = _COLOR_SLOT_FILLED if occupant_id != null else _COLOR_SLOT_EMPTY

	var slot_lbl := Label.new()
	slot_lbl.text = "  Slot [%s]" % str(slot.get("slot_type", "ITEM")).capitalize()
	slot_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var occupant_lbl := Label.new()
	if occupant_id != null:
		var oname    = slot.get("occupant_name", null)
		var orarity  = str(slot.get("occupant_rarity", ""))
		var name_str: String = str(oname) if oname != null else "(item %s)" % str(occupant_id).left(8)
		occupant_lbl.text = "%s [%s]" % [name_str, orarity.capitalize()] if orarity != "" else name_str
		occupant_lbl.modulate = RarityColor.for_rarity(orarity)
	else:
		occupant_lbl.text = "(empty)"
		occupant_lbl.modulate = _COLOR_SLOT_EMPTY

	hbox.add_child(dot)
	hbox.add_child(slot_lbl)
	hbox.add_child(occupant_lbl)

	# Theme match badge
	if occupant_id != null and slot.get("occupant_matches_theme", false):
		var theme_lbl := Label.new()
		theme_lbl.text = "  ✓ Theme"
		theme_lbl.modulate = Color(0.3, 1.0, 0.5)
		theme_lbl.add_theme_font_size_override("font_size", 10)
		hbox.add_child(theme_lbl)

	# Accepts hint for empty filtered slots
	var accepts_raw = slot.get("accepts", null)
	if occupant_id == null and accepts_raw is Array and (accepts_raw as Array).size() > 0:
		var hint_lbl := Label.new()
		hint_lbl.text = "  [%s]" % ", ".join((accepts_raw as Array).map(
			func(c: Variant) -> String: return str(c).capitalize()
		))
		hint_lbl.modulate = Color(0.6, 0.85, 1.0)
		hint_lbl.add_theme_font_size_override("font_size", 10)
		hbox.add_child(hint_lbl)

	row.add_child(hbox)

	# ── action buttons ───────────────────────────────────────────────────────
	var btn_row := HBoxContainer.new()

	if occupant_id != null:
		var remove_btn := Button.new()
		remove_btn.text = "Remove"
		remove_btn.pressed.connect(func() -> void:
			GameAPI.assign_slot(place_id, slot_id, null)
		)
		btn_row.add_child(remove_btn)
	else:
		var assign_btn := Button.new()
		assign_btn.text = "Assign Item ▾"
		var slot_accepts: Array = []
		var accepts_raw = slot.get("accepts", null)
		if accepts_raw is Array:
			for a in accepts_raw as Array:
				slot_accepts.append(str(a).to_upper())
		# picker_box is created lazily and toggled on button press
		var picker_box := VBoxContainer.new()
		picker_box.visible = false
		assign_btn.pressed.connect(func() -> void:
			picker_box.visible = not picker_box.visible
			if picker_box.visible:
				_populate_picker(picker_box, place_id, slot_id, slot_accepts)
		)
		btn_row.add_child(assign_btn)
		row.add_child(btn_row)
		row.add_child(picker_box)
		return row

	row.add_child(btn_row)
	return row


func _populate_picker(picker: VBoxContainer, place_id: String, slot_id: String, slot_accepts: Array = []) -> void:
	for child in picker.get_children():
		child.queue_free()

	if _inventory.is_empty():
		var lbl := Label.new()
		lbl.text = "  (inventory empty)"
		picker.add_child(lbl)
		return

	var added := 0
	for item in _inventory:
		var iid = item.get("available_instance_id", null)
		if iid == null:
			continue  # all copies are already placed

		# Filter by slot's accepted categories
		if slot_accepts.size() > 0:
			var item_cat: String = str(item.get("category", "")).to_upper()
			if item_cat not in slot_accepts:
				continue

		var effects: Array = item.get("effects", [])
		var effect_summary := _format_effects(effects)
		var btn := Button.new()
		var label_text: String = "  %s [%s]" % [
			item.get("name", item.get("item_id", "?")),
			item.get("rarity", "?")
		]
		if effect_summary != "":
			label_text += "  · " + effect_summary
		btn.text = label_text
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		var instance_id: String = str(iid)
		btn.pressed.connect(func() -> void:
			GameAPI.assign_slot(place_id, slot_id, instance_id)
			picker.visible = false
		)
		picker.add_child(btn)
		added += 1

	if added == 0:
		var lbl := Label.new()
		if slot_accepts.size() > 0:
			lbl.text = "  (no matching items — need: %s)" % ", ".join(slot_accepts.map(
				func(c: Variant) -> String: return str(c).capitalize()
			))
		else:
			lbl.text = "  (no unplaced items available)"
		picker.add_child(lbl)


func _format_effects(effects: Array) -> String:
	var parts: Array[String] = []
	for eff in effects:
		if not eff is Dictionary:
			continue
		match (eff as Dictionary).get("effect_type", ""):
			"xp_multiplier":
				var f: float = (eff as Dictionary).get("params", {}).get("factor", 1.0)
				parts.append("%.1f× XP" % f)
			"drop_weight_mod":
				var p: Dictionary = (eff as Dictionary).get("params", {})
				var f: float = p.get("factor", 1.0)
				var r: String = str(p.get("rarity", "?"))
				parts.append("%.1f× %s drops" % [f, r.capitalize()])
	return ", ".join(parts)
