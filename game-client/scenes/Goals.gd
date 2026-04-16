# game-client/scenes/Goals.gd
extends Control

@onready var _count_label: Label        = $VBox/Header/CountLabel
@onready var _list: VBoxContainer       = $VBox/Scroll/List

const _COLOR_DONE    := Color(0.3, 0.85, 0.3)
const _COLOR_PENDING := Color(0.85, 0.85, 0.85)
const _COLOR_BAR_BG  := Color(0.25, 0.25, 0.25)
const _COLOR_BAR_FG  := Color(0.3, 0.7, 1.0)
const _COLOR_BAR_DONE := Color(0.3, 0.85, 0.3)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.daily_goals_updated.connect(_on_goals)
	GameAPI.fetch_daily_goals()


func _exit_tree() -> void:
	if GameAPI.daily_goals_updated.is_connected(_on_goals):
		GameAPI.daily_goals_updated.disconnect(_on_goals)


func _on_goals(entries: Array) -> void:
	var done := entries.filter(func(g: Variant) -> bool:
		return (g as Dictionary).get("completed", false)
	).size()
	_count_label.text = "Daily Goals  %d / %d" % [done, entries.size()]
	for child in _list.get_children():
		child.queue_free()
	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "  No goals yet — trigger a sync to generate today's goals."
		lbl.modulate = Color(0.6, 0.6, 0.6)
		_list.add_child(lbl)
		return
	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(g: Dictionary) -> Control:
	var done: bool = g.get("completed", false)
	var pct: int   = g.get("progress_pct", 0)
	var cat: String = g.get("category", "")

	var vbox := VBoxContainer.new()

	# ── header row ────────────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var check_lbl := Label.new()
	check_lbl.text = "✓" if done else "○"
	check_lbl.modulate = _COLOR_DONE if done else _COLOR_PENDING
	check_lbl.add_theme_font_size_override("font_size", 14)

	var cat_lbl := Label.new()
	cat_lbl.text = cat.capitalize()
	cat_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cat_lbl.modulate = _COLOR_DONE if done else _COLOR_PENDING

	var prog_lbl := Label.new()
	prog_lbl.text = "%.1f / %d min  (%d%%)" % [
		g.get("progress_min", 0.0),
		g.get("target_min", 0),
		pct,
	]
	prog_lbl.add_theme_font_size_override("font_size", 11)
	prog_lbl.modulate = _COLOR_DONE if done else Color(0.7, 0.7, 0.7)

	hbox.add_child(check_lbl)
	hbox.add_child(cat_lbl)
	hbox.add_child(prog_lbl)
	vbox.add_child(hbox)

	# ── progress bar ─────────────────────────────────────────────────────────
	var bar_bg := ColorRect.new()
	bar_bg.custom_minimum_size = Vector2(0, 6)
	bar_bg.color = _COLOR_BAR_BG
	bar_bg.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var bar_fg := ColorRect.new()
	bar_fg.color = _COLOR_BAR_DONE if done else _COLOR_BAR_FG
	bar_fg.size_flags_horizontal = Control.SIZE_FILL
	bar_fg.anchor_right = clampf(pct / 100.0, 0.0, 1.0)
	bar_fg.anchor_bottom = 1.0

	bar_bg.add_child(bar_fg)
	vbox.add_child(bar_bg)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.1)
	vbox.add_child(sep)

	return vbox
