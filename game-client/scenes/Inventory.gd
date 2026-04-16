# game-client/scenes/Inventory.gd
extends Control

const RarityColor := preload("res://utils/RarityColor.gd")

@onready var _count_label: Label       = $VBox/Header/CountLabel
@onready var _item_list: VBoxContainer = $VBox/Scroll/ItemList

# Craft-mode state
var _craft_slot_a: Dictionary = {}   # item dict for first craft selection
var _craft_slot_b: Dictionary = {}   # item dict for second craft selection
var _craft_panel: VBoxContainer      # created dynamically; shown when a slot is filled

var _items_cache: Array  = []        # last received inventory array
var _places_cache: Array = []        # last received places array (for quick-assign)

# Filter / sort state
const _RARITY_ORDER := ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
var _filter_category: String = ""    # "" = all
var _filter_rarity: String   = ""    # "" = all
var _filter_search: String   = ""    # "" = all; substring match on name/item_id
var _sort_mode: String       = "name"  # "name" | "rarity" | "quantity"

# Filter/sort row (created once in _ready)
var _filter_row: HBoxContainer


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.inventory_updated.connect(_on_inventory)
	GameAPI.equip_updated.connect(_on_equip_updated)
	GameAPI.item_discarded.connect(_on_item_discarded)
	GameAPI.fuse_completed.connect(_on_fuse_completed)
	GameAPI.craft_completed.connect(_on_craft_completed)
	GameAPI.places_updated.connect(_on_places)
	GameAPI.slot_assigned.connect(_on_slot_assigned)

	# Build filter/sort row and insert it between the header and scroll area
	_filter_row = _make_filter_row()
	var vbox: VBoxContainer = $VBox
	# Insert after index 0 (Header) and before the Scroll
	vbox.add_child(_filter_row)
	vbox.move_child(_filter_row, 1)

	GameAPI.fetch_inventory()
	GameAPI.fetch_places()  # needed for quick-assign slot picker


func _exit_tree() -> void:
	if GameAPI.inventory_updated.is_connected(_on_inventory):
		GameAPI.inventory_updated.disconnect(_on_inventory)
	if GameAPI.equip_updated.is_connected(_on_equip_updated):
		GameAPI.equip_updated.disconnect(_on_equip_updated)
	if GameAPI.item_discarded.is_connected(_on_item_discarded):
		GameAPI.item_discarded.disconnect(_on_item_discarded)
	if GameAPI.fuse_completed.is_connected(_on_fuse_completed):
		GameAPI.fuse_completed.disconnect(_on_fuse_completed)
	if GameAPI.craft_completed.is_connected(_on_craft_completed):
		GameAPI.craft_completed.disconnect(_on_craft_completed)
	if GameAPI.places_updated.is_connected(_on_places):
		GameAPI.places_updated.disconnect(_on_places)
	if GameAPI.slot_assigned.is_connected(_on_slot_assigned):
		GameAPI.slot_assigned.disconnect(_on_slot_assigned)


func _on_equip_updated(_item_id: String, _equipped: bool) -> void:
	GameAPI.fetch_inventory()


func _on_item_discarded(_instance_id: String) -> void:
	GameAPI.fetch_inventory()


func _on_fuse_completed(_ok: bool, _data: Dictionary) -> void:
	GameAPI.fetch_inventory()


func _on_craft_completed(ok: bool, _data: Dictionary) -> void:
	_craft_slot_a = {}
	_craft_slot_b = {}
	if ok:
		GameAPI.fetch_inventory()
	else:
		_rebuild_list(_items_cache)


func _on_places(places: Array) -> void:
	_places_cache = places
	_rebuild_list(_items_cache)  # slot pickers may need updating


func _on_slot_assigned(_place: Dictionary) -> void:
	# Refresh both to reflect occupant changes
	GameAPI.fetch_inventory()
	GameAPI.fetch_places()


func _on_inventory(items: Array) -> void:
	_items_cache = items
	_count_label.text = "Inventory (%d)" % items.size()
	_rebuild_list(items)


func _available_slots_for(item_category: String) -> Array:
	"""Return list of {label, place_id, slot_id} for unlocked slots that accept this category."""
	var result: Array = []
	var cat_upper: String = item_category.to_upper()
	for raw_place in _places_cache:
		if not raw_place is Dictionary:
			continue
		var place := raw_place as Dictionary
		# Only UNLOCKED places
		if place.get("state", "") != "UNLOCKED":
			continue
		var pname: String = place.get("name", place.get("place_id", "?"))
		var pid: String   = place.get("place_id", "")
		for raw_slot in place.get("slots", []):
			if not raw_slot is Dictionary:
				continue
			var slot := raw_slot as Dictionary
			# Skip occupied slots
			if slot.get("occupant_id") != null:
				continue
			var sid: String = slot.get("slot_id", "")
			# Check category filter
			var accepts = slot.get("accepts")
			var accepted: bool = true
			if accepts is Array and accepts.size() > 0:
				accepted = false
				for a in accepts:
					if str(a).to_upper() == cat_upper:
						accepted = true
						break
			if accepted:
				result.append({"label": "%s · %s" % [pname, sid], "place_id": pid, "slot_id": sid})
	return result


func _make_filter_row() -> HBoxContainer:
	var row := HBoxContainer.new()

	# Search box
	var search := LineEdit.new()
	search.placeholder_text = "Search…"
	search.custom_minimum_size.x = 80
	search.add_theme_font_size_override("font_size", 11)
	search.text_changed.connect(func(t: String) -> void:
		_filter_search = t.strip_edges().to_lower()
		_rebuild_list(_items_cache)
	)
	row.add_child(search)

	var cat_label := Label.new()
	cat_label.text = "  Cat:"
	cat_label.add_theme_font_size_override("font_size", 11)
	row.add_child(cat_label)

	var cat_opt := OptionButton.new()
	cat_opt.add_item("All")
	for c in ["focus", "rest", "social", "creative", "exercise", "learning"]:
		cat_opt.add_item(c.capitalize())
	cat_opt.item_selected.connect(func(idx: int) -> void:
		_filter_category = "" if idx == 0 else ["focus","rest","social","creative","exercise","learning"][idx - 1]
		_rebuild_list(_items_cache)
	)
	row.add_child(cat_opt)

	var rar_label := Label.new()
	rar_label.text = "  Rarity:"
	rar_label.add_theme_font_size_override("font_size", 11)
	row.add_child(rar_label)

	var rar_opt := OptionButton.new()
	rar_opt.add_item("All")
	for r in _RARITY_ORDER:
		rar_opt.add_item(r.capitalize())
	rar_opt.item_selected.connect(func(idx: int) -> void:
		_filter_rarity = "" if idx == 0 else _RARITY_ORDER[idx - 1]
		_rebuild_list(_items_cache)
	)
	row.add_child(rar_opt)

	var sort_label := Label.new()
	sort_label.text = "  Sort:"
	sort_label.add_theme_font_size_override("font_size", 11)
	row.add_child(sort_label)

	var sort_opt := OptionButton.new()
	for s in ["Name", "Rarity", "Qty"]:
		sort_opt.add_item(s)
	sort_opt.item_selected.connect(func(idx: int) -> void:
		_sort_mode = ["name", "rarity", "quantity"][idx]
		_rebuild_list(_items_cache)
	)
	row.add_child(sort_opt)

	return row


func _apply_filter_sort(items: Array) -> Array:
	var result: Array = []
	for raw in items:
		if not raw is Dictionary:
			continue
		var item := raw as Dictionary
		if _filter_category != "" and item.get("category", "") != _filter_category:
			continue
		if _filter_rarity != "" and item.get("rarity", "") != _filter_rarity:
			continue
		if _filter_search != "":
			var name_lower: String = str(item.get("name", item.get("item_id", ""))).to_lower()
			if not name_lower.contains(_filter_search):
				continue
		result.append(item)

	match _sort_mode:
		"name":
			result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
				return a.get("name", a.get("item_id", "")) < b.get("name", b.get("item_id", ""))
			)
		"rarity":
			result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
				var ia: int = _RARITY_ORDER.find(a.get("rarity", "COMMON"))
				var ib: int = _RARITY_ORDER.find(b.get("rarity", "COMMON"))
				return ia > ib   # LEGENDARY first
			)
		"quantity":
			result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
				return a.get("quantity", 1) > b.get("quantity", 1)
			)
	return result


func _rebuild_list(items: Array) -> void:
	for child in _item_list.get_children():
		child.queue_free()
	_craft_panel = null

	# Craft summary panel (shown when at least one slot is filled)
	if not _craft_slot_a.is_empty() or not _craft_slot_b.is_empty():
		_craft_panel = _make_craft_panel()
		_item_list.add_child(_craft_panel)

	var visible_items := _apply_filter_sort(items)
	for item in visible_items:
		_item_list.add_child(_make_card(item))


func _make_craft_panel() -> VBoxContainer:
	var panel := VBoxContainer.new()
	panel.modulate = Color(0.85, 1.0, 0.85)

	var title := Label.new()
	title.text = "Craft"
	title.add_theme_font_size_override("font_size", 13)
	panel.add_child(title)

	var row := HBoxContainer.new()

	var slot_a_lbl := Label.new()
	slot_a_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if _craft_slot_a.is_empty():
		slot_a_lbl.text = "[pick item A]"
		slot_a_lbl.modulate = Color(0.6, 0.6, 0.6)
	else:
		slot_a_lbl.text = _craft_slot_a.get("name", _craft_slot_a.get("item_id", "?"))
		slot_a_lbl.modulate = RarityColor.for_rarity(_craft_slot_a.get("rarity", "COMMON"))
	row.add_child(slot_a_lbl)

	var plus_lbl := Label.new()
	plus_lbl.text = " + "
	row.add_child(plus_lbl)

	var slot_b_lbl := Label.new()
	slot_b_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if _craft_slot_b.is_empty():
		slot_b_lbl.text = "[pick item B]"
		slot_b_lbl.modulate = Color(0.6, 0.6, 0.6)
	else:
		slot_b_lbl.text = _craft_slot_b.get("name", _craft_slot_b.get("item_id", "?"))
		slot_b_lbl.modulate = RarityColor.for_rarity(_craft_slot_b.get("rarity", "COMMON"))
	row.add_child(slot_b_lbl)

	panel.add_child(row)

	var btn_row := HBoxContainer.new()

	# Craft button — active only when both slots are filled
	if not _craft_slot_a.is_empty() and not _craft_slot_b.is_empty():
		var craft_btn := Button.new()
		craft_btn.text = "Craft!"
		craft_btn.modulate = Color(0.4, 1.0, 0.6)
		craft_btn.pressed.connect(func() -> void:
			GameAPI.craft_items(
				_craft_slot_a.get("item_id", ""),
				_craft_slot_b.get("item_id", ""),
			)
		)
		btn_row.add_child(craft_btn)

	var cancel_btn := Button.new()
	cancel_btn.text = "Cancel"
	cancel_btn.modulate = Color(0.9, 0.5, 0.5)
	cancel_btn.pressed.connect(func() -> void:
		_craft_slot_a = {}
		_craft_slot_b = {}
		_rebuild_list(_items_cache)
	)
	btn_row.add_child(cancel_btn)
	panel.add_child(btn_row)

	return panel


func _select_for_craft(item: Dictionary) -> void:
	var item_id: String = item.get("item_id", "")
	# Deselect if already in a slot
	if _craft_slot_a.get("item_id", "") == item_id:
		_craft_slot_a = {}
		_rebuild_list(_items_cache)
		return
	if _craft_slot_b.get("item_id", "") == item_id:
		_craft_slot_b = {}
		_rebuild_list(_items_cache)
		return
	# Fill first empty slot
	if _craft_slot_a.is_empty():
		_craft_slot_a = item
	elif _craft_slot_b.is_empty():
		_craft_slot_b = item
	else:
		# Both filled — replace slot A
		_craft_slot_a = item
	_rebuild_list(_items_cache)


func _make_card(item: Dictionary) -> Control:
	var vbox := VBoxContainer.new()

	# ── main row ─────────────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(14, 14)
	dot.color = RarityColor.for_rarity(item.get("rarity", "COMMON"))

	# Name button toggles the detail panel
	var name_btn := Button.new()
	name_btn.text = item.get("name", item.get("item_id", "?"))
	name_btn.flat = true
	name_btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	name_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var qty: int = item.get("quantity", 1)
	var qty_lbl := Label.new()
	qty_lbl.text = "×%d" % qty if qty > 1 else ""

	var cat_lbl := Label.new()
	cat_lbl.text = str(item.get("category", "")).capitalize()

	var equipped: bool = item.get("equipped", false)
	var equip_btn := Button.new()
	equip_btn.text = "Unequip" if equipped else "Equip"
	var item_id: String = item.get("item_id", "")
	equip_btn.pressed.connect(func() -> void:
		GameAPI.equip_item(item_id, not equipped)
	)

	hbox.add_child(dot)
	hbox.add_child(name_btn)
	hbox.add_child(qty_lbl)
	hbox.add_child(cat_lbl)
	hbox.add_child(equip_btn)

	# Discard button — only when an unplaced copy exists
	var avail_iid = item.get("available_instance_id", null)
	if avail_iid != null:
		var discard_btn := Button.new()
		discard_btn.text = "Discard"
		discard_btn.modulate = Color(0.9, 0.4, 0.4)
		var iid: String = str(avail_iid)
		discard_btn.pressed.connect(func() -> void:
			GameAPI.discard_item(iid)
		)
		hbox.add_child(discard_btn)

	# Fuse button — 3× same rarity → 1× next rarity (not available for LEGENDARY)
	var rarity: String = item.get("rarity", "")
	if qty >= 3 and rarity != "LEGENDARY" and rarity != "":
		var fuse_btn := Button.new()
		fuse_btn.text = "Fuse 3×"
		fuse_btn.modulate = Color(0.6, 0.85, 1.0)   # light blue
		var fuse_item_id: String = item_id
		fuse_btn.pressed.connect(func() -> void:
			GameAPI.fuse_item(fuse_item_id)
		)
		hbox.add_child(fuse_btn)

	# Craft button — select this item for combining with another of the same category
	var in_slot_a: bool = _craft_slot_a.get("item_id", "") == item_id
	var in_slot_b: bool = _craft_slot_b.get("item_id", "") == item_id
	var craft_sel_btn := Button.new()
	if in_slot_a or in_slot_b:
		craft_sel_btn.text = "Deselect"
		craft_sel_btn.modulate = Color(1.0, 0.8, 0.4)   # amber = selected
	else:
		craft_sel_btn.text = "Craft"
		craft_sel_btn.modulate = Color(0.75, 1.0, 0.55)  # light green
	var craft_item_snapshot := item.duplicate()
	craft_sel_btn.pressed.connect(func() -> void:
		_select_for_craft(craft_item_snapshot)
	)
	hbox.add_child(craft_sel_btn)

	vbox.add_child(hbox)

	# "Place in…" quick-assign — inline slot list toggled by button in hbox
	# Built after hbox is added so the popup appears below the main row
	if avail_iid != null:
		var iid_str: String = str(avail_iid)
		var cat: String = item.get("category", "")
		var slots := _available_slots_for(cat)
		if slots.size() > 0:
			var place_popup_vbox := VBoxContainer.new()
			place_popup_vbox.visible = false
			for slot_info in slots:
				var slot_btn := Button.new()
				slot_btn.text = slot_info["label"]
				slot_btn.flat  = true
				slot_btn.add_theme_font_size_override("font_size", 10)
				var pid: String = slot_info["place_id"]
				var sid: String = slot_info["slot_id"]
				slot_btn.pressed.connect(func() -> void:
					GameAPI.assign_slot(pid, sid, iid_str)
					place_popup_vbox.visible = false
				)
				place_popup_vbox.add_child(slot_btn)
			vbox.add_child(place_popup_vbox)

			var place_btn := Button.new()
			place_btn.text = "Place in…"
			place_btn.modulate = Color(0.75, 0.6, 1.0)   # lilac
			place_btn.pressed.connect(func() -> void:
				place_popup_vbox.visible = not place_popup_vbox.visible
			)
			hbox.add_child(place_btn)

	# ── effect summary row (only when slot effects present) ───────────────────
	var effects: Array = item.get("effects", [])
	var effect_text := _format_slot_effects(effects)
	if effect_text != "":
		var eff_lbl := Label.new()
		eff_lbl.text = "  ✦ " + effect_text
		eff_lbl.modulate = Color(0.85, 0.75, 0.35)   # warm gold
		eff_lbl.add_theme_font_size_override("font_size", 11)
		vbox.add_child(eff_lbl)

	# ── detail panel (hidden; toggled by name_btn) ───────────────────────────
	var detail := _make_detail_panel(item)
	detail.visible = false
	vbox.add_child(detail)

	name_btn.pressed.connect(func() -> void:
		detail.visible = not detail.visible
		name_btn.modulate = Color(0.75, 0.95, 1.0) if detail.visible else Color.WHITE
	)

	return vbox


func _make_detail_panel(item: Dictionary) -> Control:
	var panel := VBoxContainer.new()
	panel.modulate = Color(0.85, 0.85, 0.85)

	var indent := "    "

	# Description
	var desc: String = item.get("description", "")
	if not desc.is_empty():
		var desc_lbl := Label.new()
		desc_lbl.text = indent + desc
		desc_lbl.add_theme_font_size_override("font_size", 11)
		desc_lbl.modulate = Color(0.85, 0.85, 0.85)
		desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		panel.add_child(desc_lbl)

	# All effects
	var effects: Array = item.get("effects", [])
	for eff_text in _format_all_effects(effects):
		var eff_lbl := Label.new()
		eff_lbl.text = indent + "✦ " + eff_text
		eff_lbl.modulate = Color(0.85, 0.75, 0.35)
		eff_lbl.add_theme_font_size_override("font_size", 11)
		panel.add_child(eff_lbl)

	# First seen
	var first_seen = item.get("first_seen_at", null)
	if first_seen != null:
		var fs_lbl := Label.new()
		var fs_str: String = str(first_seen)
		# Trim to date portion if ISO timestamp
		if fs_str.length() >= 10:
			fs_str = fs_str.left(10)
		fs_lbl.text = indent + "First found: " + fs_str
		fs_lbl.modulate = Color(0.6, 0.6, 0.6)
		fs_lbl.add_theme_font_size_override("font_size", 10)
		panel.add_child(fs_lbl)

	# Rarity + category reminder
	var meta_lbl := Label.new()
	meta_lbl.text = indent + "%s · %s" % [
		str(item.get("rarity", "")).capitalize(),
		str(item.get("category", "")).capitalize(),
	]
	meta_lbl.modulate = Color(0.55, 0.55, 0.55)
	meta_lbl.add_theme_font_size_override("font_size", 10)
	panel.add_child(meta_lbl)

	return panel


func _format_all_effects(effects: Array) -> Array[String]:
	var parts: Array[String] = []
	for raw in effects:
		if not raw is Dictionary:
			continue
		var eff := raw as Dictionary
		var params: Dictionary = eff.get("params", {}) as Dictionary
		match eff.get("effect_type", ""):
			"xp_multiplier":
				parts.append("%.1f× XP (global, when placed)" % params.get("factor", 1.0))
			"drop_weight_mod":
				parts.append("%.1f× %s drop weight (when placed)" % [
					params.get("factor", 1.0),
					str(params.get("rarity", "?")).capitalize(),
				])
			"category_xp_bonus":
				parts.append("%.1f× %s XP (when placed)" % [
					params.get("factor", 1.0),
					str(params.get("category", "?")).capitalize(),
				])
			_:
				var et: String = eff.get("effect_type", "unknown")
				if et != "" and et != "home_unlock":
					parts.append(et)
	return parts


func _format_slot_effects(effects: Array) -> String:
	var parts: Array[String] = []
	for raw in effects:
		if not raw is Dictionary:
			continue
		var eff := raw as Dictionary
		match eff.get("effect_type", ""):
			"xp_multiplier":
				var f: float = eff.get("params", {}).get("factor", 1.0)
				parts.append("%.1f× XP when placed" % f)
			"drop_weight_mod":
				var p: Dictionary = eff.get("params", {})
				var f: float = p.get("factor", 1.0)
				var r: String = str(p.get("rarity", "?")).capitalize()
				parts.append("%.1f× %s drops when placed" % [f, r])
			"category_xp_bonus":
				var p: Dictionary = eff.get("params", {})
				var f: float = p.get("factor", 1.0)
				var c: String = str(p.get("category", "?")).capitalize()
				parts.append("%.1f× %s XP when placed" % [f, c])
	return ", ".join(parts)
