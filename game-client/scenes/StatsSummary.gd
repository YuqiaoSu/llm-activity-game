# game-client/scenes/StatsSummary.gd
extends Control

@onready var _list: VBoxContainer = $VBox/Scroll/List

const _CAT_ORDER := ["WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"]
const _DIM := Color(0.55, 0.55, 0.55)
const _ACCENT := Color(0.4, 0.85, 1.0)
const _GOLD  := Color(1.0, 0.85, 0.3)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Stats.tscn")
	)
	GameAPI.stats_summary_updated.connect(_on_summary)
	GameAPI.fetch_stats_summary()


func _exit_tree() -> void:
	if GameAPI.stats_summary_updated.is_connected(_on_summary):
		GameAPI.stats_summary_updated.disconnect(_on_summary)


func _on_summary(data: Dictionary) -> void:
	for child in _list.get_children():
		child.queue_free()

	_add_section("Overall")
	_add_stat("Total XP",         "%d XP" % data.get("total_xp", 0),        _ACCENT)
	_add_stat("Level",            "Lv. %d" % data.get("level", 1),           _ACCENT)
	_add_stat("Sessions",         "%d chunks" % data.get("total_chunks", 0), Color.WHITE)
	_add_stat("Active time",      "%d min" % data.get("total_active_min", 0), Color.WHITE)
	_add_stat("Peak week XP",     "%d XP" % data.get("peak_week_xp", 0),     _GOLD)
	_add_stat("Items collected",  "%d unique" % data.get("items_collected", 0), Color.WHITE)

	_add_section("Categories (all-time XP)")
	var breakdown: Dictionary = data.get("category_breakdown", {}) as Dictionary
	for cat in _CAT_ORDER:
		var xp: int = breakdown.get(cat, 0) as int
		_add_stat(cat.capitalize(), "%d XP" % xp, Color.WHITE if xp > 0 else _DIM)


func _add_section(title: String) -> void:
	var lbl := Label.new()
	lbl.text = title
	lbl.modulate = _GOLD
	lbl.add_theme_font_size_override("font_size", 13)
	_list.add_child(lbl)
	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.2)
	_list.add_child(sep)


func _add_stat(label: String, value: String, col: Color) -> void:
	var row := HBoxContainer.new()
	var lbl := Label.new()
	lbl.text = label
	lbl.custom_minimum_size.x = 140
	lbl.modulate = _DIM
	var val := Label.new()
	val.text = value
	val.modulate = col
	val.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(lbl)
	row.add_child(val)
	_list.add_child(row)
