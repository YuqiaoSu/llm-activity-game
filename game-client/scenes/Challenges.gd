# game-client/scenes/Challenges.gd
extends Control

@onready var _count_label: Label            = $VBox/Header/CountLabel
@onready var _challenge_list: VBoxContainer = $VBox/Scroll/ChallengeList

const _COLOR_DONE     := Color(0.20, 0.80, 1.00)  # cyan-blue
const _COLOR_PROGRESS := Color(0.85, 0.85, 0.85)  # light grey
const _COLOR_LOCKED   := Color(0.45, 0.45, 0.45)  # dim grey


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.challenges_updated.connect(_on_challenges)
	GameAPI.fetch_challenges()


func _exit_tree() -> void:
	if GameAPI.challenges_updated.is_connected(_on_challenges):
		GameAPI.challenges_updated.disconnect(_on_challenges)


func _on_challenges(entries: Array) -> void:
	var done_count := 0
	for raw in entries:
		if raw is Dictionary and (raw as Dictionary).get("completed", false):
			done_count += 1
	_count_label.text = "Challenges (%d / %d done this week)" % [done_count, entries.size()]

	for child in _challenge_list.get_children():
		child.queue_free()
	for raw in entries:
		if raw is Dictionary:
			_challenge_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var completed: bool = entry.get("completed", false)
	var progress: int   = entry.get("progress", 0)
	var threshold: int  = entry.get("threshold", 1)
	var metric: String  = entry.get("metric", "xp")

	var vbox := VBoxContainer.new()

	# ── main row ─────────────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(12, 12)
	dot.color = _COLOR_DONE if completed else _COLOR_PROGRESS

	var name_lbl := Label.new()
	name_lbl.text = ("✓ " if completed else "  ") + entry.get("name", "?")
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.modulate = _COLOR_DONE if completed else _COLOR_PROGRESS

	var status_lbl := Label.new()
	if completed:
		status_lbl.text = "Done!"
		status_lbl.modulate = _COLOR_DONE
	else:
		status_lbl.text = _progress_text(progress, threshold, metric)
		status_lbl.modulate = _COLOR_LOCKED

	hbox.add_child(dot)
	hbox.add_child(name_lbl)
	hbox.add_child(status_lbl)
	vbox.add_child(hbox)

	# ── description (smaller, indented) ──────────────────────────────────────
	var desc_lbl := Label.new()
	desc_lbl.text = "    " + entry.get("description", "")
	desc_lbl.modulate = Color(0.65, 0.65, 0.65) if not completed else Color(0.85, 0.85, 0.85)
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vbox.add_child(desc_lbl)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.12)
	vbox.add_child(sep)

	return vbox


func _progress_text(progress: int, threshold: int, metric: String) -> String:
	match metric:
		"xp":        return "%d / %d XP" % [progress, threshold]
		"total_xp":  return "%d / %d total XP" % [progress, threshold]
		"categories": return "%d / %d categories" % [progress, threshold]
		_:           return "%d / %d" % [progress, threshold]
