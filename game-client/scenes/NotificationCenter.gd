# game-client/scenes/NotificationCenter.gd
extends Control

@onready var _list: VBoxContainer   = $VBox/Scroll/List
@onready var _filter_opts: OptionButton = $VBox/FilterRow/FilterOption
@onready var _ack_all_btn: Button   = $VBox/FilterRow/AckAllButton

const _EVENT_LABELS := {
	"item_drop":          "Item Drop",
	"level_up":           "Level Up",
	"place_unlock":       "Place Unlock",
	"place_level_up":     "Place Level Up",
	"achievement_unlock": "Achievement",
	"challenge_complete": "Challenge",
	"challenge_progress": "Challenge",
	"daily_goal_hit":     "Daily Goal",
	"xp_milestone":       "XP Milestone",
}

const _EVENT_COLORS := {
	"item_drop":          Color(0.70, 0.90, 1.00),
	"level_up":           Color(1.00, 0.85, 0.10),
	"place_unlock":       Color(0.20, 0.80, 0.60),
	"place_level_up":     Color(0.55, 0.85, 1.00),
	"achievement_unlock": Color(1.00, 0.84, 0.00),
	"challenge_complete": Color(0.20, 0.80, 1.00),
	"challenge_progress": Color(0.40, 0.85, 0.50),
	"daily_goal_hit":     Color(0.40, 1.00, 0.60),
	"xp_milestone":       Color(1.00, 0.84, 0.00),
}

# Parallel to OptionButton items (index 0 = All)
const _FILTER_VALUES := ["", "item_drop", "level_up", "place_unlock", "place_level_up", "achievement_unlock", "challenge_complete", "challenge_progress", "daily_goal_hit", "xp_milestone"]

var _entries: Array = []
var _settings_panel: PanelContainer = null
var _pref_checkboxes: Dictionary = {}   # event_type → CheckBox


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.inbox_updated.connect(_on_inbox)
	GameAPI.notification_prefs_updated.connect(_on_prefs_updated)
	_ack_all_btn.pressed.connect(_on_ack_all)
	_filter_opts.item_selected.connect(_on_filter_changed)

	_filter_opts.clear()
	_filter_opts.add_item("All")
	for label: String in ["Item Drop", "Level Up", "Place Unlock", "Place Level Up", "Achievement", "Challenge", "Challenge Progress", "Daily Goal", "XP Milestone"]:
		_filter_opts.add_item(label)

	_build_settings_panel()
	_fetch()
	GameAPI.fetch_notification_prefs()


func _build_settings_panel() -> void:
	# ⚙ toggle button in header
	var gear_btn := Button.new()
	gear_btn.text = "⚙ Mute"
	$VBox/Header.add_child(gear_btn)

	# Settings panel (initially hidden)
	_settings_panel = PanelContainer.new()
	_settings_panel.visible = false
	var sv := VBoxContainer.new()
	var title_lbl := Label.new()
	title_lbl.text = "Notification Mute Settings"
	title_lbl.add_theme_font_size_override("font_size", 13)
	sv.add_child(title_lbl)

	var known_types: Array[String] = [
		"item_drop", "item_sold", "bulk_item_sold", "level_up",
		"place_unlock", "place_level_up", "achievement_unlock",
		"xp_milestone", "streak_milestone", "challenge_progress",
		"daily_goal_hit",
	]
	for et: String in known_types:
		var row := HBoxContainer.new()
		var cb := CheckBox.new()
		cb.text = "Enable " + et.replace("_", " ").capitalize()
		cb.button_pressed = true   # default: not muted = enabled
		var et_captured := et
		cb.toggled.connect(func(checked: bool) -> void:
			GameAPI.patch_notification_pref(et_captured, not checked)
		)
		_pref_checkboxes[et] = cb
		row.add_child(cb)
		sv.add_child(row)

	_settings_panel.add_child(sv)
	$VBox.add_child(_settings_panel)

	gear_btn.pressed.connect(func() -> void:
		_settings_panel.visible = not _settings_panel.visible
	)


func _exit_tree() -> void:
	if GameAPI.inbox_updated.is_connected(_on_inbox):
		GameAPI.inbox_updated.disconnect(_on_inbox)
	if GameAPI.notification_prefs_updated.is_connected(_on_prefs_updated):
		GameAPI.notification_prefs_updated.disconnect(_on_prefs_updated)


func _on_prefs_updated(prefs: Array) -> void:
	for pref in prefs:
		if not pref is Dictionary:
			continue
		var et: String = str(pref.get("event_type", ""))
		var muted: bool = bool(pref.get("muted", false))
		if et in _pref_checkboxes:
			var cb: CheckBox = _pref_checkboxes[et]
			cb.set_pressed_no_signal(not muted)


func _fetch() -> void:
	var idx: int = _filter_opts.selected
	var type_filter: String = _FILTER_VALUES[idx] if idx < _FILTER_VALUES.size() else ""
	GameAPI.fetch_inbox(50, type_filter)


func _on_filter_changed(_idx: int) -> void:
	_fetch()


func _on_ack_all() -> void:
	GameAPI.ack_all_notifications()
	await get_tree().create_timer(0.3).timeout
	_fetch()


func _on_inbox(entries: Array) -> void:
	_entries = entries
	_rebuild()


func _rebuild() -> void:
	for child in _list.get_children():
		child.queue_free()

	if _entries.is_empty():
		var lbl := Label.new()
		lbl.text = "No notifications yet."
		lbl.modulate = Color(0.6, 0.6, 0.6)
		_list.add_child(lbl)
		return

	for raw in _entries:
		if not raw is Dictionary:
			continue
		var entry := raw as Dictionary
		_add_entry(entry)


func _add_entry(entry: Dictionary) -> void:
	var hbox := HBoxContainer.new()

	var etype: String = entry.get("event_type", "item_drop")

	# Parse payload early so we can check wishlisted
	var payload_str: String = entry.get("payload", "{}")
	var payload: Dictionary = {}
	if not payload_str.is_empty():
		var parsed = JSON.parse_string(payload_str)
		if parsed is Dictionary:
			payload = parsed
	var wishlisted: bool = etype == "item_drop" and bool(payload.get("wishlisted", false))

	# Coloured dot — gold star for wishlisted item drops
	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(8, 8)
	dot.color = Color(1.0, 0.85, 0.1) if wishlisted else _EVENT_COLORS.get(etype, Color(0.7, 0.7, 0.7))
	dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER

	# Type badge
	var badge := Label.new()
	badge.text = ("★ " if wishlisted else "") + _EVENT_LABELS.get(etype, etype)
	badge.custom_minimum_size.x = 100
	badge.add_theme_font_size_override("font_size", 11)
	badge.modulate = Color(1.0, 0.85, 0.1) if wishlisted else _EVENT_COLORS.get(etype, Color(0.7, 0.7, 0.7))

	# Summary
	var summary := Label.new()
	summary.text = _entry_summary(entry)
	summary.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	summary.clip_text = true

	# Ack status indicator
	var acked: int = entry.get("acknowledged", 0)
	if acked == 0:
		var dot2 := ColorRect.new()
		dot2.custom_minimum_size = Vector2(6, 6)
		dot2.color = Color(1, 0.5, 0.1)   # orange = unread
		dot2.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		hbox.add_child(dot2)

	hbox.add_child(dot)
	hbox.add_child(badge)
	hbox.add_child(summary)
	_list.add_child(hbox)


func _entry_summary(entry: Dictionary) -> String:
	var payload_str: String = entry.get("payload", "{}")
	var payload: Dictionary = {}
	if not payload_str.is_empty():
		var parsed = JSON.parse_string(payload_str)
		if parsed is Dictionary:
			payload = parsed

	match entry.get("event_type", "item_drop"):
		"item_drop":
			var name: String = payload.get("item_name", payload.get("item_id", "Unknown"))
			var rarity: String = payload.get("rarity", "")
			var star: String = "  ★" if bool(payload.get("wishlisted", false)) else ""
			return name + ((" · " + rarity) if not rarity.is_empty() else "") + star
		"level_up":
			return "Reached level %d" % payload.get("new_level", "?")
		"place_unlock":
			var pname: String = str(payload.get("place_name", "New place"))
			var cond: String  = str(payload.get("condition", ""))
			return pname + (" · " + cond if not cond.is_empty() else "")
		"place_level_up":
			var pname: String = payload.get("place_name", "Place")
			var lvl = payload.get("new_level", "?")
			return "%s reached level %s" % [pname, str(lvl)]
		"achievement_unlock":
			var ach_name: String = str(payload.get("name", "Achievement"))
			var ach_desc: String = str(payload.get("description", ""))
			var chain: String    = str(payload.get("chain_next", ""))
			var line: String     = ach_name
			if not ach_desc.is_empty():
				line += " — " + ach_desc
			if not chain.is_empty() and chain != "null":
				line += "  → Next: " + chain
			return line
		"challenge_complete":
			return str(payload.get("name", "Challenge")) + " — complete! Claim your reward."
		"challenge_progress":
			var pct: int = int(payload.get("pct", 50))
			return str(payload.get("name", "Challenge")) + " — %d%% done!" % pct
		"daily_goal_hit":
			var xp: int     = int(payload.get("xp", 0))
			var target: int = int(payload.get("target", 0))
			return "Daily goal reached! %d / %d XP 🎯" % [xp, target]
		"xp_milestone":
			var ms: int       = int(payload.get("milestone", 0))
			var item_n: String = str(payload.get("item_name", "item"))
			var rar: String    = str(payload.get("rarity", "RARE")).capitalize()
			return "XP milestone: %d XP! Bonus %s drop — %s" % [ms, rar, item_n]
		_:
			return "(unknown event)"
