# game-client/scenes/FriendCompare.gd
extends Control

@onready var _you_panel:      VBoxContainer = $VBox/OverviewPanel/Panels/YouPanel/Stats
@onready var _other_panel:    VBoxContainer = $VBox/OverviewPanel/Panels/OtherPanel/Stats
@onready var _winner_lbl:     Label         = $VBox/OverviewPanel/WinnerLabel
@onready var _picker:         OptionButton  = $VBox/Header/GhostPicker
@onready var _you_name:       Label         = $VBox/OverviewPanel/Panels/YouPanel/NameLabel
@onready var _other_name:     Label         = $VBox/OverviewPanel/Panels/OtherPanel/NameLabel
@onready var _overview_panel: Control       = $VBox/OverviewPanel
@onready var _race_panel:     Control       = $VBox/RacePanel
@onready var _race_list:      VBoxContainer = $VBox/RacePanel/Scroll/RaceList
@onready var _race_header:    Label         = $VBox/RacePanel/RaceHeader
@onready var _tab_overview:   Button        = $VBox/Tabs/OverviewTab
@onready var _tab_race:       Button        = $VBox/Tabs/RaceTab

const _COLOR_WIN  := Color(0.30, 0.90, 0.30)
const _COLOR_LOSE := Color(1.00, 0.40, 0.40)
const _COLOR_TIE  := Color(1.00, 0.85, 0.20)
const _COLOR_DIM  := Color(0.60, 0.60, 0.60)
const _COLOR_CAT  := Color(0.90, 0.78, 0.40)

var _available: Array = []
var _selected_id: String = "ghost_casual"


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	_picker.item_selected.connect(_on_ghost_selected)
	_tab_overview.pressed.connect(func() -> void: _show_tab(true))
	_tab_race.pressed.connect(func() -> void: _show_tab(false))

	GameAPI.compare_updated.connect(_on_compare)
	GameAPI.race_updated.connect(_on_race)
	GameAPI.fetch_compare(_selected_id)
	GameAPI.fetch_race(_selected_id)

	_show_tab(true)  # Overview visible by default


func _exit_tree() -> void:
	if GameAPI.compare_updated.is_connected(_on_compare):
		GameAPI.compare_updated.disconnect(_on_compare)
	if GameAPI.race_updated.is_connected(_on_race):
		GameAPI.race_updated.disconnect(_on_race)


func _show_tab(overview: bool) -> void:
	_overview_panel.visible = overview
	_race_panel.visible = not overview
	_tab_overview.modulate = Color(1, 1, 1) if overview else _COLOR_DIM
	_tab_race.modulate = Color(1, 1, 1) if not overview else _COLOR_DIM


func _on_ghost_selected(idx: int) -> void:
	if idx < _available.size():
		_selected_id = (_available[idx] as Dictionary).get("player_id", _selected_id)
		GameAPI.fetch_compare(_selected_id)
		GameAPI.fetch_race(_selected_id)


func _on_compare(data: Dictionary) -> void:
	var you: Dictionary   = data.get("you", {}) as Dictionary
	var other: Dictionary = data.get("other", {}) as Dictionary
	var winner: String    = data.get("winner", "tie")

	var avail: Array = data.get("available", []) as Array
	if avail.size() > 0 and _available.size() == 0:
		_available = avail
		_picker.clear()
		for entry in avail:
			_picker.add_item((entry as Dictionary).get("name", "?"))
		for i in range(avail.size()):
			if (avail[i] as Dictionary).get("player_id", "") == _selected_id:
				_picker.select(i)
				break

	_you_name.text = you.get("name", "You")
	_other_name.text = other.get("name", "Them")

	_fill_panel(_you_panel, you)
	_fill_panel(_other_panel, other)

	match winner:
		"you":
			_winner_lbl.text = "★ You're ahead!"
			_winner_lbl.modulate = _COLOR_WIN
			_you_name.modulate = _COLOR_WIN
			_other_name.modulate = _COLOR_LOSE
		"other":
			_winner_lbl.text = "Keep going — they're ahead!"
			_winner_lbl.modulate = _COLOR_LOSE
			_you_name.modulate = _COLOR_LOSE
			_other_name.modulate = _COLOR_WIN
		_:
			_winner_lbl.text = "It's a tie!"
			_winner_lbl.modulate = _COLOR_TIE
			_you_name.modulate = _COLOR_TIE
			_other_name.modulate = _COLOR_TIE


func _on_race(data: Dictionary) -> void:
	for child in _race_list.get_children():
		child.queue_free()

	var other_name: String = data.get("other_name", "Them")
	var you_wins: int   = data.get("you_wins", 0) as int
	var other_wins: int = data.get("other_wins", 0) as int
	_race_header.text = "This week vs %s  (You %d — %d Them)" % [other_name, you_wins, other_wins]

	var categories: Array = data.get("categories", []) as Array
	for raw in categories:
		if not raw is Dictionary:
			continue
		var entry := raw as Dictionary
		_race_list.add_child(_make_race_row(entry))


func _make_race_row(entry: Dictionary) -> Control:
	var cat: String    = entry.get("category", "?")
	var your_xp: int   = entry.get("your_xp", 0) as int
	var their_xp: int  = entry.get("their_xp", 0) as int
	var leader: String = entry.get("leader", "tie")

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)

	var cat_lbl := Label.new()
	cat_lbl.text = cat
	cat_lbl.modulate = _COLOR_CAT
	cat_lbl.add_theme_font_size_override("font_size", 11)
	cat_lbl.custom_minimum_size.x = 80

	var you_lbl := Label.new()
	you_lbl.text = str(your_xp)
	you_lbl.add_theme_font_size_override("font_size", 11)
	you_lbl.custom_minimum_size.x = 55
	you_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

	var badge := Label.new()
	badge.add_theme_font_size_override("font_size", 11)
	badge.custom_minimum_size.x = 28
	badge.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	match leader:
		"you":
			badge.text = "◀"
			badge.modulate = _COLOR_WIN
			you_lbl.modulate = _COLOR_WIN
		"other":
			badge.text = "▶"
			badge.modulate = _COLOR_LOSE
			you_lbl.modulate = _COLOR_LOSE
		_:
			badge.text = "="
			badge.modulate = _COLOR_TIE

	var them_lbl := Label.new()
	them_lbl.text = str(their_xp)
	them_lbl.add_theme_font_size_override("font_size", 11)
	them_lbl.custom_minimum_size.x = 55

	row.add_child(cat_lbl)
	row.add_child(you_lbl)
	row.add_child(badge)
	row.add_child(them_lbl)
	return row


func _fill_panel(panel: VBoxContainer, d: Dictionary) -> void:
	for child in panel.get_children():
		child.queue_free()
	_add_stat(panel, "Level",     "Lv. %d" % d.get("level", 1))
	_add_stat(panel, "Total XP",  str(d.get("total_xp", 0)))
	_add_stat(panel, "This week", "%d XP" % d.get("weekly_xp", 0))
	_add_stat(panel, "Streak",    "%d day%s" % [d.get("streak_days", 0),
	           "s" if d.get("streak_days", 0) != 1 else ""])


func _add_stat(panel: VBoxContainer, label: String, value: String) -> void:
	var hbox := HBoxContainer.new()
	var lbl := Label.new()
	lbl.text = label
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.modulate = _COLOR_DIM
	lbl.add_theme_font_size_override("font_size", 11)
	var val := Label.new()
	val.text = value
	val.add_theme_font_size_override("font_size", 11)
	hbox.add_child(lbl)
	hbox.add_child(val)
	panel.add_child(hbox)
