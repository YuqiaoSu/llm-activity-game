# game-client/scenes/DailyChart.gd
# Activity history chart — per-day XP bars stacked by category for the last 14 days.
extends Control

@onready var _header_label: Label      = $VBox/Header/HeaderLabel
@onready var _list: VBoxContainer      = $VBox/Scroll/List
@onready var _back_button: Button      = $VBox/Header/BackButton

# Category colours matching History.gd
const _CAT_COLORS := {
	"WORK":    Color(0.27, 0.58, 1.00),
	"GAME":    Color(0.18, 0.80, 0.44),
	"VIDEO":   Color(0.96, 0.26, 0.21),
	"SOCIAL":  Color(1.00, 0.50, 0.00),
	"EXPLORE": Color(0.99, 0.76, 0.03),
	"SLEEP":   Color(0.49, 0.34, 0.76),
	"SPECIAL": Color(0.64, 0.19, 0.85),
}
const _CAT_COLOR_FALLBACK := Color(0.45, 0.45, 0.45)
const _ALL_CATEGORIES := ["WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"]
const _DAYS := 14

var _max_day_xp: int = 1   # avoid division by zero


func _ready() -> void:
	GameAPI.daily_chart_updated.connect(_on_daily_chart)
	_back_button.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.fetch_daily_chart(_DAYS)


func _exit_tree() -> void:
	if GameAPI.daily_chart_updated.is_connected(_on_daily_chart):
		GameAPI.daily_chart_updated.disconnect(_on_daily_chart)


func _on_daily_chart(entries: Array) -> void:
	# Compute max daily XP for normalising bars
	_max_day_xp = 1
	for raw in entries:
		if raw is Dictionary:
			var xp: int = (raw as Dictionary).get("total_xp", 0) as int
			if xp > _max_day_xp:
				_max_day_xp = xp

	_header_label.text = "Daily Activity (%d days)" % entries.size()

	for child in _list.get_children():
		child.queue_free()

	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var total_xp: int   = entry.get("total_xp", 0) as int
	var date_str: String = entry.get("date", "?")
	var by_cat: Dictionary = entry.get("by_category", {}) as Dictionary

	var vbox := VBoxContainer.new()
	vbox.custom_minimum_size.y = 40

	# ── header: date + total XP ──────────────────────────────────────────────
	var header := HBoxContainer.new()

	var date_lbl := Label.new()
	date_lbl.text = date_str
	date_lbl.custom_minimum_size.x = 100
	date_lbl.modulate = Color(0.85, 0.85, 0.85)
	header.add_child(date_lbl)

	var xp_lbl := Label.new()
	xp_lbl.text = "%d XP" % total_xp
	xp_lbl.custom_minimum_size.x = 70
	if total_xp == 0:
		xp_lbl.modulate = Color(0.35, 0.35, 0.35)
	else:
		xp_lbl.modulate = Color.WHITE
	header.add_child(xp_lbl)

	# Duration hint
	var dur_sec: int = entry.get("total_duration_sec", 0) as int
	if dur_sec > 0:
		var dur_lbl := Label.new()
		dur_lbl.text = "%dmin" % (dur_sec / 60)
		dur_lbl.modulate = Color(0.55, 0.55, 0.55)
		dur_lbl.add_theme_font_size_override("font_size", 10)
		header.add_child(dur_lbl)

	vbox.add_child(header)

	# ── stacked category bars ────────────────────────────────────────────────
	# Each bar segment is proportional to that category's share of the max-day XP.
	var bar_container := HBoxContainer.new()
	bar_container.custom_minimum_size.y = 10
	bar_container.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	if total_xp > 0:
		for cat in _ALL_CATEGORIES:
			var cat_xp: int = by_cat.get(cat, 0) as int
			if cat_xp <= 0:
				continue
			var seg := ColorRect.new()
			seg.color = _CAT_COLORS.get(cat, _CAT_COLOR_FALLBACK)
			# Width is cat_xp / max_day_xp * full_width.
			# We model this as a fraction of SIZE_EXPAND_FILL by using stretch_ratio.
			seg.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			seg.size_flags_stretch_ratio = float(cat_xp) / float(_max_day_xp)
			bar_container.add_child(seg)

		# Remainder (unfilled) bar
		var remainder_xp: int = _max_day_xp - total_xp
		if remainder_xp > 0:
			var gap := ColorRect.new()
			gap.color = Color(0.12, 0.12, 0.12)
			gap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			gap.size_flags_stretch_ratio = float(remainder_xp) / float(_max_day_xp)
			bar_container.add_child(gap)
	else:
		# Empty day — grey bar
		var empty_bar := ColorRect.new()
		empty_bar.color = Color(0.12, 0.12, 0.12)
		empty_bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		bar_container.add_child(empty_bar)

	vbox.add_child(bar_container)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.06)
	vbox.add_child(sep)

	return vbox
