# game-client/scenes/Inventory.gd
extends Control

const RarityColor := preload("res://utils/RarityColor.gd")

@onready var _count_label: Label       = $VBox/Header/CountLabel
@onready var _item_list: VBoxContainer = $VBox/Scroll/ItemList


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.inventory_updated.connect(_on_inventory)
	GameAPI.equip_updated.connect(_on_equip_updated)
	GameAPI.item_discarded.connect(_on_item_discarded)
	GameAPI.fetch_inventory()


func _exit_tree() -> void:
	if GameAPI.inventory_updated.is_connected(_on_inventory):
		GameAPI.inventory_updated.disconnect(_on_inventory)
	if GameAPI.equip_updated.is_connected(_on_equip_updated):
		GameAPI.equip_updated.disconnect(_on_equip_updated)
	if GameAPI.item_discarded.is_connected(_on_item_discarded):
		GameAPI.item_discarded.disconnect(_on_item_discarded)


func _on_equip_updated(_item_id: String, _equipped: bool) -> void:
	GameAPI.fetch_inventory()


func _on_item_discarded(_instance_id: String) -> void:
	GameAPI.fetch_inventory()


func _on_inventory(items: Array) -> void:
	_count_label.text = "Inventory (%d)" % items.size()
	for child in _item_list.get_children():
		child.queue_free()
	for raw in items:
		if not raw is Dictionary:
			push_warning("Inventory: skipping non-Dictionary item: %s" % str(raw))
			continue
		_item_list.add_child(_make_card(raw as Dictionary))


func _make_card(item: Dictionary) -> Control:
	var vbox := VBoxContainer.new()

	# ── main row ─────────────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(14, 14)
	dot.color = RarityColor.for_rarity(item.get("rarity", "COMMON"))

	var name_lbl := Label.new()
	name_lbl.text = item.get("name", item.get("item_id", "?"))
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

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
	hbox.add_child(name_lbl)
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

	vbox.add_child(hbox)

	# ── effect summary row (only when slot effects present) ───────────────────
	var effects: Array = item.get("effects", [])
	var effect_text := _format_slot_effects(effects)
	if effect_text != "":
		var eff_lbl := Label.new()
		eff_lbl.text = "  ✦ " + effect_text
		eff_lbl.modulate = Color(0.85, 0.75, 0.35)   # warm gold
		eff_lbl.add_theme_font_size_override("font_size", 11)
		vbox.add_child(eff_lbl)

	return vbox


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
	return ", ".join(parts)
