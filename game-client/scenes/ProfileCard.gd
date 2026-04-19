# game-client/scenes/ProfileCard.gd
# Player profile card: companion portrait, stats, top categories, pinned achievements.
extends Control

@onready var _companion_rect: ColorRect    = $VBox/CompanionArea/CompanionRect
@onready var _stage_label: Label           = $VBox/CompanionArea/StageLabel
@onready var _name_label: Label            = $VBox/NameLabel
@onready var _level_label: Label           = $VBox/LevelLabel
@onready var _xp_label: Label             = $VBox/XPLabel
@onready var _streak_label: Label          = $VBox/StreakLabel
@onready var _sparkline_container: HBoxContainer = $VBox/SparklineContainer
@onready var _poll_button: Button          = $VBox/PollRow/PollButton
@onready var _poll_status: Label           = $VBox/PollRow/PollStatus
@onready var _top_cats_list: VBoxContainer = $VBox/TopCatsList
@onready var _pinned_list: HBoxContainer   = $VBox/PinnedList
@onready var _pinned_details: VBoxContainer = $VBox/Scroll/PinnedDetails

var _is_polling: bool = false
var _titles_container: VBoxContainer = null
var _rename_row: HBoxContainer = null
var _current_name: String = ""
var _eta_label: Label = null
var _goal_bar: ProgressBar = null
var _goal_label: Label = null
var _daily_xp_target: int = 100
var _today_xp: int = 0

const _STAGE_COLORS := [
	Color(0.80, 0.80, 0.90),
	Color(0.50, 0.80, 0.50),
	Color(0.30, 0.60, 1.00),
	Color(0.80, 0.40, 1.00),
]
const _STAGE_NAMES := ["Hatchling", "Growing", "Mature", "Legendary"]
const _MOOD_EMOJI := {
	"happy":   "😄",
	"neutral": "😐",
	"sad":     "😔",
	"anxious": "😰",
}
const _COLOR_PINNED  := Color(0.30, 0.80, 1.00)
const _COLOR_MUTED   := Color(0.45, 0.45, 0.45)
const _COLOR_GOLD    := Color(1.00, 0.84, 0.00)
const _MAX_PINS      := 3


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.profile_updated.connect(_on_profile)
	GameAPI.pinned_achievements_updated.connect(_on_pinned)
	GameAPI.poll_completed.connect(_on_poll_result)
	GameAPI.daily_stats_updated.connect(_on_daily_stats)
	GameAPI.titles_updated.connect(_on_titles)
	GameAPI.focus_streak_updated.connect(_on_focus_streak)
	GameAPI.xp_projection_updated.connect(_on_xp_projection)
	GameAPI.player_settings_updated.connect(_on_player_settings)
	_poll_button.pressed.connect(_on_poll_pressed)

	# Build rename row once; insert after NameLabel in VBox
	_rename_row = HBoxContainer.new()
	_rename_row.visible = false
	var name_edit := LineEdit.new()
	name_edit.name = "NameEdit"
	name_edit.placeholder_text = "New name…"
	name_edit.custom_minimum_size.x = 120
	_rename_row.add_child(name_edit)
	var save_btn := Button.new()
	save_btn.text = "Save"
	save_btn.pressed.connect(func() -> void:
		var new_name: String = name_edit.text.strip_edges()
		if new_name.length() >= 1 and new_name.length() <= 24:
			GameAPI.rename_player(new_name)
		_rename_row.visible = false
		_name_label.visible = true
	)
	_rename_row.add_child(save_btn)
	var cancel_btn := Button.new()
	cancel_btn.text = "Cancel"
	cancel_btn.pressed.connect(func() -> void:
		_rename_row.visible = false
		_name_label.visible = true
	)
	_rename_row.add_child(cancel_btn)
	$VBox.add_child(_rename_row)
	$VBox.move_child(_rename_row, _name_label.get_index() + 1)

	# ETA label: created here, positioned right after XPLabel
	_eta_label = Label.new()
	_eta_label.add_theme_font_size_override("font_size", 11)
	_eta_label.modulate = _COLOR_MUTED
	$VBox.add_child(_eta_label)
	$VBox.move_child(_eta_label, _xp_label.get_index() + 1)

	# Daily goal bar: label + ProgressBar, inserted after StreakLabel
	_goal_label = Label.new()
	_goal_label.add_theme_font_size_override("font_size", 11)
	_goal_label.modulate = Color(0.70, 0.90, 0.70)
	_goal_label.text = "Daily goal: — XP"
	_goal_bar = ProgressBar.new()
	_goal_bar.min_value = 0
	_goal_bar.max_value = 100
	_goal_bar.value = 0
	_goal_bar.custom_minimum_size.y = 8
	$VBox.add_child(_goal_label)
	$VBox.add_child(_goal_bar)
	$VBox.move_child(_goal_label, _streak_label.get_index() + 1)
	$VBox.move_child(_goal_bar, _goal_label.get_index() + 1)

	_name_label.mouse_filter = Control.MOUSE_FILTER_STOP
	_name_label.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
			name_edit.text = ""
			name_edit.placeholder_text = _current_name
			_rename_row.visible = true
			_name_label.visible = false
			name_edit.grab_focus()
	)

	GameAPI.fetch_profile()
	GameAPI.fetch_pinned_achievements()
	GameAPI.fetch_daily_stats(7)
	GameAPI.fetch_titles()
	GameAPI.fetch_focus_streak()
	GameAPI.fetch_xp_projection()
	GameAPI.fetch_player_settings()


func _exit_tree() -> void:
	if GameAPI.profile_updated.is_connected(_on_profile):
		GameAPI.profile_updated.disconnect(_on_profile)
	if GameAPI.pinned_achievements_updated.is_connected(_on_pinned):
		GameAPI.pinned_achievements_updated.disconnect(_on_pinned)
	if GameAPI.poll_completed.is_connected(_on_poll_result):
		GameAPI.poll_completed.disconnect(_on_poll_result)
	if GameAPI.daily_stats_updated.is_connected(_on_daily_stats):
		GameAPI.daily_stats_updated.disconnect(_on_daily_stats)
	if GameAPI.titles_updated.is_connected(_on_titles):
		GameAPI.titles_updated.disconnect(_on_titles)
	if GameAPI.focus_streak_updated.is_connected(_on_focus_streak):
		GameAPI.focus_streak_updated.disconnect(_on_focus_streak)
	if GameAPI.xp_projection_updated.is_connected(_on_xp_projection):
		GameAPI.xp_projection_updated.disconnect(_on_xp_projection)
	if GameAPI.player_settings_updated.is_connected(_on_player_settings):
		GameAPI.player_settings_updated.disconnect(_on_player_settings)


func _on_poll_pressed() -> void:
	if _is_polling:
		return
	_is_polling = true
	_poll_button.disabled = true
	_poll_status.text = "Checking…"
	GameAPI.poll_now()


func _on_poll_result(result: String) -> void:
	_is_polling = false
	_poll_button.disabled = false
	match result:
		"OK":
			_poll_status.text = "✓ Rewards processed!"
			_poll_status.modulate = Color(0.3, 0.85, 0.3)
			GameAPI.fetch_profile()
			GameAPI.fetch_pinned_achievements()
		"NO_NEW_CHUNKS":
			_poll_status.text = "No new activity"
			_poll_status.modulate = Color(0.6, 0.6, 0.6)
		"ON_COOLDOWN":
			_poll_status.text = "On cooldown — try again shortly"
			_poll_status.modulate = Color(0.8, 0.5, 0.2)
		_:
			_poll_status.text = "Sync error"
			_poll_status.modulate = Color(0.9, 0.3, 0.3)


func _on_profile(data: Dictionary) -> void:
	var stage := mini(data.get("evolution_stage", 0) as int, _STAGE_COLORS.size() - 1)
	_companion_rect.color = _STAGE_COLORS[stage]

	var mood: String = data.get("mood", "neutral")
	var emoji: String = _MOOD_EMOJI.get(mood, "😐")
	var next_evo = data.get("next_evolution_level", null)
	if next_evo != null:
		_stage_label.text = "%s %s\nevolves @ Lv.%d" % [emoji, _STAGE_NAMES[stage], next_evo as int]
	else:
		_stage_label.text = "%s %s\n(max stage)" % [emoji, _STAGE_NAMES[stage]]

	_current_name = data.get("name", "Player")
	_name_label.text = _current_name + "  ✏"

	var level: int = data.get("level", 1)
	_level_label.text = "Level %d" % level

	var total_xp: int = data.get("total_xp", 0) as int
	var xp_end = data.get("level_xp_end", null)
	if xp_end != null:
		var xp_start: int = data.get("level_xp_start", 0) as int
		var progress: int = total_xp - xp_start
		var needed: int   = (xp_end as int) - xp_start
		_xp_label.text = "%d XP  ·  %d / %d to Lv.%d" % [total_xp, progress, needed, level + 1]
	else:
		_xp_label.text = "%d XP  ·  Max level!" % total_xp

	var streak: int = data.get("streak_days", 0) as int
	if streak == 0:
		_streak_label.text = "Streak: none yet"
		_streak_label.modulate = _COLOR_MUTED
	else:
		_streak_label.text = "🔥 %d-day streak" % streak
		_streak_label.modulate = _COLOR_GOLD if streak >= 7 else Color.WHITE

	_rebuild_top_cats(data.get("category_xp", {}) as Dictionary)


func _rebuild_top_cats(category_xp: Dictionary) -> void:
	for child in _top_cats_list.get_children():
		child.queue_free()

	var pairs: Array = []
	for cat in category_xp:
		pairs.append([cat, int(category_xp[cat])])
	pairs.sort_custom(func(a, b): return a[1] > b[1])

	var shown := 0
	for pair in pairs:
		if shown >= 3:
			break
		var xp: int = pair[1]
		if xp <= 0:
			break
		var hbox := HBoxContainer.new()
		var lbl := Label.new()
		lbl.text = str(pair[0]).capitalize()
		lbl.custom_minimum_size.x = 80
		var xp_lbl := Label.new()
		xp_lbl.text = "%d XP" % xp
		xp_lbl.modulate = Color(0.8, 0.9, 1.0)
		hbox.add_child(lbl)
		hbox.add_child(xp_lbl)
		_top_cats_list.add_child(hbox)
		shown += 1

	if shown == 0:
		var lbl := Label.new()
		lbl.text = "No activity yet"
		lbl.modulate = _COLOR_MUTED
		_top_cats_list.add_child(lbl)


func _on_pinned(entries: Array) -> void:
	_rebuild_pinned_cards(entries)
	_rebuild_pinned_details(entries)


func _rebuild_pinned_cards(entries: Array) -> void:
	for child in _pinned_list.get_children():
		child.queue_free()

	for raw in entries:
		if not raw is Dictionary:
			continue
		var entry := raw as Dictionary
		var panel := PanelContainer.new()
		panel.custom_minimum_size = Vector2(90, 55)
		var vbox := VBoxContainer.new()
		var name_lbl := Label.new()
		name_lbl.text = entry.get("name", "?")
		name_lbl.modulate = _COLOR_PINNED
		name_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		var date_lbl := Label.new()
		date_lbl.text = _short_date(str(entry.get("unlocked_at", "")))
		date_lbl.add_theme_font_size_override("font_size", 10)
		date_lbl.modulate = _COLOR_MUTED
		vbox.add_child(name_lbl)
		vbox.add_child(date_lbl)
		panel.add_child(vbox)
		_pinned_list.add_child(panel)

	for _i in range(entries.size(), _MAX_PINS):
		var slot := PanelContainer.new()
		slot.custom_minimum_size = Vector2(90, 55)
		var lbl := Label.new()
		lbl.text = "—"
		lbl.modulate = _COLOR_MUTED
		lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		slot.add_child(lbl)
		_pinned_list.add_child(slot)


func _rebuild_pinned_details(entries: Array) -> void:
	for child in _pinned_details.get_children():
		child.queue_free()

	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "No achievements pinned yet. Visit the Achievements screen to pin up to 3."
		lbl.modulate = _COLOR_MUTED
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_pinned_details.add_child(lbl)
		return

	for raw in entries:
		if not raw is Dictionary:
			continue
		var entry := raw as Dictionary
		var vbox := VBoxContainer.new()

		var hbox := HBoxContainer.new()
		var star := Label.new()
		star.text = "★"
		star.modulate = _COLOR_GOLD
		var name_lbl := Label.new()
		name_lbl.text = entry.get("name", "?")
		name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		name_lbl.modulate = _COLOR_PINNED
		var date_lbl := Label.new()
		date_lbl.text = _short_date(str(entry.get("unlocked_at", "")))
		date_lbl.modulate = _COLOR_MUTED
		hbox.add_child(star)
		hbox.add_child(name_lbl)
		hbox.add_child(date_lbl)

		var desc_lbl := Label.new()
		desc_lbl.text = "  " + entry.get("description", "")
		desc_lbl.modulate = Color(0.75, 0.75, 0.75)
		desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

		var sep := HSeparator.new()
		sep.modulate = Color(1, 1, 1, 0.12)

		vbox.add_child(hbox)
		vbox.add_child(desc_lbl)
		vbox.add_child(sep)
		_pinned_details.add_child(vbox)


func _on_player_settings(data: Dictionary) -> void:
	_daily_xp_target = data.get("daily_xp_target", 100) as int
	_update_goal_bar()


func _update_goal_bar() -> void:
	if _goal_bar == null or _goal_label == null:
		return
	_goal_label.text = "Daily goal: %d / %d XP" % [_today_xp, _daily_xp_target]
	_goal_bar.max_value = max(1, _daily_xp_target)
	_goal_bar.value = mini(_today_xp, _daily_xp_target)
	if _today_xp >= _daily_xp_target:
		_goal_label.modulate = Color(0.30, 0.90, 0.30)   # bright green = goal met
	else:
		_goal_label.modulate = Color(0.70, 0.90, 0.70)   # muted green = in progress


func _on_daily_stats(entries: Array) -> void:
	_make_sparkline(entries)
	# Extract today's XP from the entries (newest first; entries[0] = today)
	if entries.size() > 0:
		var today := entries[0] as Dictionary
		_today_xp = today.get("total_xp", 0) as int
		_update_goal_bar()


func _make_sparkline(entries: Array) -> void:
	for child in _sparkline_container.get_children():
		child.queue_free()

	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "no data"
		lbl.modulate = _COLOR_MUTED
		_sparkline_container.add_child(lbl)
		return

	# entries are newest-first from the API; reverse so oldest is left
	var days: Array = entries.duplicate()
	days.reverse()
	# Use only the last 7 days
	if days.size() > 7:
		days = days.slice(days.size() - 7)

	var max_xp: int = 1
	for raw in days:
		var xp: int = (raw as Dictionary).get("total_xp", 0) as int
		if xp > max_xp:
			max_xp = xp

	const MAX_BAR_H := 32
	const BAR_W     := 18
	const BAR_GAP   := 3
	var today_idx := days.size() - 1

	for i in range(days.size()):
		var day := days[i] as Dictionary
		var xp: int = day.get("total_xp", 0) as int
		var bar_h: int = max(2, int(float(xp) / float(max_xp) * MAX_BAR_H))

		var col := _COLOR_GOLD if i == today_idx else Color(0.4, 0.7, 1.0)

		var vbox := VBoxContainer.new()
		vbox.custom_minimum_size = Vector2(BAR_W, MAX_BAR_H + 4)
		vbox.alignment = BoxContainer.ALIGNMENT_END

		var bar := ColorRect.new()
		bar.color = col
		bar.custom_minimum_size = Vector2(BAR_W, bar_h)
		bar.size_flags_vertical = Control.SIZE_SHRINK_END

		vbox.add_child(bar)
		_sparkline_container.add_child(vbox)

		if i < days.size() - 1:
			var gap := Control.new()
			gap.custom_minimum_size = Vector2(BAR_GAP, 0)
			_sparkline_container.add_child(gap)


func _on_xp_projection(data: Dictionary) -> void:
	if _eta_label == null:
		return
	if data.get("at_max_level", false):
		_eta_label.text = "Max level reached!"
		_eta_label.modulate = _COLOR_GOLD
		return
	var eta_days = data.get("eta_days", null)
	var eta_date = data.get("eta_date", null)
	if eta_days == null:
		_eta_label.text = "No recent activity — keep going!"
		_eta_label.modulate = _COLOR_MUTED
	else:
		var lvl_label: String = _level_label.text  # e.g. "Level 3"
		_eta_label.text = "At this pace: next level in ~%d day(s) (by %s)" % [eta_days as int, str(eta_date).left(10)]
		_eta_label.modulate = Color(0.70, 0.90, 1.00)


func _on_focus_streak(data: Dictionary) -> void:
	var streak: int = data.get("focus_streak", 0) as int
	if streak <= 0:
		return
	if _titles_container == null:
		# Titles section not yet built; it will show focus streak when _on_titles fires
		return
	# Append or update focus streak badge after title list
	var fid := "focus_streak_badge"
	for child in _titles_container.get_children():
		if child.name == fid:
			child.queue_free()
	var badge := Label.new()
	badge.name = fid
	var next_at = data.get("next_reward_at", null)
	if next_at != null:
		badge.text = "🎯 Focus streak: %d day(s) · reward at %d" % [streak, next_at as int]
	else:
		badge.text = "🎯 Focus streak: %d day(s) · milestone reached!" % streak
	badge.modulate = Color(0.40, 0.85, 1.00)
	badge.add_theme_font_size_override("font_size", 11)
	_titles_container.add_child(badge)


func _on_titles(entries: Array) -> void:
	if _titles_container == null:
		var sep := HSeparator.new()
		sep.modulate = Color(1, 1, 1, 0.15)
		$VBox/Scroll/PinnedDetails.add_child(sep)

		var header := Label.new()
		header.text = "Titles"
		header.add_theme_font_size_override("font_size", 13)
		header.modulate = Color(0.85, 0.85, 0.85)
		$VBox/Scroll/PinnedDetails.add_child(header)

		_titles_container = VBoxContainer.new()
		$VBox/Scroll/PinnedDetails.add_child(_titles_container)

	for child in _titles_container.get_children():
		child.queue_free()

	var equipped_title := ""
	for raw in entries:
		if (raw as Dictionary).get("equipped", false):
			equipped_title = (raw as Dictionary).get("label", "")

	if equipped_title != "":
		var badge_row := HBoxContainer.new()
		var badge_lbl := Label.new()
		badge_lbl.text = "★ " + equipped_title
		badge_lbl.modulate = _COLOR_GOLD
		badge_lbl.add_theme_font_size_override("font_size", 13)
		badge_row.add_child(badge_lbl)
		_titles_container.add_child(badge_row)

	for raw in entries:
		var entry := raw as Dictionary
		var hbox := HBoxContainer.new()
		var check := Label.new()
		check.text = "✓" if entry.get("earned", false) else "✗"
		check.modulate = Color(0.3, 0.85, 0.3) if entry.get("earned", false) else _COLOR_MUTED
		check.custom_minimum_size.x = 18
		var lbl := Label.new()
		lbl.text = entry.get("label", "")
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if entry.get("equipped", false):
			lbl.modulate = _COLOR_GOLD
		elif not entry.get("earned", false):
			lbl.modulate = _COLOR_MUTED
		hbox.add_child(check)
		hbox.add_child(lbl)
		_titles_container.add_child(hbox)


func _short_date(iso: String) -> String:
	if iso.length() >= 10:
		return iso.left(10)
	return iso
