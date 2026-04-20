# game-client/scenes/Goals.gd
extends Control

@onready var _count_label:  Label        = $VBox/Header/CountLabel
@onready var _list:         VBoxContainer = $VBox/Scroll/List
@onready var _streak_lbl:   Label        = $VBox/StreakLabel
@onready var _claim_btn:    Button       = $VBox/ClaimButton
@onready var _claim_status: Label        = $VBox/ClaimStatus

const _COLOR_DONE      := Color(0.3, 0.85, 0.3)
const _COLOR_PENDING   := Color(0.85, 0.85, 0.85)
const _COLOR_BAR_BG    := Color(0.25, 0.25, 0.25)
const _COLOR_BAR_FG    := Color(0.3, 0.7, 1.0)
const _COLOR_BAR_DONE  := Color(0.3, 0.85, 0.3)
const _COLOR_MILESTONE := Color(1.0, 0.82, 0.2)

const _RARITY_EMOJI := {"RARE": "💙", "EPIC": "💜", "LEGENDARY": "🌟"}


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.daily_goals_updated.connect(_on_goals)
	GameAPI.goal_streak_updated.connect(_on_streak)
	GameAPI.streak_reward_claimed.connect(_on_claim_result)
	_claim_btn.pressed.connect(func() -> void:
		_claim_status.text = "Claiming…"
		GameAPI.claim_streak_reward()
	)
	_claim_btn.visible = false

	# Difficulty scale row: SpinBox + "Set" button
	var diff_row := HBoxContainer.new()
	var diff_lbl := Label.new()
	diff_lbl.text = "Difficulty ×"
	diff_lbl.add_theme_font_size_override("font_size", 11)
	var diff_spin := SpinBox.new()
	diff_spin.min_value = 0.5
	diff_spin.max_value = 2.0
	diff_spin.step = 0.1
	diff_spin.value = 1.0
	diff_spin.suffix = ""
	diff_spin.custom_minimum_size = Vector2(90, 0)
	var diff_set_btn := Button.new()
	diff_set_btn.text = "Set"
	diff_set_btn.add_theme_font_size_override("font_size", 10)
	diff_set_btn.pressed.connect(func() -> void:
		GameAPI.patch_player_settings({"goal_difficulty_scale": diff_spin.value})
	)
	diff_row.add_child(diff_lbl)
	diff_row.add_child(diff_spin)
	diff_row.add_child(diff_set_btn)
	$VBox.add_child(diff_row)
	$VBox.move_child(diff_row, _claim_btn.get_index() + 1)

	GameAPI.player_settings_updated.connect(func(d: Dictionary) -> void:
		var scale: float = d.get("goal_difficulty_scale", 1.0) as float
		diff_spin.value = scale
	)
	GameAPI.fetch_player_settings()
	GameAPI.fetch_daily_goals()
	GameAPI.fetch_goal_streak()


func _exit_tree() -> void:
	if GameAPI.daily_goals_updated.is_connected(_on_goals):
		GameAPI.daily_goals_updated.disconnect(_on_goals)
	if GameAPI.goal_streak_updated.is_connected(_on_streak):
		GameAPI.goal_streak_updated.disconnect(_on_streak)
	if GameAPI.streak_reward_claimed.is_connected(_on_claim_result):
		GameAPI.streak_reward_claimed.disconnect(_on_claim_result)


func _on_streak(data: Dictionary) -> void:
	var streak: int = data.get("goal_streak", 0) as int
	var next = data.get("next_milestone_at", null)
	var days_to = data.get("days_to_milestone", null)
	var milestones: Array = data.get("milestones", [])

	if streak == 0:
		_streak_lbl.text = "Goal streak: none yet"
		_streak_lbl.modulate = Color(0.6, 0.6, 0.6)
	else:
		var streak_txt := "Goal streak: %d day%s" % [streak, "s" if streak != 1 else ""]
		if next != null:
			streak_txt += "  ·  %d to next reward" % (days_to as int)
		else:
			streak_txt += "  ·  All milestones reached!"
		_streak_lbl.text = streak_txt
		_streak_lbl.modulate = _COLOR_MILESTONE if streak >= 7 else _COLOR_PENDING

	# Show reached milestone badges
	for m in milestones:
		if not m is Dictionary:
			continue
		var md := m as Dictionary
		if md.get("reached", false):
			var days: int = md.get("days", 0) as int
			var rarity: String = str(md.get("rarity", ""))
			var emoji: String = _RARITY_EMOJI.get(rarity, "★")
			_streak_lbl.text += "\n  %s %d-day %s milestone reached!" % [emoji, days, rarity.capitalize()]


func _on_claim_result(data: Dictionary) -> void:
	var granted: bool = bool(data.get("reward_granted", false))
	if granted:
		_claim_status.text = "✓ Milestone reward granted!"
		_claim_status.modulate = _COLOR_DONE
	else:
		_claim_status.text = "No new reward (already claimed or goals not complete)"
		_claim_status.modulate = Color(0.6, 0.6, 0.6)
	GameAPI.fetch_goal_streak()
	GameAPI.fetch_daily_goals()


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
