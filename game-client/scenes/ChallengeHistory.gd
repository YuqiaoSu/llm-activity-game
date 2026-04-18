# game-client/scenes/ChallengeHistory.gd
extends Control

@onready var _list: VBoxContainer = $VBox/Scroll/List

const _GOLD  := Color(1.00, 0.84, 0.00)
const _GREEN := Color(0.30, 0.85, 0.30)
const _DIM   := Color(0.55, 0.55, 0.55)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Challenges.tscn")
	)
	GameAPI.challenge_history_updated.connect(_on_history)
	GameAPI.fetch_challenge_history(12)


func _exit_tree() -> void:
	if GameAPI.challenge_history_updated.is_connected(_on_history):
		GameAPI.challenge_history_updated.disconnect(_on_history)


func _on_history(entries: Array) -> void:
	for child in _list.get_children():
		child.queue_free()

	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "No challenge history yet. Complete some challenges!"
		lbl.modulate = _DIM
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD
		_list.add_child(lbl)
		return

	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var hbox := HBoxContainer.new()
	hbox.add_theme_constant_override("separation", 8)

	var all_complete: bool    = entry.get("all_complete", false)
	var completed_count: int  = entry.get("completed_count", 0)
	var total_count: int      = entry.get("total_count", 0)
	var week_start: String    = entry.get("week_start", "?")

	var badge := Label.new()
	badge.text = "★" if all_complete else "·"
	badge.modulate = _GOLD if all_complete else _DIM
	badge.custom_minimum_size.x = 16

	var week_lbl := Label.new()
	week_lbl.text = "Week of %s" % week_start
	week_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	week_lbl.modulate = _GOLD if all_complete else Color.WHITE

	var count_lbl := Label.new()
	count_lbl.text = "%d / %d" % [completed_count, total_count]
	count_lbl.modulate = _GREEN if all_complete else _DIM

	hbox.add_child(badge)
	hbox.add_child(week_lbl)
	hbox.add_child(count_lbl)
	return hbox
