# game-client/scenes/Suggestions.gd
extends Control

@onready var _count_label: Label        = $VBox/Header/CountLabel
@onready var _list: VBoxContainer       = $VBox/Scroll/List

const _COLOR_STREAK  := Color(1.0, 0.35, 0.35)   # red — urgent
const _COLOR_GAP     := Color(1.0, 0.78, 0.2)    # amber — warning
const _COLOR_NUDGE   := Color(0.35, 0.85, 0.95)  # cyan — informational
const _COLOR_DIVERSIFY := Color(0.75, 0.5, 1.0)  # purple — creative

const _TYPE_LABEL := {
	"streak_danger": "Streak",
	"gap":           "Gap",
	"challenge_nudge": "Challenge",
	"diversify":     "Diversify",
}


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.suggestions_updated.connect(_on_suggestions)
	GameAPI.fetch_suggestions()


func _exit_tree() -> void:
	if GameAPI.suggestions_updated.is_connected(_on_suggestions):
		GameAPI.suggestions_updated.disconnect(_on_suggestions)


func _on_suggestions(entries: Array) -> void:
	_count_label.text = "Suggestions (%d)" % entries.size()
	for child in _list.get_children():
		child.queue_free()
	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "  All caught up — keep going!"
		lbl.modulate = Color(0.6, 0.6, 0.6)
		_list.add_child(lbl)
		return
	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(s: Dictionary) -> Control:
	var stype: String = s.get("type", "")
	var color := _type_color(stype)

	var vbox := VBoxContainer.new()

	# ── type badge + text ─────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var badge := Label.new()
	badge.text = "[%s]" % _TYPE_LABEL.get(stype, stype.capitalize())
	badge.modulate = color
	badge.add_theme_font_size_override("font_size", 11)
	badge.custom_minimum_size = Vector2(90, 0)

	var text_lbl := Label.new()
	text_lbl.text = s.get("text", "")
	text_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	hbox.add_child(badge)
	hbox.add_child(text_lbl)
	vbox.add_child(hbox)

	# ── target minutes chip ───────────────────────────────────────────────────
	var target_min: int = s.get("target_min", 0)
	var cat: String = s.get("category", "")
	if target_min > 0:
		var meta_lbl := Label.new()
		var meta_parts: Array[String] = []
		if cat != "":
			meta_parts.append("Category: %s" % cat.capitalize())
		meta_parts.append("Goal: %d min" % target_min)
		meta_lbl.text = "  " + " · ".join(meta_parts)
		meta_lbl.modulate = Color(0.65, 0.65, 0.65)
		meta_lbl.add_theme_font_size_override("font_size", 11)
		vbox.add_child(meta_lbl)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.12)
	vbox.add_child(sep)

	return vbox


func _type_color(stype: String) -> Color:
	match stype:
		"streak_danger":   return _COLOR_STREAK
		"gap":             return _COLOR_GAP
		"challenge_nudge": return _COLOR_NUDGE
		"diversify":       return _COLOR_DIVERSIFY
	return Color(0.75, 0.75, 0.75)
