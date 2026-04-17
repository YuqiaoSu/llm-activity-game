# game-client/scenes/Recap.gd
extends Control

@onready var _week_label: Label       = $VBox/Header/WeekLabel
@onready var _daily_list: VBoxContainer = $VBox/DailySection/DailyList
@onready var _list: VBoxContainer     = $VBox/Scroll/List

const _COLOR_GOLD    := Color(1.0, 0.82, 0.1)
const _COLOR_DIM     := Color(0.6, 0.6, 0.6)
const _COLOR_GOOD    := Color(0.3, 0.85, 0.3)

var _weeks_ago: int = 0


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	$VBox/Header/PrevWeekBtn.pressed.connect(func() -> void:
		_weeks_ago += 1
		GameAPI.fetch_weekly_recap(_weeks_ago)
	)
	$VBox/Header/NextWeekBtn.pressed.connect(func() -> void:
		if _weeks_ago > 0:
			_weeks_ago -= 1
			GameAPI.fetch_weekly_recap(_weeks_ago)
	)
	GameAPI.recap_updated.connect(_on_recap)
	GameAPI.daily_recap_updated.connect(_on_daily_recap)
	GameAPI.fetch_weekly_recap(0)
	GameAPI.fetch_daily_recap()


func _exit_tree() -> void:
	if GameAPI.recap_updated.is_connected(_on_recap):
		GameAPI.recap_updated.disconnect(_on_recap)
	if GameAPI.daily_recap_updated.is_connected(_on_daily_recap):
		GameAPI.daily_recap_updated.disconnect(_on_daily_recap)


func _on_daily_recap(data: Dictionary) -> void:
	for child in _daily_list.get_children():
		child.queue_free()

	var total_xp: int = data.get("total_xp_earned", 0) as int
	var active_min: int = data.get("total_active_min", 0) as int
	var drops: int = data.get("drops_earned", 0) as int
	var goals_done: int = data.get("goals_completed", 0) as int
	var goals_tot: int = data.get("goals_total", 0) as int
	var streak: int = data.get("streak_days", 0) as int
	var top_cat = data.get("top_category", null)

	if total_xp == 0 and active_min == 0:
		var lbl := Label.new()
		lbl.text = "  No activity yet today"
		lbl.modulate = _COLOR_DIM
		_daily_list.add_child(lbl)
		return

	_add_daily_stat("XP earned",   str(total_xp))
	_add_daily_stat("Active time", "%d min" % active_min)
	_add_daily_stat("Drops",       str(drops))
	if goals_tot > 0:
		var goals_color := _COLOR_GOOD if goals_done >= goals_tot else Color.WHITE
		_add_daily_stat("Goals", "%d / %d" % [goals_done, goals_tot], goals_color)
	if streak > 0:
		_add_daily_stat("Streak", "%d day%s 🔥" % [streak, "s" if streak != 1 else ""])
	if top_cat != null:
		_add_daily_stat("Top cat", str(top_cat).capitalize(), _COLOR_GOLD)


func _add_daily_stat(label: String, value: String, color: Color = Color.WHITE) -> void:
	var hbox := HBoxContainer.new()
	var lbl := Label.new()
	lbl.text = "  " + label
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.modulate = _COLOR_DIM
	lbl.add_theme_font_size_override("font_size", 12)
	var val := Label.new()
	val.text = value
	val.modulate = color
	val.add_theme_font_size_override("font_size", 12)
	hbox.add_child(lbl)
	hbox.add_child(val)
	_daily_list.add_child(hbox)


func _on_recap(data: Dictionary) -> void:
	_week_label.text = "%s → %s" % [data.get("week_start", "?"), data.get("week_end", "?")]
	for child in _list.get_children():
		child.queue_free()

	# ── headline stats ────────────────────────────────────────────────────────
	_add_stat("Active time",     "%d min" % data.get("total_active_min", 0))
	_add_stat("XP earned",       str(data.get("total_xp_earned", 0)))
	_add_stat("Items found",     str(data.get("items_found", 0)))

	var lvl_start: int = data.get("level_start", 1)
	var lvl_end:   int = data.get("level_end", 1)
	if lvl_end > lvl_start:
		_add_stat("Level",  "%d → %d  ↑" % [lvl_start, lvl_end], _COLOR_GOOD)
	else:
		_add_stat("Level", "Lv. %d" % lvl_end)

	_add_stat("Challenges",  "%d completed" % data.get("challenges_completed", 0))
	_add_stat("Achievements", "%d unlocked"  % data.get("achievements_unlocked", 0))
	_add_stat("Streak",      "%d days"       % data.get("streak_at_end", 0))

	# ── category breakdown ────────────────────────────────────────────────────
	var breakdown = data.get("category_breakdown", {})
	if breakdown is Dictionary and (breakdown as Dictionary).size() > 0:
		_add_separator()
		var sep_lbl := Label.new()
		sep_lbl.text = "  Category breakdown"
		sep_lbl.modulate = _COLOR_DIM
		sep_lbl.add_theme_font_size_override("font_size", 11)
		_list.add_child(sep_lbl)

		# Sort by XP descending
		var cats: Array = (breakdown as Dictionary).keys()
		cats.sort_custom(func(a: String, b: String) -> bool:
			return (breakdown as Dictionary).get(a, {}).get("xp", 0) > \
			       (breakdown as Dictionary).get(b, {}).get("xp", 0)
		)
		for cat in cats:
			var cd = (breakdown as Dictionary).get(cat, {}) as Dictionary
			var xp: int = cd.get("xp", 0)
			var min_v: int = cd.get("active_min", 0)
			_add_stat(
				"  " + str(cat).capitalize(),
				"%d XP · %d min" % [xp, min_v],
			)


func _add_stat(label: String, value: String, color: Color = Color.WHITE) -> void:
	var hbox := HBoxContainer.new()
	var lbl := Label.new()
	lbl.text = label
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.modulate = _COLOR_DIM
	var val := Label.new()
	val.text = value
	val.modulate = color
	hbox.add_child(lbl)
	hbox.add_child(val)
	_list.add_child(hbox)


func _add_separator() -> void:
	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.12)
	_list.add_child(sep)
