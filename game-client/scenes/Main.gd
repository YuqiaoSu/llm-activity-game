# game-client/scenes/Main.gd
extends Control

@onready var _companion_rect: ColorRect       = $VBox/CompanionArea/CompanionRect
@onready var _evolution_label: Label          = $VBox/CompanionArea/EvolutionLabel
@onready var _level_label: Label              = $VBox/LevelLabel
@onready var _xp_label: Label                 = $VBox/XPLabel
@onready var _category_container: VBoxContainer = $VBox/CategoryContainer
@onready var _poll_status: Label              = $VBox/PollStatus
@onready var _poll_button: Button             = $VBox/Buttons/PollButton

var _is_polling: bool = false

const _STAGE_COLORS := [
	Color(0.80, 0.80, 0.90),  # 0 — Hatchling  (pale blue)
	Color(0.50, 0.80, 0.50),  # 1 — Growing    (green)
	Color(0.30, 0.60, 1.00),  # 2 — Mature     (bright blue)
	Color(0.80, 0.40, 1.00),  # 3 — Legendary  (purple)
]
const _STAGE_NAMES := ["Hatchling", "Growing", "Mature", "Legendary"]
const _MAX_XP_PER_CAT := 5000
# All categories defined on the backend (services/models/enums.py Category enum).
# Listed here so bars always appear even if a category has never been active.
const _ALL_CATEGORIES := ["WORK", "GAME", "VIDEO", "SOCIAL", "EXPLORE", "SLEEP", "SPECIAL"]


func _ready() -> void:
	GameAPI.profile_updated.connect(_on_profile)
	GameAPI.poll_completed.connect(_on_poll_result)
	_poll_button.pressed.connect(_on_poll_pressed)
	$VBox/Buttons/InventoryButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Inventory.tscn")
	)
	$VBox/Buttons/PlacesButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Places.tscn")
	)
	$VBox/Buttons/StatsButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Stats.tscn")
	)
	$VBox/Buttons/HistoryButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/History.tscn")
	)
	$VBox/Buttons/AchievementsButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Achievements.tscn")
	)
	$VBox/Buttons/ChallengesButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Challenges.tscn")
	)
	$AutoPollTimer.timeout.connect(_on_auto_poll_timeout)
	GameAPI.fetch_profile()


func _exit_tree() -> void:
	if GameAPI.profile_updated.is_connected(_on_profile):
		GameAPI.profile_updated.disconnect(_on_profile)
	if GameAPI.poll_completed.is_connected(_on_poll_result):
		GameAPI.poll_completed.disconnect(_on_poll_result)


func _on_profile(data: Dictionary) -> void:
	var stage := mini(data.get("evolution_stage", 0) as int, _STAGE_COLORS.size() - 1)
	_companion_rect.color = _STAGE_COLORS[stage]
	_evolution_label.text = _STAGE_NAMES[stage]

	var level: int = data.get("level", 1)
	_level_label.text = "Level %d" % level

	var total_xp: int = data.get("total_xp", 0)
	var xp_end = data.get("level_xp_end", null)
	var xp_line: String
	if xp_end != null:
		var xp_start: int = data.get("level_xp_start", 0)
		var progress: int = total_xp - xp_start
		var needed: int   = (xp_end as int) - xp_start
		xp_line = "%d XP  ·  %d / %d to level %d" % [total_xp, progress, needed, level + 1]
	else:
		xp_line = "%d XP  ·  Max level!" % total_xp
	var streak_days: int = data.get("streak_days", 0)
	if streak_days >= 2:
		xp_line += "  ·  %d-day streak" % streak_days
	_xp_label.text = xp_line

	_rebuild_xp_bars(data.get("category_xp", {}) as Dictionary)


func _rebuild_xp_bars(category_xp: Dictionary) -> void:
	for child in _category_container.get_children():
		child.queue_free()
	for category: String in _ALL_CATEGORIES:
		var hbox := HBoxContainer.new()
		var lbl := Label.new()
		lbl.text = category.capitalize()
		lbl.custom_minimum_size.x = 80
		var bar := ProgressBar.new()
		bar.max_value = _MAX_XP_PER_CAT
		var raw = category_xp.get(category, 0)
		if not (raw is int or raw is float):
			push_warning("Main: unexpected XP type for '%s'" % category)
			raw = 0
		bar.value = int(raw)
		bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		bar.show_percentage = false
		hbox.add_child(lbl)
		hbox.add_child(bar)
		_category_container.add_child(hbox)


func _on_poll_pressed() -> void:
	if _is_polling:
		return
	_is_polling = true
	_poll_button.disabled = true
	_poll_status.text = "Checking..."
	GameAPI.poll_now()


func _on_auto_poll_timeout() -> void:
	if _is_polling:
		return
	_is_polling = true
	GameAPI.poll_now()


func _on_poll_result(result: String) -> void:
	_is_polling = false
	_poll_button.disabled = false
	match result:
		"OK":
			_poll_status.text = "Rewards processed!"
			GameAPI.fetch_profile()
		"NO_NEW_CHUNKS":
			_poll_status.text = "No new activity"
		"ON_COOLDOWN":
			_poll_status.text = "On cooldown — try again shortly"
		_:
			_poll_status.text = "Sync error — is the tracker running?"
