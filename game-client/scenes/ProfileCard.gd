# game-client/scenes/ProfileCard.gd
# Player profile card: companion portrait, stats, top categories, pinned achievements.
extends Control

@onready var _companion_rect: ColorRect    = $VBox/CompanionArea/CompanionRect
@onready var _stage_label: Label           = $VBox/CompanionArea/StageLabel
@onready var _name_label: Label            = $VBox/NameLabel
@onready var _level_label: Label           = $VBox/LevelLabel
@onready var _xp_label: Label             = $VBox/XPLabel
@onready var _streak_label: Label          = $VBox/StreakLabel
@onready var _poll_button: Button          = $VBox/PollRow/PollButton
@onready var _poll_status: Label           = $VBox/PollRow/PollStatus
@onready var _top_cats_list: VBoxContainer = $VBox/TopCatsList
@onready var _pinned_list: HBoxContainer   = $VBox/PinnedList
@onready var _pinned_details: VBoxContainer = $VBox/Scroll/PinnedDetails

var _is_polling: bool = false

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
	_poll_button.pressed.connect(_on_poll_pressed)
	GameAPI.fetch_profile()
	GameAPI.fetch_pinned_achievements()


func _exit_tree() -> void:
	if GameAPI.profile_updated.is_connected(_on_profile):
		GameAPI.profile_updated.disconnect(_on_profile)
	if GameAPI.pinned_achievements_updated.is_connected(_on_pinned):
		GameAPI.pinned_achievements_updated.disconnect(_on_pinned)
	if GameAPI.poll_completed.is_connected(_on_poll_result):
		GameAPI.poll_completed.disconnect(_on_poll_result)


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

	_name_label.text = data.get("name", "Player")

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


func _short_date(iso: String) -> String:
	if iso.length() >= 10:
		return iso.left(10)
	return iso
