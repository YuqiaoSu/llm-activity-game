# game-client/scenes/PlayerJournal.gd
extends Control

@onready var _list:      VBoxContainer = $VBox/Scroll/List
@onready var _count_lbl: Label         = $VBox/Header/CountLabel

const _EVENT_COLOR := {
	"item_drop":         Color(0.90, 0.70, 0.25),
	"level_up":          Color(0.40, 0.80, 1.00),
	"achievement_unlock":Color(1.00, 0.84, 0.00),
	"place_unlock":      Color(0.70, 0.55, 1.00),
	"place_level_up":    Color(0.70, 0.55, 1.00),
	"xp_milestone":      Color(0.55, 1.00, 0.55),
	"streak_milestone":  Color(1.00, 0.55, 0.20),
	"recovery_gift":     Color(0.90, 0.50, 1.00),
	"daily_goal_hit":    Color(0.30, 1.00, 0.70),
	"challenge_progress":Color(0.55, 0.85, 1.00),
}
const _COLOR_DIM  := Color(0.55, 0.55, 0.55)
const _COLOR_DATE := Color(0.45, 0.45, 0.45)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/ProfileCard.tscn")
	)
	GameAPI.player_journal_updated.connect(_on_journal)
	GameAPI.fetch_player_journal(30)


func _exit_tree() -> void:
	if GameAPI.player_journal_updated.is_connected(_on_journal):
		GameAPI.player_journal_updated.disconnect(_on_journal)


func _on_journal(entries: Array) -> void:
	for child in _list.get_children():
		child.queue_free()

	_count_lbl.text = "%d events" % entries.size()

	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "No events yet — start playing to fill your journal!"
		lbl.modulate = _COLOR_DIM
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD
		_list.add_child(lbl)
		return

	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var etype: String   = entry.get("event_type", "")
	var summary: String = entry.get("summary", etype)
	var ts: String      = entry.get("happened_at", "")

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(8, 8)
	dot.color = _EVENT_COLOR.get(etype, _COLOR_DIM)

	var sum_lbl := Label.new()
	sum_lbl.text = summary
	sum_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sum_lbl.modulate = _EVENT_COLOR.get(etype, Color.WHITE)
	sum_lbl.add_theme_font_size_override("font_size", 11)

	var date_lbl := Label.new()
	date_lbl.text = ts.left(10) if ts.length() >= 10 else ts
	date_lbl.modulate = _COLOR_DATE
	date_lbl.add_theme_font_size_override("font_size", 10)

	row.add_child(dot)
	row.add_child(sum_lbl)
	row.add_child(date_lbl)

	var vbox := VBoxContainer.new()
	vbox.add_child(row)
	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.10)
	vbox.add_child(sep)
	return vbox
