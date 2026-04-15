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
	GameAPI.fetch_inventory()


func _exit_tree() -> void:
	if GameAPI.inventory_updated.is_connected(_on_inventory):
		GameAPI.inventory_updated.disconnect(_on_inventory)


func _on_inventory(items: Array) -> void:
	_count_label.text = "Inventory (%d)" % items.size()
	for child in _item_list.get_children():
		child.queue_free()
	for item: Dictionary in items:
		_item_list.add_child(_make_card(item))


func _make_card(item: Dictionary) -> Control:
	var hbox := HBoxContainer.new()

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(14, 14)
	dot.color = RarityColor.for_rarity(item.get("rarity", "COMMON"))

	var name_lbl := Label.new()
	name_lbl.text = item.get("name", item.get("item_id", "?"))
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var cat_lbl := Label.new()
	cat_lbl.text = (item.get("category", "") as String).capitalize()

	hbox.add_child(dot)
	hbox.add_child(name_lbl)
	hbox.add_child(cat_lbl)
	return hbox
