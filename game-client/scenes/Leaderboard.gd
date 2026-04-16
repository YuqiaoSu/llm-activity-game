# game-client/scenes/Leaderboard.gd
# Personal bests screen — shows weekly XP bars for recent weeks.
extends Control

@onready var _title_label: Label       = $VBox/TitleLabel
@onready var _best_label: Label        = $VBox/BestLabel
@onready var _trend_label: Label       = $VBox/TrendLabel
@onready var _scroll: ScrollContainer  = $VBox/Scroll
@onready var _list: VBoxContainer      = $VBox/Scroll/List
@onready var _back_button: Button      = $VBox/BackButton

const _COLOR_CURRENT := Color(0.30, 0.70, 1.00)   # blue — this week
const _COLOR_BEST    := Color(1.00, 0.80, 0.10)   # gold — best week
const _COLOR_NORMAL  := Color(0.50, 0.75, 0.50)   # green — ordinary week
const _COLOR_EMPTY   := Color(0.30, 0.30, 0.30)   # grey — no activity

var _personal_best_xp: int = 0
var _weeks: int = 8


func _ready() -> void:
	GameAPI.leaderboard_updated.connect(_on_leaderboard)
	_back_button.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.fetch_leaderboard(_weeks)


func _exit_tree() -> void:
	if GameAPI.leaderboard_updated.is_connected(_on_leaderboard):
		GameAPI.leaderboard_updated.disconnect(_on_leaderboard)


func _on_leaderboard(data: Dictionary) -> void:
	_personal_best_xp = data.get("personal_best_xp", 0) as int
	var trend: String = data.get("trend", "flat")
	var weeks_arr: Array = data.get("weeks", [])

	_best_label.text = "Personal best: %d XP" % _personal_best_xp if _personal_best_xp > 0 else "No activity yet"

	match trend:
		"up":
			_trend_label.text = "▲ Trending up vs last week"
			_trend_label.modulate = Color(0.3, 1.0, 0.4)
		"down":
			_trend_label.text = "▼ Trending down vs last week"
			_trend_label.modulate = Color(1.0, 0.4, 0.3)
		_:
			_trend_label.text = "→ Flat vs last week"
			_trend_label.modulate = Color(0.7, 0.7, 0.7)

	for child in _list.get_children():
		child.queue_free()

	for raw in weeks_arr:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var total_xp: int  = entry.get("total_xp", 0) as int
	var active_min: int = entry.get("total_active_min", 0) as int
	var is_current: bool = bool(entry.get("is_current", false))
	var is_best: bool    = bool(entry.get("is_best", false))
	var week_start: String = entry.get("week_start", "")
	var week_end: String   = entry.get("week_end", "")

	var vbox := VBoxContainer.new()
	vbox.custom_minimum_size.y = 44

	# ── header row: date range + XP summary ──────────────────────────────────
	var header := HBoxContainer.new()

	var date_lbl := Label.new()
	date_lbl.text = "%s → %s" % [week_start, week_end]
	date_lbl.custom_minimum_size.x = 180
	if is_current:
		date_lbl.text += "  (this week)"
		date_lbl.modulate = _COLOR_CURRENT
	header.add_child(date_lbl)

	if is_best and total_xp > 0:
		var star_lbl := Label.new()
		star_lbl.text = " ★ Best"
		star_lbl.modulate = _COLOR_BEST
		header.add_child(star_lbl)

	var xp_lbl := Label.new()
	xp_lbl.text = " %d XP" % total_xp
	if total_xp == 0:
		xp_lbl.modulate = _COLOR_EMPTY
	else:
		xp_lbl.modulate = Color.WHITE
	header.add_child(xp_lbl)

	if active_min > 0:
		var min_lbl := Label.new()
		min_lbl.text = "  %dmin active" % active_min
		min_lbl.modulate = Color(0.65, 0.65, 0.65)
		min_lbl.add_theme_font_size_override("font_size", 10)
		header.add_child(min_lbl)

	vbox.add_child(header)

	# ── proportional XP bar ───────────────────────────────────────────────────
	var bar_bg := ColorRect.new()
	bar_bg.color = Color(0.15, 0.15, 0.15)
	bar_bg.custom_minimum_size = Vector2(0, 8)
	bar_bg.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var bar_fill := ColorRect.new()
	bar_fill.color = _COLOR_CURRENT if is_current else (_COLOR_BEST if is_best else _COLOR_NORMAL)
	if total_xp == 0:
		bar_fill.color = _COLOR_EMPTY

	# Fill ratio: relative to personal best (or 100% if it's the best week)
	var ratio: float = 0.0
	if _personal_best_xp > 0 and total_xp > 0:
		ratio = clampf(float(total_xp) / float(_personal_best_xp), 0.0, 1.0)

	bar_fill.anchor_right = ratio
	bar_fill.size_flags_horizontal = 0
	bar_fill.anchor_top = 0.0
	bar_fill.anchor_bottom = 1.0

	bar_bg.add_child(bar_fill)
	vbox.add_child(bar_bg)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.08)
	vbox.add_child(sep)

	return vbox
