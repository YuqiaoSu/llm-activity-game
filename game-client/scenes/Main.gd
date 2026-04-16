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
var _event_badge: Label = null   # created lazily on first active event

const _MOOD_EMOJI := {
	"happy":   "😄",
	"neutral": "😐",
	"sad":     "😔",
	"anxious": "😰",
}

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
	GameAPI.poll_summary_ready.connect(_on_poll_summary)
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
	$VBox/Buttons/InboxButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/NotificationCenter.tscn")
	)
	$VBox/Buttons/CollectionButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Collection.tscn")
	)
	$VBox/Buttons/SuggestionsButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Suggestions.tscn")
	)
	$VBox/Buttons/GoalsButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Goals.tscn")
	)
	$VBox/Buttons/RecapButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Recap.tscn")
	)
	$VBox/Buttons/CatalogueButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Catalogue.tscn")
	)
	$VBox/Buttons/LeaderboardButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Leaderboard.tscn")
	)
	$VBox/Buttons/ChartButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/DailyChart.tscn")
	)
	$VBox/Buttons/EventsButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Events.tscn")
	)
	$VBox/Buttons/HeatmapButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Heatmap.tscn")
	)
	GameAPI.active_events_updated.connect(_on_active_events)
	$AutoPollTimer.timeout.connect(_on_auto_poll_timeout)
	GameAPI.fetch_profile()
	GameAPI.fetch_active_events()


func _exit_tree() -> void:
	if GameAPI.profile_updated.is_connected(_on_profile):
		GameAPI.profile_updated.disconnect(_on_profile)
	if GameAPI.poll_completed.is_connected(_on_poll_result):
		GameAPI.poll_completed.disconnect(_on_poll_result)
	if GameAPI.poll_summary_ready.is_connected(_on_poll_summary):
		GameAPI.poll_summary_ready.disconnect(_on_poll_summary)
	if GameAPI.active_events_updated.is_connected(_on_active_events):
		GameAPI.active_events_updated.disconnect(_on_active_events)


func _on_profile(data: Dictionary) -> void:
	var stage := mini(data.get("evolution_stage", 0) as int, _STAGE_COLORS.size() - 1)
	_companion_rect.color = _STAGE_COLORS[stage]

	var level: int = data.get("level", 1)
	var next_evo = data.get("next_evolution_level", null)
	if next_evo != null:
		_evolution_label.text = "%s · evolves at Lv.%d" % [_STAGE_NAMES[stage], next_evo as int]
	else:
		_evolution_label.text = "%s (max stage)" % _STAGE_NAMES[stage]

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

	# Mood emoji prefix on the evolution label
	var mood: String = data.get("mood", "neutral")
	var emoji: String = _MOOD_EMOJI.get(mood, "😐")
	_evolution_label.text = emoji + " " + _evolution_label.text

	# Dormancy indicator
	var is_dormant: bool = data.get("is_dormant", false)
	var dormant_days: int = data.get("dormant_days", 0)
	var has_recovery: bool = data.get("has_recovery_bonus", false)
	if is_dormant:
		_evolution_label.modulate = Color(0.55, 0.55, 0.65)   # muted blue-grey
		var dormant_text := " 💤 dormant (%dd)" % dormant_days
		if has_recovery:
			dormant_text += " · 1.5× XP ready!"
		_evolution_label.text += dormant_text
	else:
		_evolution_label.modulate = Color.WHITE

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


func _on_poll_summary(summary: Dictionary) -> void:
	var total_xp: int = summary.get("total_xp", 0) as int
	if total_xp <= 0:
		return   # nothing interesting to show

	var drops: int = summary.get("drops_earned", 0) as int
	var chunks: int = summary.get("chunks_processed", 0) as int
	var by_cat: Dictionary = summary.get("xp_by_category", {}) as Dictionary

	# Build summary text
	var lines: PackedStringArray = [
		"Session Summary",
		"",
		"+%d XP total  ·  %d chunk%s  ·  %d drop%s" % [
			total_xp, chunks, "s" if chunks != 1 else "",
			drops, "s" if drops != 1 else "",
		],
	]
	for cat in by_cat:
		var xp: int = by_cat.get(cat, 0) as int
		if xp > 0:
			lines.append("  %s: +%d XP" % [str(cat).capitalize(), xp])

	# Show as a temporary overlay label at the top of the screen
	var popup := Label.new()
	popup.text = "\n".join(lines)
	popup.modulate = Color(0.9, 1.0, 0.6)
	popup.add_theme_font_size_override("font_size", 13)
	popup.position = Vector2(20, 80)
	popup.z_index = 10
	add_child(popup)

	# Auto-remove after 5 seconds
	var timer := get_tree().create_timer(5.0)
	timer.timeout.connect(func() -> void:
		if is_instance_valid(popup):
			popup.queue_free()
	)


func _on_active_events(entries: Array) -> void:
	# Show a compact badge below the XP bar when at least one event is active.
	# Badge is removed when entries is empty.
	if is_instance_valid(_event_badge):
		_event_badge.queue_free()
		_event_badge = null

	if entries.is_empty():
		return

	var lines: PackedStringArray = []
	for raw in entries:
		var ev := raw as Dictionary
		var mult: float = float(ev.get("multiplier", 1.0))
		var cat: String  = str(ev.get("category", "?")).capitalize()
		lines.append("⚡ %s  ·  %.1f× %s XP" % [ev.get("label", "Event"), mult, cat])

	_event_badge = Label.new()
	_event_badge.text = "\n".join(lines)
	_event_badge.modulate = Color(1.0, 0.9, 0.3)
	_event_badge.add_theme_font_size_override("font_size", 12)
	$VBox.add_child(_event_badge)
	# Move the badge just after the XP label (index 3 in VBox: CompanionArea=0, LevelLabel=1, XPLabel=2)
	$VBox.move_child(_event_badge, 3)
