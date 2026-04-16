# game-client/scenes/Achievements.gd
extends Control

@onready var _count_label: Label           = $VBox/Header/CountLabel
@onready var _achievement_list: VBoxContainer = $VBox/Scroll/AchievementList

const _COLOR_UNLOCKED := Color(1.00, 0.84, 0.00)  # gold
const _COLOR_LOCKED   := Color(0.40, 0.40, 0.40)  # grey


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.achievements_updated.connect(_on_achievements)
	GameAPI.fetch_achievements()


func _exit_tree() -> void:
	if GameAPI.achievements_updated.is_connected(_on_achievements):
		GameAPI.achievements_updated.disconnect(_on_achievements)


func _on_achievements(entries: Array) -> void:
	var unlocked_count := 0
	for raw in entries:
		if raw is Dictionary and (raw as Dictionary).get("unlocked", false):
			unlocked_count += 1
	_count_label.text = "Achievements (%d / %d)" % [unlocked_count, entries.size()]

	for child in _achievement_list.get_children():
		child.queue_free()
	for raw in entries:
		if raw is Dictionary:
			_achievement_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var unlocked: bool = entry.get("unlocked", false)

	var vbox := VBoxContainer.new()

	# ── main row ────────────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(12, 12)
	dot.color = _COLOR_UNLOCKED if unlocked else _COLOR_LOCKED

	var name_lbl := Label.new()
	name_lbl.text = ("✓ " if unlocked else "  ") + entry.get("name", "?")
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.modulate = _COLOR_UNLOCKED if unlocked else _COLOR_LOCKED

	var status_lbl := Label.new()
	if unlocked:
		var ts: String = entry.get("unlocked_at", "")
		status_lbl.text = _format_date(ts)
		status_lbl.modulate = _COLOR_UNLOCKED
	else:
		var ctype: String = entry.get("condition_type", "")
		var threshold: int = entry.get("threshold", 0)
		status_lbl.text = _condition_hint(ctype, threshold)
		status_lbl.modulate = _COLOR_LOCKED

	hbox.add_child(dot)
	hbox.add_child(name_lbl)
	hbox.add_child(status_lbl)
	vbox.add_child(hbox)

	# ── description (smaller, indented) ─────────────────────────────────────
	var desc_lbl := Label.new()
	desc_lbl.text = "    " + entry.get("description", "")
	desc_lbl.modulate = Color(0.70, 0.70, 0.70) if not unlocked else Color(0.90, 0.90, 0.90)
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vbox.add_child(desc_lbl)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.12)
	vbox.add_child(sep)

	return vbox


func _condition_hint(ctype: String, threshold: int) -> String:
	match ctype:
		"total_xp":        return "%d XP needed" % threshold
		"level":           return "Reach level %d" % threshold
		"streak":          return "%d-day streak" % threshold
		"items_collected": return "Collect %d items" % threshold
		_:                 return ""


func _format_date(iso: String) -> String:
	# iso is like "2026-04-15T09:30:00+00:00" — show YYYY-MM-DD
	if iso.length() >= 10:
		return iso.left(10)
	return iso
