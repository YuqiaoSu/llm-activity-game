# game-client/scenes/Main.gd
extends Control

@onready var _companion_rect: ColorRect       = $VBox/CompanionArea/CompanionRect
@onready var _evolution_label: Label          = $VBox/CompanionArea/EvolutionLabel
@onready var _level_label: Label              = $VBox/LevelLabel
@onready var _xp_label: Label                 = $VBox/XPLabel
@onready var _category_container: VBoxContainer = $VBox/CategoryContainer
@onready var _poll_status: Label              = $VBox/PollStatus
@onready var _poll_button: Button             = $VBox/Buttons/PollButton

const _STAGE_COLORS := [
	Color(0.80, 0.80, 0.90),  # 0 — Hatchling  (pale blue)
	Color(0.50, 0.80, 0.50),  # 1 — Growing    (green)
	Color(0.30, 0.60, 1.00),  # 2 — Mature     (bright blue)
	Color(0.80, 0.40, 1.00),  # 3 — Legendary  (purple)
]
const _STAGE_NAMES := ["Hatchling", "Growing", "Mature", "Legendary"]
const _MAX_XP_PER_CAT := 5000


func _ready() -> void:
	GameAPI.profile_updated.connect(_on_profile)
	GameAPI.poll_completed.connect(_on_poll_result)
	_poll_button.pressed.connect(_on_poll_pressed)
	$VBox/Buttons/InventoryButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Inventory.tscn")
	)
	GameAPI.fetch_profile()


func _on_profile(data: Dictionary) -> void:
	var stage := mini(data.get("evolution_stage", 0) as int, _STAGE_COLORS.size() - 1)
	_companion_rect.color = _STAGE_COLORS[stage]
	_evolution_label.text = _STAGE_NAMES[stage]
	_level_label.text = "Level %d" % data.get("level", 1)
	_xp_label.text = "%d XP total" % data.get("total_xp", 0)
	_rebuild_xp_bars(data.get("category_xp", {}) as Dictionary)


func _rebuild_xp_bars(category_xp: Dictionary) -> void:
	for child in _category_container.get_children():
		child.queue_free()
	for category: String in category_xp:
		var hbox := HBoxContainer.new()
		var lbl := Label.new()
		lbl.text = category.capitalize()
		lbl.custom_minimum_size.x = 80
		var bar := ProgressBar.new()
		bar.max_value = _MAX_XP_PER_CAT
		bar.value = category_xp[category] as int
		bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		bar.show_percentage = false
		hbox.add_child(lbl)
		hbox.add_child(bar)
		_category_container.add_child(hbox)


func _on_poll_pressed() -> void:
	_poll_button.disabled = true
	_poll_status.text = "Checking..."
	GameAPI.poll_now()


func _on_poll_result(result: String) -> void:
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
