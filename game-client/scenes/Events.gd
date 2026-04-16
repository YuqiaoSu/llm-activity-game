# game-client/scenes/Events.gd
# Shows all challenge events (past, active, future) with a status badge.
extends Control

@onready var _list: VBoxContainer = $ScrollContainer/List
@onready var _back_button: Button = $BackButton


func _ready() -> void:
	_back_button.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.events_updated.connect(_on_events)
	GameAPI.fetch_events()


func _exit_tree() -> void:
	if GameAPI.events_updated.is_connected(_on_events):
		GameAPI.events_updated.disconnect(_on_events)


func _on_events(entries: Array) -> void:
	for child in _list.get_children():
		child.queue_free()

	if entries.is_empty():
		var empty_lbl := Label.new()
		empty_lbl.text = "No challenge events scheduled."
		_list.add_child(empty_lbl)
		return

	for raw in entries:
		var ev := raw as Dictionary
		_list.add_child(_make_banner(ev))


func _make_banner(ev: Dictionary) -> Control:
	var panel := PanelContainer.new()
	var vbox := VBoxContainer.new()
	panel.add_child(vbox)

	# Header row: label + status badge
	var hbox := HBoxContainer.new()
	var name_lbl := Label.new()
	name_lbl.text = ev.get("label", "Event")
	name_lbl.add_theme_font_size_override("font_size", 15)
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hbox.add_child(name_lbl)

	var status := _compute_status(ev)
	var badge := Label.new()
	badge.text = status["text"]
	badge.modulate = status["color"]
	hbox.add_child(badge)
	vbox.add_child(hbox)

	# Details
	var cat: String = ev.get("category", "")
	var mult: float = float(ev.get("multiplier", 1.0))
	var detail := Label.new()
	detail.text = "%s  ·  %.1f× XP  ·  %s → %s" % [
		cat.capitalize(),
		mult,
		_short_date(ev.get("starts_at", "")),
		_short_date(ev.get("ends_at", "")),
	]
	detail.add_theme_color_override("font_color", Color(0.75, 0.75, 0.75))
	vbox.add_child(detail)

	return panel


func _compute_status(ev: Dictionary) -> Dictionary:
	var now_str := Time.get_datetime_string_from_system(true)
	var starts: String = ev.get("starts_at", "")
	var ends: String   = ev.get("ends_at", "")
	if starts > now_str:
		return {"text": "Upcoming", "color": Color(0.6, 0.8, 1.0)}
	if ends < now_str:
		return {"text": "Ended",    "color": Color(0.5, 0.5, 0.5)}
	return {"text": "ACTIVE",   "color": Color(0.3, 1.0, 0.4)}


func _short_date(iso: String) -> String:
	# "2026-04-17T14:00:00" → "Apr 17"
	if iso.length() < 10:
		return iso
	var parts := iso.left(10).split("-")
	if parts.size() < 3:
		return iso.left(10)
	const MONTHS := ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
	                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
	var m := int(parts[1])
	return "%s %s" % [MONTHS[m] if m >= 1 and m <= 12 else parts[1], parts[2]]
