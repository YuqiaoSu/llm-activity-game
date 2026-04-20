# game-client/scenes/PlayerTimeline.gd
extends Control

@onready var _list:      VBoxContainer = $VBox/Scroll/List
@onready var _count_lbl: Label         = $VBox/Header/CountLabel

const _EVENT_COLOR := {
	"level_up":           Color(0.40, 0.80, 1.00),
	"achievement_unlocked": Color(1.00, 0.84, 0.00),
	"place_unlocked":     Color(0.70, 0.55, 1.00),
	"streak_milestone":   Color(1.00, 0.55, 0.20),
	"item_drop_wishlist": Color(0.90, 0.70, 0.25),
}
const _COLOR_DIM  := Color(0.55, 0.55, 0.55)
const _COLOR_DATE := Color(0.45, 0.45, 0.45)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/ProfileCard.tscn")
	)
	GameAPI.player_timeline_updated.connect(_on_timeline)
	GameAPI.fetch_player_timeline(30)


func _exit_tree() -> void:
	if GameAPI.player_timeline_updated.is_connected(_on_timeline):
		GameAPI.player_timeline_updated.disconnect(_on_timeline)


func _on_timeline(entries: Array) -> void:
	for child in _list.get_children():
		child.queue_free()

	_count_lbl.text = "%d events" % entries.size()

	if entries.is_empty():
		var lbl := Label.new()
		lbl.text = "No milestones yet — keep playing!"
		lbl.modulate = _COLOR_DIM
		_list.add_child(lbl)
		return

	for raw in entries:
		if raw is Dictionary:
			_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
	var etype:  String = entry.get("event_type", "")
	var title:  String = entry.get("title", etype)
	var detail: String = entry.get("detail", "")
	var ts:     String = entry.get("happened_at", "")
	var color: Color   = _EVENT_COLOR.get(etype, _COLOR_DIM)

	var outer := VBoxContainer.new()

	var top_row := HBoxContainer.new()
	top_row.add_theme_constant_override("separation", 8)

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(8, 8)
	dot.color = color

	var title_lbl := Label.new()
	title_lbl.text = title
	title_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_lbl.modulate = color
	title_lbl.add_theme_font_size_override("font_size", 11)

	var date_lbl := Label.new()
	date_lbl.text = ts.left(10) if ts.length() >= 10 else ts
	date_lbl.modulate = _COLOR_DATE
	date_lbl.add_theme_font_size_override("font_size", 10)

	top_row.add_child(dot)
	top_row.add_child(title_lbl)
	top_row.add_child(date_lbl)
	outer.add_child(top_row)

	if detail != "":
		var detail_lbl := Label.new()
		detail_lbl.text = "  %s" % detail
		detail_lbl.modulate = Color(0.70, 0.70, 0.70)
		detail_lbl.add_theme_font_size_override("font_size", 10)
		outer.add_child(detail_lbl)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.10)
	outer.add_child(sep)

	return outer
