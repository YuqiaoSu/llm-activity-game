# game-client/scenes/ItemSets.gd
extends Control

@onready var _list: VBoxContainer = $VBox/Scroll/List

const _RARITY_COLORS := {
	"COMMON":    Color(0.75, 0.75, 0.75),
	"UNCOMMON":  Color(0.30, 0.80, 0.30),
	"RARE":      Color(0.25, 0.55, 1.00),
	"EPIC":      Color(0.75, 0.30, 1.00),
	"LEGENDARY": Color(1.00, 0.70, 0.10),
}
const _GOLD   := Color(1.00, 0.84, 0.00)
const _DIM    := Color(0.50, 0.50, 0.50)
const _GREEN  := Color(0.30, 0.85, 0.30)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Inventory.tscn")
	)
	GameAPI.item_sets_updated.connect(_on_sets)
	GameAPI.fetch_item_sets()


func _exit_tree() -> void:
	if GameAPI.item_sets_updated.is_connected(_on_sets):
		GameAPI.item_sets_updated.disconnect(_on_sets)


func _on_sets(entries: Array) -> void:
	for child in _list.get_children():
		child.queue_free()

	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "No item sets found. Discover more items to unlock sets!"
		lbl.modulate = _DIM
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD
		_list.add_child(lbl)
		return

	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_set(raw as Dictionary))


func _make_set(entry: Dictionary) -> Control:
	var set_id: String    = entry.get("set_id", "unknown")
	var items: Array      = entry.get("items", []) as Array
	var owned: int        = entry.get("owned_count", 0) as int
	var total: int        = entry.get("total_count", 0) as int
	var complete: bool    = entry.get("complete", false) as bool

	var vbox := VBoxContainer.new()

	# ── Set header row ────────────────────────────────────────────────────────
	var header_row := HBoxContainer.new()

	var name_lbl := Label.new()
	name_lbl.text = set_id.replace("set_", "").replace("_", " ").capitalize()
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.modulate = _GOLD if complete else Color.WHITE

	var count_lbl := Label.new()
	count_lbl.text = "%d / %d" % [owned, total]
	count_lbl.modulate = _GREEN if complete else _DIM

	if complete:
		var badge := Label.new()
		badge.text = " ★"
		badge.modulate = _GOLD
		header_row.add_child(badge)

	header_row.add_child(name_lbl)
	header_row.add_child(count_lbl)

	# Progress bar
	var bar := ProgressBar.new()
	bar.max_value = total
	bar.value = owned
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(0, 6)

	# ── Item rows ──────────────────────────────────────────────────────────────
	var items_vbox := VBoxContainer.new()
	for raw_item in items:
		var item := raw_item as Dictionary
		var item_owned: bool   = item.get("owned", false) as bool
		var rarity: String     = item.get("rarity", "COMMON")
		var item_name: String  = item.get("name", "?")

		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 6)

		var check := Label.new()
		check.text = "✓" if item_owned else "✗"
		check.modulate = _GREEN if item_owned else _DIM
		check.custom_minimum_size.x = 16

		var rarity_lbl := Label.new()
		rarity_lbl.text = "[%s]" % rarity
		rarity_lbl.modulate = _RARITY_COLORS.get(rarity, _DIM)
		rarity_lbl.add_theme_font_size_override("font_size", 10)
		rarity_lbl.custom_minimum_size.x = 80

		var item_lbl := Label.new()
		item_lbl.text = item_name
		item_lbl.modulate = Color.WHITE if item_owned else _DIM
		item_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

		row.add_child(check)
		row.add_child(rarity_lbl)
		row.add_child(item_lbl)
		items_vbox.add_child(row)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.15)

	vbox.add_child(header_row)
	vbox.add_child(bar)
	vbox.add_child(items_vbox)
	vbox.add_child(sep)
	return vbox
