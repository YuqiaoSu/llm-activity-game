# game-client/scenes/Catalogue.gd
# Loot table browser: shows all droppable items grouped by category.
# Discovered items show full name + description; undiscovered show "???".
extends Control

@onready var _title_label: Label         = $VBox/TitleLabel
@onready var _tabs: HBoxContainer        = $VBox/Tabs
@onready var _count_label: Label         = $VBox/CountLabel
@onready var _scroll: ScrollContainer    = $VBox/Scroll
@onready var _list: VBoxContainer        = $VBox/Scroll/List
@onready var _back_button: Button        = $VBox/BackButton

const _ALL_CATEGORIES := ["WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"]
const _RARITY_COLORS := {
	"COMMON":    Color(0.85, 0.85, 0.85),
	"UNCOMMON":  Color(0.40, 0.85, 0.40),
	"RARE":      Color(0.30, 0.60, 1.00),
	"EPIC":      Color(0.80, 0.40, 1.00),
	"LEGENDARY": Color(1.00, 0.75, 0.10),
}

var _current_category: String = ""  # "" = all categories
var _all_items: Array = []
var _tab_buttons: Dictionary = {}   # category -> Button


func _ready() -> void:
	GameAPI.catalogue_updated.connect(_on_catalogue_updated)
	GameAPI.wishlist_toggled.connect(_on_wishlist_toggled)
	_back_button.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	_build_tabs()
	_select_category("")
	GameAPI.fetch_catalogue()


func _exit_tree() -> void:
	if GameAPI.catalogue_updated.is_connected(_on_catalogue_updated):
		GameAPI.catalogue_updated.disconnect(_on_catalogue_updated)
	if GameAPI.wishlist_toggled.is_connected(_on_wishlist_toggled):
		GameAPI.wishlist_toggled.disconnect(_on_wishlist_toggled)


func _on_wishlist_toggled(_data: Dictionary) -> void:
	GameAPI.fetch_catalogue()


func _build_tabs() -> void:
	# "All" tab
	var all_btn := Button.new()
	all_btn.text = "All"
	all_btn.pressed.connect(func() -> void: _select_category(""))
	_tabs.add_child(all_btn)
	_tab_buttons[""] = all_btn

	for cat in _ALL_CATEGORIES:
		var btn := Button.new()
		btn.text = cat.capitalize()
		btn.pressed.connect(func() -> void: _select_category(cat))
		_tabs.add_child(btn)
		_tab_buttons[cat] = btn


func _select_category(cat: String) -> void:
	_current_category = cat
	_title_label.text = "Catalogue" if cat.is_empty() else "Catalogue — " + cat.capitalize()
	# Highlight active tab
	for key in _tab_buttons:
		var btn: Button = _tab_buttons[key]
		btn.modulate = Color(1.0, 0.85, 0.2) if key == cat else Color.WHITE
	_rebuild_list()


func _on_catalogue_updated(items: Array) -> void:
	_all_items = items
	_rebuild_list()


func _rebuild_list() -> void:
	for child in _list.get_children():
		child.queue_free()

	var visible_items: Array = _all_items
	if not _current_category.is_empty():
		visible_items = _all_items.filter(
			func(i: Dictionary) -> bool:
				return (i.get("category") or "") == _current_category
		)

	var discovered_count: int = visible_items.filter(
		func(i: Dictionary) -> bool: return bool(i.get("discovered", false))
	).size()
	_count_label.text = "%d / %d discovered" % [discovered_count, visible_items.size()]

	for item in visible_items:
		_list.add_child(_make_item_row(item))


func _make_item_row(item: Dictionary) -> Control:
	var hbox := HBoxContainer.new()
	hbox.custom_minimum_size.y = 28

	# Rarity color swatch
	var swatch := ColorRect.new()
	swatch.custom_minimum_size = Vector2(6, 28)
	var rarity: String = item.get("rarity", "COMMON")
	swatch.color = _RARITY_COLORS.get(rarity, Color.GRAY)
	hbox.add_child(swatch)

	# Name / placeholder
	var name_lbl := Label.new()
	name_lbl.custom_minimum_size.x = 160
	var discovered: bool = bool(item.get("discovered", false))
	if discovered:
		name_lbl.text = item.get("name", "?")
	else:
		name_lbl.text = "???"
		name_lbl.modulate = Color(0.5, 0.5, 0.5)
	hbox.add_child(name_lbl)

	# Rarity label
	var rarity_lbl := Label.new()
	rarity_lbl.text = rarity.capitalize()
	rarity_lbl.custom_minimum_size.x = 80
	rarity_lbl.modulate = _RARITY_COLORS.get(rarity, Color.WHITE)
	hbox.add_child(rarity_lbl)

	# Category (only shown in "All" view)
	if _current_category.is_empty():
		var cat_lbl := Label.new()
		cat_lbl.text = (item.get("category") or "").capitalize()
		cat_lbl.custom_minimum_size.x = 70
		cat_lbl.modulate = Color(0.7, 0.9, 1.0)
		hbox.add_child(cat_lbl)

	# Description (only for discovered items)
	if discovered:
		var desc: String = item.get("description", "")
		if not desc.is_empty():
			var desc_lbl := Label.new()
			desc_lbl.text = desc
			desc_lbl.modulate = Color(0.75, 0.75, 0.75)
			desc_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			hbox.add_child(desc_lbl)

	# Wishlist toggle (★ / ☆) — always shown so players can wishlist undiscovered items
	var wishlisted: bool = bool(item.get("wishlisted", false))
	var item_id: String = item.get("item_id", "")
	var star_btn := Button.new()
	star_btn.text = "★" if wishlisted else "☆"
	star_btn.modulate = Color(1.0, 0.85, 0.1) if wishlisted else Color(0.5, 0.5, 0.5)
	star_btn.custom_minimum_size.x = 28
	star_btn.pressed.connect(func() -> void:
		if wishlisted:
			GameAPI.remove_from_wishlist(item_id)
		else:
			GameAPI.add_to_wishlist(item_id)
	)
	hbox.add_child(star_btn)

	return hbox
