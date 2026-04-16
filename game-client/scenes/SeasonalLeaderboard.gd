# game-client/scenes/SeasonalLeaderboard.gd
# Monthly personal bests — mirrors the weekly Leaderboard layout.
extends Control

@onready var _title_lbl:  Label          = $VBox/TitleLabel
@onready var _best_lbl:   Label          = $VBox/BestLabel
@onready var _trend_lbl:  Label          = $VBox/TrendLabel
@onready var _list:       VBoxContainer  = $VBox/Scroll/List
@onready var _months_spin: SpinBox       = $VBox/Controls/MonthsSpin

const _COLOR_CURRENT := Color(0.30, 0.70, 1.00)   # blue — this month
const _COLOR_BEST    := Color(1.00, 0.80, 0.10)   # gold — best month
const _COLOR_NORMAL  := Color(0.50, 0.75, 0.50)   # green — ordinary month
const _COLOR_EMPTY   := Color(0.30, 0.30, 0.30)   # grey — no activity

var _personal_best_xp: int = 0
var _months: int = 6


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	_months_spin.min_value = 2
	_months_spin.max_value = 24
	_months_spin.step      = 1
	_months_spin.value     = _months
	_months_spin.value_changed.connect(func(v: float) -> void:
		_months = int(v)
		GameAPI.fetch_seasonal_leaderboard(_months)
	)
	GameAPI.seasonal_leaderboard_updated.connect(_on_leaderboard)
	GameAPI.fetch_seasonal_leaderboard(_months)


func _exit_tree() -> void:
	if GameAPI.seasonal_leaderboard_updated.is_connected(_on_leaderboard):
		GameAPI.seasonal_leaderboard_updated.disconnect(_on_leaderboard)


func _on_leaderboard(data: Dictionary) -> void:
	_personal_best_xp = data.get("personal_best_xp", 0) as int
	var trend: String  = data.get("trend", "flat")
	var months_arr: Array = data.get("months", [])

	_title_lbl.text = "Seasonal Leaderboard"
	_best_lbl.text = "Personal best: %d XP / month" % _personal_best_xp if _personal_best_xp > 0 else "No activity yet"

	match trend:
		"up":
			_trend_lbl.text = "▲ Up vs last month"
			_trend_lbl.modulate = Color(0.3, 1.0, 0.4)
		"down":
			_trend_lbl.text = "▼ Down vs last month"
			_trend_lbl.modulate = Color(1.0, 0.4, 0.3)
		_:
			_trend_lbl.text = "→ Flat vs last month"
			_trend_lbl.modulate = Color(0.7, 0.7, 0.7)

	for child in _list.get_children():
		child.queue_free()

	for raw in months_arr:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var total_xp: int    = entry.get("total_xp", 0) as int
	var active_min: int  = entry.get("active_min", 0) as int
	var is_current: bool = bool(entry.get("is_current", false))
	var is_best: bool    = bool(entry.get("is_best", false))
	var month: String    = entry.get("month", "")

	var bar_color := _COLOR_NORMAL
	if total_xp == 0:
		bar_color = _COLOR_EMPTY
	elif is_current:
		bar_color = _COLOR_CURRENT
	elif is_best:
		bar_color = _COLOR_BEST

	var vbox := VBoxContainer.new()
	vbox.custom_minimum_size.y = 44

	# ── header row ────────────────────────────────────────────────────────────
	var header := HBoxContainer.new()

	var month_lbl := Label.new()
	month_lbl.text = month
	month_lbl.custom_minimum_size.x = 100
	month_lbl.modulate = bar_color
	if is_current:
		month_lbl.text += "  (this month)"
	header.add_child(month_lbl)

	if is_best and total_xp > 0:
		var star := Label.new()
		star.text = " ★ Best"
		star.modulate = _COLOR_BEST
		star.add_theme_font_size_override("font_size", 11)
		header.add_child(star)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)

	var xp_lbl := Label.new()
	xp_lbl.text = "%d XP  ·  %d min" % [total_xp, active_min]
	xp_lbl.modulate = bar_color
	header.add_child(xp_lbl)

	vbox.add_child(header)

	# ── proportional XP bar ────────────────────────────────────────────────────
	var bar := ProgressBar.new()
	bar.max_value = max(_personal_best_xp, 1)
	bar.value = total_xp
	bar.show_percentage = false
	bar.custom_minimum_size.y = 12
	bar.modulate = bar_color
	vbox.add_child(bar)

	# ── separator ─────────────────────────────────────────────────────────────
	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.12)
	vbox.add_child(sep)

	return vbox
