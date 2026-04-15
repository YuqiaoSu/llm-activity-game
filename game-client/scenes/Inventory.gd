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
	GameAPI.fetch_inventory()


func _exit_tree() -> void:
	if GameAPI.inventory_updated.is_connected(_on_inventory):
		GameAPI.inventory_updated.disconnect(_on_inventory)
	if GameAPI.equip_updated.is_connected(_on_equip_updated):
		GameAPI.equip_updated.disconnect(_on_equip_updated)


func _on_equip_updated(_item_id: String, _equipped: bool) -> void:
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
	return hbox
