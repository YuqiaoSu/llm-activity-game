# game-client/scenes/Inventory.gd
extends Control

const RarityColor := preload("res://utils/RarityColor.gd")

@onready var _count_label: Label       = $VBox/Header/CountLabel
@onready var _item_list: VBoxContainer = $VBox/Scroll/ItemList

# Craft-mode state
var _craft_slot_a: Dictionary = {}   # item dict for first craft selection
var _craft_slot_b: Dictionary = {}   # item dict for second craft selection
var _craft_panel: VBoxContainer      # created dynamically; shown when a slot is filled

# Compare-mode state
var _compare_items: Array = []       # up to 2 item dicts selected for side-by-side compare
var _compare_bar: HBoxContainer      # bar with "Compare →" shown when 2 items picked

var _items_cache: Array  = []        # last received inventory array
var _places_cache: Array = []        # last received places array (for quick-assign)

# Filter / sort state
const _RARITY_ORDER := ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
var _filter_category: String = ""    # "" = all
var _filter_rarity: String   = ""    # "" = all
var _filter_search: String   = ""    # "" = all; substring match on name/item_id
var _filter_favorites: bool  = false # true = show only favorited items
var _filter_tag: String      = ""    # "" = all; server-side tag match
var _sort_mode: String       = "name"  # "name" | "rarity" | "quantity"

# Filter/sort row (created once in _ready)
var _filter_row: HBoxContainer

# Value summary overlay
var _value_overlay: Control = null


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	$VBox/Header/SetsButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/ItemSets.tscn")
	)
	$VBox/Header/DropOddsButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/DropOdds.tscn")
	)

	# "Repair All" button — added dynamically so .tscn doesn't need editing
	var repair_all_btn := Button.new()
	repair_all_btn.text = "Repair All 🔧"
	repair_all_btn.modulate = Color(0.5, 0.9, 1.0)
	repair_all_btn.add_theme_font_size_override("font_size", 10)
	repair_all_btn.pressed.connect(func() -> void:
		GameAPI.bulk_repair_items()
	)
	$VBox/Header.add_child(repair_all_btn)
	GameAPI.bulk_repair_completed.connect(func(d: Dictionary) -> void:
		var msg := "Repaired %d item(s) for %d XP" % [d.get("repaired_count", 0), d.get("total_xp_spent", 0)]
		if d.get("skipped_locked", 0) > 0:
			msg += " (%d locked skipped)" % d.get("skipped_locked", 0)
		repair_all_btn.text = msg
		# Reset label after 3 seconds
		var timer := get_tree().create_timer(3.0)
		timer.timeout.connect(func() -> void: repair_all_btn.text = "Repair All 🔧")
	)

	# "Value Summary" button
	var value_btn := Button.new()
	value_btn.text = "💰 Value"
	value_btn.add_theme_font_size_override("font_size", 10)
	value_btn.pressed.connect(func() -> void:
		GameAPI.fetch_inventory_value_summary()
	)
	$VBox/Header.add_child(value_btn)
	_build_value_overlay()
	GameAPI.inventory_value_summary_updated.connect(_on_value_summary)

	GameAPI.inventory_updated.connect(_on_inventory)
	GameAPI.equip_updated.connect(_on_equip_updated)
	GameAPI.item_discarded.connect(_on_item_discarded)
	GameAPI.fuse_completed.connect(_on_fuse_completed)
	GameAPI.craft_completed.connect(_on_craft_completed)
	GameAPI.places_updated.connect(_on_places)
	GameAPI.slot_assigned.connect(_on_slot_assigned)
	GameAPI.donation_completed.connect(_on_donation_completed)
	GameAPI.item_gifted.connect(func(_d: Dictionary) -> void:
		GameAPI.fetch_inventory()
		GameAPI.fetch_places()
	)
	GameAPI.inventory_note_saved.connect(func(_data: Dictionary) -> void:
		GameAPI.fetch_inventory()
	)

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
	if GameAPI.donation_completed.is_connected(_on_donation_completed):
		GameAPI.donation_completed.disconnect(_on_donation_completed)
	if GameAPI.inventory_value_summary_updated.is_connected(_on_value_summary):
		GameAPI.inventory_value_summary_updated.disconnect(_on_value_summary)
	# inventory_note_saved: connected via anonymous lambda — no disconnect needed


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


func _on_donation_completed(_ok: bool, _data: Dictionary) -> void:
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


func _unlocked_lvl5_places() -> Array:
	"""Return [{place_id, name}] for UNLOCKED places at level >= 5."""
	var result: Array = []
	for raw in _places_cache:
		if not raw is Dictionary:
			continue
		var place := raw as Dictionary
		if place.get("state", "") != "UNLOCKED":
			continue
		if int(place.get("level", 0)) >= 5:
			result.append({
				"place_id": place.get("place_id", ""),
				"name":     place.get("name", place.get("place_id", "?")),
			})
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
	for s in ["Name", "Rarity", "Qty", "Set"]:
		sort_opt.add_item(s)
	sort_opt.item_selected.connect(func(idx: int) -> void:
		_sort_mode = ["name", "rarity", "quantity", "set"][idx]
		_rebuild_list(_items_cache)
	)
	row.add_child(sort_opt)

	var fav_btn := Button.new()
	fav_btn.text = "★ Only"
	fav_btn.add_theme_font_size_override("font_size", 11)
	fav_btn.modulate = Color(0.75, 0.75, 0.75)
	fav_btn.pressed.connect(func() -> void:
		_filter_favorites = not _filter_favorites
		fav_btn.modulate = Color(1.0, 0.85, 0.1) if _filter_favorites else Color(0.75, 0.75, 0.75)
		_rebuild_list(_items_cache)
	)
	row.add_child(fav_btn)

	var tag_label := Label.new()
	tag_label.text = "  Tag:"
	tag_label.add_theme_font_size_override("font_size", 11)
	row.add_child(tag_label)

	var tag_edit := LineEdit.new()
	tag_edit.placeholder_text = "filter tag…"
	tag_edit.custom_minimum_size.x = 70
	tag_edit.max_length = 12
	tag_edit.add_theme_font_size_override("font_size", 11)
	tag_edit.text_changed.connect(func(t: String) -> void:
		_filter_tag = t.strip_edges()
		GameAPI.fetch_inventory(_filter_tag)
	)
	row.add_child(tag_edit)

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
		if _filter_favorites and not bool(item.get("favorite", false)):
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
		"set":
			result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
				var sa: String = str(a.get("set_id", ""))
				var sb: String = str(b.get("set_id", ""))
				var a_has: bool = sa != "" and sa != "null"
				var b_has: bool = sb != "" and sb != "null"
				if a_has != b_has:
					return a_has  # items in a set sort before set-less items
				if a_has and sa != sb:
					return sa < sb  # alphabetical within different sets
				return a.get("name", a.get("item_id", "")) < b.get("name", b.get("item_id", ""))
			)
	return result


func _select_for_compare(item: Dictionary) -> void:
	var item_id: String = item.get("item_id", "")
	# Deselect if already selected
	for i in range(_compare_items.size()):
		if (_compare_items[i] as Dictionary).get("item_id", "") == item_id:
			_compare_items.remove_at(i)
			_rebuild_list(_items_cache)
			return
	# Add if fewer than 2
	if _compare_items.size() < 2:
		_compare_items.append(item)
	else:
		_compare_items[0] = _compare_items[1]
		_compare_items[1] = item
	_rebuild_list(_items_cache)


func _rebuild_list(items: Array) -> void:
	for child in _item_list.get_children():
		child.queue_free()
	_craft_panel = null
	_compare_bar = null

	# Craft summary panel (shown when at least one slot is filled)
	if not _craft_slot_a.is_empty() or not _craft_slot_b.is_empty():
		_craft_panel = _make_craft_panel()
		_item_list.add_child(_craft_panel)

	# Compare bar (shown when 2 items selected)
	if _compare_items.size() == 2:
		_compare_bar = HBoxContainer.new()
		var a_name: String = (_compare_items[0] as Dictionary).get("name", "Item A")
		var b_name: String = (_compare_items[1] as Dictionary).get("name", "Item B")
		var info_lbl := Label.new()
		info_lbl.text = "Comparing: %s vs %s" % [a_name, b_name]
		info_lbl.add_theme_font_size_override("font_size", 11)
		info_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var go_btn := Button.new()
		go_btn.text = "Compare →"
		go_btn.modulate = Color(0.60, 0.85, 1.00)
		go_btn.pressed.connect(func() -> void:
			GameAPI.compare_items = _compare_items.duplicate()
			get_tree().change_scene_to_file("res://scenes/ItemCompare.tscn")
		)
		var cancel_btn := Button.new()
		cancel_btn.text = "✕"
		cancel_btn.pressed.connect(func() -> void:
			_compare_items.clear()
			_rebuild_list(_items_cache)
		)
		_compare_bar.add_child(info_lbl)
		_compare_bar.add_child(go_btn)
		_compare_bar.add_child(cancel_btn)
		_item_list.add_child(_compare_bar)

	var visible_items := _apply_filter_sort(items)

	if _sort_mode == "set":
		var last_set: String = "##NONE##"
		for item in visible_items:
			var set_id: String = str(item.get("set_id", ""))
			var in_set: bool = set_id != "" and set_id != "null"
			var group_key: String = set_id if in_set else ""
			if group_key != last_set:
				last_set = group_key
				var header_lbl := Label.new()
				header_lbl.text = set_id.replace("_", " ").capitalize() if in_set else "— No set —"
				header_lbl.modulate = Color(0.55, 0.55, 0.55)
				header_lbl.add_theme_font_size_override("font_size", 11)
				_item_list.add_child(header_lbl)
			_item_list.add_child(_make_card(item))
	else:
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
	var is_locked: bool = bool(item.get("locked", false))
	var name_btn := Button.new()
	name_btn.text = ("🔒 " if is_locked else "") + item.get("name", item.get("item_id", "?"))
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

	# Discard + Sell buttons — only when an unplaced copy exists
	var avail_iid = item.get("available_instance_id", null)
	if avail_iid != null:
		var iid: String = str(avail_iid)

		var discard_btn := Button.new()
		discard_btn.text = "Discard"
		discard_btn.modulate = Color(0.9, 0.4, 0.4)
		discard_btn.pressed.connect(func() -> void:
			GameAPI.discard_item(iid)
		)
		hbox.add_child(discard_btn)

		# Sell button — shows XP value based on rarity
		var rarity_sell: String = item.get("rarity", "COMMON")
		var sell_xp_map := {"COMMON": 5, "UNCOMMON": 15, "RARE": 30, "EPIC": 60, "LEGENDARY": 100}
		var sell_xp: int = sell_xp_map.get(rarity_sell, 5)
		var sell_btn := Button.new()
		sell_btn.text = "Sell +%dXP" % sell_xp
		sell_btn.modulate = Color(0.65, 0.90, 0.55)  # light green
		sell_btn.add_theme_font_size_override("font_size", 10)
		sell_btn.pressed.connect(func() -> void:
			GameAPI.sell_inventory_item(iid)
		)
		hbox.add_child(sell_btn)

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

	# Compare toggle
	var in_compare: bool = false
	for ci in _compare_items:
		if (ci as Dictionary).get("item_id", "") == item_id:
			in_compare = true
			break
	var cmp_btn := Button.new()
	cmp_btn.text = "★ Cmp" if in_compare else "Cmp"
	cmp_btn.modulate = Color(0.60, 0.85, 1.00) if in_compare else Color(0.75, 0.75, 0.75)
	cmp_btn.add_theme_font_size_override("font_size", 10)
	var cmp_snapshot := item.duplicate()
	cmp_btn.pressed.connect(func() -> void:
		_select_for_compare(cmp_snapshot)
	)
	hbox.add_child(cmp_btn)

	# Favorite toggle button
	var is_fav: bool = bool(item.get("favorite", false))
	var fav_btn := Button.new()
	fav_btn.text = "★" if is_fav else "☆"
	fav_btn.modulate = Color(1.0, 0.85, 0.1) if is_fav else Color(0.65, 0.65, 0.65)
	fav_btn.add_theme_font_size_override("font_size", 12)
	var fav_iid: String = str(item.get("available_instance_id", ""))
	if fav_iid != "":
		fav_btn.pressed.connect(func() -> void:
			GameAPI.toggle_inventory_favorite(fav_iid, not is_fav)
		)
	else:
		fav_btn.disabled = true
	hbox.add_child(fav_btn)

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

	# "Donate" — permanently boost a level-5+ place with this item
	if avail_iid != null:
		var donate_places := _unlocked_lvl5_places()
		if donate_places.size() > 0:
			var donate_popup := VBoxContainer.new()
			donate_popup.visible = false
			var donate_iid: String = str(avail_iid)
			for dp in donate_places:
				var dp_btn := Button.new()
				dp_btn.text = "→ %s" % dp["name"]
				dp_btn.flat = true
				dp_btn.add_theme_font_size_override("font_size", 10)
				var dp_id: String = dp["place_id"]
				dp_btn.pressed.connect(func() -> void:
					GameAPI.donate_item_to_place(dp_id, donate_iid)
					donate_popup.visible = false
				)
				donate_popup.add_child(dp_btn)
			vbox.add_child(donate_popup)

			var donate_btn := Button.new()
			donate_btn.text = "Donate"
			donate_btn.modulate = Color(1.0, 0.75, 0.3)   # amber
			donate_btn.pressed.connect(func() -> void:
				donate_popup.visible = not donate_popup.visible
			)
			hbox.add_child(donate_btn)

	# "Gift →" — convert item to place XP instantly (no level requirement)
	if avail_iid != null:
		var unlocked_places := _places_cache.filter(func(p): return p.get("state", "") == "UNLOCKED")
		if unlocked_places.size() > 0:
			var gift_popup := VBoxContainer.new()
			gift_popup.visible = false
			var gift_iid: String = str(avail_iid)
			for gp in unlocked_places:
				var gp_btn := Button.new()
				gp_btn.text = "→ %s" % gp["name"]
				gp_btn.flat = true
				gp_btn.add_theme_font_size_override("font_size", 10)
				var gp_id: String = gp["place_id"]
				gp_btn.pressed.connect(func() -> void:
					GameAPI.gift_item_to_place(gp_id, gift_iid)
					gift_popup.visible = false
				)
				gift_popup.add_child(gp_btn)
			vbox.add_child(gift_popup)

			var gift_btn := Button.new()
			gift_btn.text = "Gift →"
			gift_btn.modulate = Color(0.55, 0.85, 0.95)   # teal
			gift_btn.add_theme_font_size_override("font_size", 10)
			gift_btn.pressed.connect(func() -> void:
				gift_popup.visible = not gift_popup.visible
			)
			hbox.add_child(gift_btn)

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

	# Expiry warning (shown when item expires within 7 days)
	var expires_at = item.get("expires_at", null)
	if expires_at != null:
		var exp_str: String = str(expires_at)
		var exp_lbl := Label.new()
		exp_lbl.text = indent + "⏰ Expires: " + (exp_str.left(10) if exp_str.length() >= 10 else exp_str)
		exp_lbl.modulate = Color(1.0, 0.35, 0.35)
		exp_lbl.add_theme_font_size_override("font_size", 10)
		panel.add_child(exp_lbl)

	# First seen
	var first_seen = item.get("first_seen_at", null)
	if first_seen != null:
		var fs_lbl := Label.new()
		var fs_str: String = str(first_seen)
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

	# Durability — warn when below 100; show repair button
	var durability: int = int(item.get("durability", 100))
	if durability < 100:
		var dur_lbl := Label.new()
		dur_lbl.text = indent + "⚠ Worn (%d%%)" % durability
		dur_lbl.modulate = Color(1.0, 0.5, 0.2) if durability > 0 else Color(0.9, 0.2, 0.2)
		dur_lbl.add_theme_font_size_override("font_size", 10)
		panel.add_child(dur_lbl)

		var avail_iid_dur = item.get("available_instance_id", null)
		if avail_iid_dur != null:
			var iid_str_dur: String = str(avail_iid_dur)
			var rarity_r: String = item.get("rarity", "COMMON")
			var repair_xp_map := {"COMMON": 10, "UNCOMMON": 20, "RARE": 40, "EPIC": 70, "LEGENDARY": 100}
			var repair_cost: int = repair_xp_map.get(rarity_r, 10)
			var repair_btn := Button.new()
			repair_btn.text = "Repair -%dXP" % repair_cost
			repair_btn.modulate = Color(0.5, 0.9, 1.0)
			repair_btn.add_theme_font_size_override("font_size", 10)
			repair_btn.pressed.connect(func() -> void:
				GameAPI.repair_item(iid_str_dur)
			)
			panel.add_child(repair_btn)

	# Lock / Unlock toggle button
	var lock_iid = item.get("available_instance_id", null)
	if lock_iid != null:
		var is_locked_detail: bool = bool(item.get("locked", false))
		var lock_btn := Button.new()
		lock_btn.text = "Unlock 🔒" if is_locked_detail else "Lock 🔒"
		lock_btn.modulate = Color(0.7, 0.7, 1.0) if is_locked_detail else Color(0.75, 0.75, 0.75)
		lock_btn.add_theme_font_size_override("font_size", 10)
		var lock_iid_str: String = str(lock_iid)
		lock_btn.pressed.connect(func() -> void:
			GameAPI.lock_inventory_item(lock_iid_str, not is_locked_detail)
		)
		panel.add_child(lock_btn)

	# Note — inline display + edit field
	var avail_iid = item.get("available_instance_id", null)
	if avail_iid != null:
		var note_row := HBoxContainer.new()
		var note_prefix := Label.new()
		note_prefix.text = indent + "Note:"
		note_prefix.add_theme_font_size_override("font_size", 10)
		note_prefix.modulate = Color(0.65, 0.65, 0.65)
		var note_edit := LineEdit.new()
		note_edit.placeholder_text = "Add a note… (max 50 chars)"
		note_edit.text = str(item.get("note", "")) if item.get("note", null) != null else ""
		note_edit.max_length = 50
		note_edit.add_theme_font_size_override("font_size", 10)
		note_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var iid_str: String = str(avail_iid)
		var _save_note := func() -> void:
			GameAPI.patch_inventory_note(iid_str, note_edit.text.strip_edges())
		note_edit.text_submitted.connect(func(_t: String) -> void: _save_note.call())
		note_edit.focus_exited.connect(func() -> void: _save_note.call())
		note_row.add_child(note_prefix)
		note_row.add_child(note_edit)
		panel.add_child(note_row)

		# ── tags row (3 LineEdits) ────────────────────────────────────────────
		var existing_tags: Array = item.get("tags", [])
		var tags_row := HBoxContainer.new()
		var tags_prefix := Label.new()
		tags_prefix.text = indent + "Tags:"
		tags_prefix.add_theme_font_size_override("font_size", 10)
		tags_prefix.modulate = Color(0.65, 0.65, 0.65)
		tags_row.add_child(tags_prefix)

		var tag_edits: Array[LineEdit] = []
		for ti in range(3):
			var te := LineEdit.new()
			te.placeholder_text = "tag %d" % (ti + 1)
			te.max_length = 12
			te.text = str(existing_tags[ti]) if ti < existing_tags.size() else ""
			te.custom_minimum_size = Vector2(70, 0)
			te.add_theme_font_size_override("font_size", 10)
			tag_edits.append(te)
			tags_row.add_child(te)

		var save_tags_btn := Button.new()
		save_tags_btn.text = "Save"
		save_tags_btn.add_theme_font_size_override("font_size", 10)
		save_tags_btn.pressed.connect(func() -> void:
			var new_tags: Array = []
			for te in tag_edits:
				var v: String = te.text.strip_edges()
				if v != "":
					new_tags.append(v)
			GameAPI.patch_inventory_tags(iid_str, new_tags)
		)
		tags_row.add_child(save_tags_btn)
		panel.add_child(tags_row)

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


func _build_value_overlay() -> void:
	var overlay := ColorRect.new()
	overlay.color = Color(0, 0, 0, 0.75)
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.visible = false
	_value_overlay = overlay
	add_child(overlay)

	var panel := PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(280, 200)
	overlay.add_child(panel)

	var vbox := VBoxContainer.new()
	panel.add_child(vbox)

	var header_row := HBoxContainer.new()
	vbox.add_child(header_row)

	var title := Label.new()
	title.text = "Inventory Value"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 14)
	header_row.add_child(title)

	var close_btn := Button.new()
	close_btn.text = "✕"
	close_btn.pressed.connect(func() -> void: overlay.visible = false)
	header_row.add_child(close_btn)

	# Placeholder label — replaced in _on_value_summary
	var body_lbl := Label.new()
	body_lbl.name = "BodyLabel"
	body_lbl.text = "Loading…"
	body_lbl.modulate = Color(0.75, 0.75, 0.75)
	vbox.add_child(body_lbl)


func _on_value_summary(data: Dictionary) -> void:
	if _value_overlay == null or not is_instance_valid(_value_overlay):
		return

	var panel := _value_overlay.get_child(0)
	var vbox: VBoxContainer = panel.get_child(0) as VBoxContainer
	var body_lbl: Label = vbox.get_node("BodyLabel") as Label

	var total: int = data.get("total_items", 0)
	var est: int   = data.get("estimated_value", 0)
	var by_rar: Dictionary = data.get("by_rarity", {}) as Dictionary

	var lines: PackedStringArray = PackedStringArray()
	lines.append("Total items:  %d" % total)
	lines.append("Est. value:   %d XP" % est)
	lines.append("")
	const ORDER := ["LEGENDARY", "EPIC", "RARE", "UNCOMMON", "COMMON"]
	for rar in ORDER:
		var count: int = by_rar.get(rar, 0) as int
		if count > 0:
			lines.append("  %s: %d" % [rar.capitalize(), count])

	body_lbl.text = "\n".join(lines)
	_value_overlay.visible = true
