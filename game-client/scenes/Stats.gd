# game-client/scenes/Stats.gd
extends Control

@onready var _stat_list: VBoxContainer = $VBox/Scroll/StatList

var _stats_data: Dictionary = {}
var _daily_data: Array = []


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.stats_updated.connect(_on_stats)
	GameAPI.daily_stats_updated.connect(_on_daily_stats)
	GameAPI.fetch_stats()
	GameAPI.fetch_daily_stats()


func _exit_tree() -> void:
	if GameAPI.stats_updated.is_connected(_on_stats):
		GameAPI.stats_updated.disconnect(_on_stats)
	if GameAPI.daily_stats_updated.is_connected(_on_daily_stats):
		GameAPI.daily_stats_updated.disconnect(_on_daily_stats)


func _on_stats(data: Dictionary) -> void:
	_stats_data = data
	_rebuild()


func _on_daily_stats(entries: Array) -> void:
	_daily_data = entries
	_rebuild()


func _rebuild() -> void:
	for child in _stat_list.get_children():
		child.queue_free()

	# ── lifetime stats ───────────────────────────────────────────────────────
	if not _stats_data.is_empty():
		var stage_names := ["Hatchling", "Growing", "Mature", "Legendary"]
		var stage := mini(_stats_data.get("evolution_stage", 0) as int, stage_names.size() - 1)

		_add_row("Level", str(_stats_data.get("level", 1)))
		_add_row("Stage", stage_names[stage])
		_add_row("Total XP", "%d" % _stats_data.get("total_xp", 0))
		_add_row("Top Category", str(_stats_data.get("top_category", "—")).capitalize())
		_add_row("Sessions Processed", str(_stats_data.get("chunks_processed", 0)))
		_add_row("Items Dropped", str(_stats_data.get("drops_total", 0)))
		_add_row("Places Unlocked", str(_stats_data.get("places_unlocked", 0)))

		var cur_streak: int = _stats_data.get("current_streak", 0)
		var long_streak: int = _stats_data.get("longest_streak", 0)
		_add_row("Current Streak", "%d day%s" % [cur_streak, "s" if cur_streak != 1 else ""])
		_add_row("Longest Streak", "%d day%s" % [long_streak, "s" if long_streak != 1 else ""])

		var cat_xp: Dictionary = _stats_data.get("category_xp", {})
		for category: String in cat_xp:
			var xp: int = cat_xp[category] as int
			if xp > 0:
				_add_row(category.capitalize() + " XP", str(xp))

	# ── daily activity section ───────────────────────────────────────────────
	if not _daily_data.is_empty():
		_add_section_header("Daily Activity (last 7 days)")
		var today := _today_str()
		for raw in _daily_data:
			if not raw is Dictionary:
				continue
			var entry := raw as Dictionary
			var date_str: String = entry.get("date", "")
			var day_label: String = "Today" if date_str == today else date_str
			var xp: int      = entry.get("total_xp", 0)
			var dur_sec: int = entry.get("total_duration_sec", 0)
			var mins: int    = dur_sec / 60
			var dominant: String = _dominant_category(entry.get("categories", {}) as Dictionary)
			var value: String = "%d XP · %d min" % [xp, mins]
			if not dominant.is_empty():
				value += " · " + dominant.capitalize()
			_add_row(day_label, value)


func _add_section_header(title: String) -> void:
	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.20)
	_stat_list.add_child(sep)
	var lbl := Label.new()
	lbl.text = title
	lbl.modulate = Color(0.70, 0.85, 1.00)
	lbl.add_theme_font_size_override("font_size", 12)
	_stat_list.add_child(lbl)


func _add_row(label: String, value: String) -> void:
	var hbox := HBoxContainer.new()
	var lbl := Label.new()
	lbl.text = label
	lbl.custom_minimum_size.x = 160
	var val := Label.new()
	val.text = value
	val.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hbox.add_child(lbl)
	hbox.add_child(val)
	_stat_list.add_child(hbox)


func _today_str() -> String:
	var d := Time.get_date_dict_from_system()
	return "%04d-%02d-%02d" % [d.year, d.month, d.day]


func _dominant_category(categories: Dictionary) -> String:
	var best_cat := ""
	var best_xp  := 0
	for cat: String in categories:
		var xp: int = categories[cat] as int
		if xp > best_xp:
			best_xp  = xp
			best_cat = cat
	return best_cat
