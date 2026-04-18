# game-client/scenes/Achievements.gd
extends Control

@onready var _count_label:      Label          = $VBox/Header/CountLabel
@onready var _pinned_list:      HBoxContainer  = $VBox/PinnedSection/PinnedList
@onready var _achievement_list: VBoxContainer  = $VBox/Scroll/AchievementList

const _COLOR_UNLOCKED  := Color(1.00, 0.84, 0.00)  # gold
const _COLOR_LOCKED    := Color(0.40, 0.40, 0.40)  # grey
const _COLOR_PINNED    := Color(0.30, 0.80, 1.00)  # cyan accent
const _COLOR_PIN_BTN   := Color(0.20, 0.60, 0.90)
const _MAX_PINS        := 3

var _pin_count: int = 0


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.achievements_updated.connect(_on_achievements)
	GameAPI.achievement_pinned.connect(_on_pin_changed)
	GameAPI.achievement_unpinned.connect(_on_pin_changed)
	GameAPI.fetch_achievements()


func _exit_tree() -> void:
	if GameAPI.achievements_updated.is_connected(_on_achievements):
		GameAPI.achievements_updated.disconnect(_on_achievements)
	if GameAPI.achievement_pinned.is_connected(_on_pin_changed):
		GameAPI.achievement_pinned.disconnect(_on_pin_changed)
	if GameAPI.achievement_unpinned.is_connected(_on_pin_changed):
		GameAPI.achievement_unpinned.disconnect(_on_pin_changed)


func _on_pin_changed(_data: Dictionary) -> void:
	GameAPI.fetch_achievements()


func _on_achievements(entries: Array) -> void:
	var unlocked_count := 0
	_pin_count = 0
	for raw in entries:
		if raw is Dictionary:
			var d := raw as Dictionary
			if d.get("unlocked", false):
				unlocked_count += 1
			if d.get("pinned", false):
				_pin_count += 1
	_count_label.text = "Achievements (%d / %d)" % [unlocked_count, entries.size()]

	_rebuild_pinned(entries)

	for child in _achievement_list.get_children():
		child.queue_free()
	for raw in entries:
		if raw is Dictionary:
			_achievement_list.add_child(_make_row(raw as Dictionary))


func _rebuild_pinned(entries: Array) -> void:
	for child in _pinned_list.get_children():
		child.queue_free()

	var pinned := entries.filter(func(e: Variant) -> bool:
		return (e as Dictionary).get("pinned", false)
	)
	pinned.sort_custom(func(a: Variant, b: Variant) -> bool:
		return (a as Dictionary).get("pin_order", 99) < (b as Dictionary).get("pin_order", 99)
	)

	for raw in pinned:
		if raw is Dictionary:
			_pinned_list.add_child(_make_pin_card(raw as Dictionary))

	# Empty slot placeholders
	for _i in range(pinned.size(), _MAX_PINS):
		var slot := PanelContainer.new()
		slot.custom_minimum_size = Vector2(100, 60)
		var lbl := Label.new()
		lbl.text = "— empty —"
		lbl.modulate = Color(0.4, 0.4, 0.4)
		lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		slot.add_child(lbl)
		_pinned_list.add_child(slot)


func _make_pin_card(entry: Dictionary) -> Control:
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(100, 60)

	var vbox := VBoxContainer.new()
	var name_lbl := Label.new()
	name_lbl.text = entry.get("name", "?")
	name_lbl.modulate = _COLOR_PINNED
	name_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	var unpin_btn := Button.new()
	unpin_btn.text = "Unpin"
	var ach_id: String = entry.get("achievement_id", "")
	unpin_btn.pressed.connect(func() -> void:
		GameAPI.unpin_achievement(ach_id)
	)

	vbox.add_child(name_lbl)
	vbox.add_child(unpin_btn)
	panel.add_child(vbox)
	return panel


func _make_row(entry: Dictionary) -> Control:
	var unlocked: bool = entry.get("unlocked", false)
	var pinned: bool   = entry.get("pinned", false)

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

	# ── pin button (only for unlocked achievements) ─────────────────────────
	if unlocked:
		var pin_btn := Button.new()
		pin_btn.text = "Unpin" if pinned else "Pin"
		pin_btn.modulate = _COLOR_PINNED if pinned else Color(1, 1, 1)
		pin_btn.disabled = not pinned and _pin_count >= _MAX_PINS
		var ach_id: String = entry.get("achievement_id", "")
		pin_btn.pressed.connect(func() -> void:
			if pinned:
				GameAPI.unpin_achievement(ach_id)
			else:
				GameAPI.pin_achievement(ach_id)
		)
		hbox.add_child(pin_btn)

	vbox.add_child(hbox)

	# ── description (smaller, indented) ─────────────────────────────────────
	var desc_lbl := Label.new()
	desc_lbl.text = "    " + entry.get("description", "")
	desc_lbl.modulate = Color(0.70, 0.70, 0.70) if not unlocked else Color(0.90, 0.90, 0.90)
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vbox.add_child(desc_lbl)

	# ── progress bar (only for locked achievements) ──────────────────────────
	if not unlocked:
		var progress: int     = entry.get("progress", 0) as int
		var progress_pct: int = entry.get("progress_pct", 0) as int
		var threshold: int    = entry.get("threshold", 1) as int
		var ctype: String     = entry.get("condition_type", "")

		var bar := ProgressBar.new()
		bar.min_value = 0
		bar.max_value = 100
		bar.value = progress_pct
		bar.custom_minimum_size = Vector2(0, 8)
		bar.show_percentage = false
		vbox.add_child(bar)

		var prog_lbl := Label.new()
		prog_lbl.text = "    %s / %s" % [_format_progress(ctype, progress), _format_progress(ctype, threshold)]
		prog_lbl.modulate = Color(0.65, 0.65, 0.65)
		prog_lbl.add_theme_font_size_override("font_size", 10)
		vbox.add_child(prog_lbl)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.12)
	vbox.add_child(sep)

	return vbox


func _format_progress(ctype: String, value: int) -> String:
	match ctype:
		"total_xp":        return "%d XP" % value
		"level":           return "Lv.%d" % value
		"streak":          return "%d days" % value
		"items_collected": return "%d items" % value
		_:                 return str(value)


func _condition_hint(ctype: String, threshold: int) -> String:
	match ctype:
		"total_xp":        return "%d XP needed" % threshold
		"level":           return "Reach level %d" % threshold
		"streak":          return "%d-day streak" % threshold
		"items_collected": return "Collect %d items" % threshold
		_:                 return ""


func _format_date(iso: String) -> String:
	if iso.length() >= 10:
		return iso.left(10)
	return iso
