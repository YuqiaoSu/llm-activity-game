# game-client/scenes/Calendar.gd
# 30-day activity calendar — colour-coded intensity grid.
extends Control

@onready var _grid: GridContainer      = $VBox/Scroll/Grid
@onready var _months_spin: SpinBox     = $VBox/Controls/MonthsSpin
@onready var _legend: HBoxContainer    = $VBox/Legend

# XP intensity → colour (same 4-tier scale as heatmap)
const _INTENSITY_COLORS := [
    Color(0.15, 0.15, 0.15),  # 0 — inactive
    Color(0.10, 0.40, 0.20),  # 1 — low
    Color(0.10, 0.65, 0.30),  # 2 — medium
    Color(0.15, 0.85, 0.40),  # 3 — high
    Color(0.50, 1.00, 0.60),  # 4 — very high
]
const _DAY_LABELS  := ["S", "M", "T", "W", "T", "F", "S"]
const _CELL_SIZE   := 20


func _ready() -> void:
    $VBox/Header/BackButton.pressed.connect(func() -> void:
        get_tree().change_scene_to_file("res://scenes/Main.tscn")
    )
    GameAPI.calendar_updated.connect(_on_calendar)
    _months_spin.min_value = 1
    _months_spin.max_value = 6
    _months_spin.value     = 1
    _months_spin.value_changed.connect(func(_v: float) -> void:
        _fetch()
    )
    _build_legend()
    _fetch()


func _exit_tree() -> void:
    if GameAPI.calendar_updated.is_connected(_on_calendar):
        GameAPI.calendar_updated.disconnect(_on_calendar)


func _fetch() -> void:
    GameAPI.fetch_calendar(int(_months_spin.value))


func _build_legend() -> void:
    for child in _legend.get_children():
        child.queue_free()
    var labels_text := ["None", "Low", "Med", "High", "Max"]
    for i in range(_INTENSITY_COLORS.size()):
        var box := ColorRect.new()
        box.custom_minimum_size = Vector2(14, 14)
        box.color = _INTENSITY_COLORS[i]
        var lbl := Label.new()
        lbl.text = labels_text[i]
        lbl.add_theme_font_size_override("font_size", 10)
        _legend.add_child(box)
        _legend.add_child(lbl)


func _on_calendar(entries: Array) -> void:
    for child in _grid.get_children():
        child.queue_free()

    if entries.is_empty():
        return

    # 7-column grid for Sun–Sat; add day-of-week header row
    _grid.columns = 7
    for day_label in _DAY_LABELS:
        var hdr := Label.new()
        hdr.text = day_label
        hdr.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
        hdr.custom_minimum_size = Vector2(_CELL_SIZE, _CELL_SIZE)
        hdr.add_theme_font_size_override("font_size", 9)
        hdr.modulate = Color(0.6, 0.6, 0.6)
        _grid.add_child(hdr)

    # Determine day-of-week for the first entry (0=Sun for display purposes)
    var first_date := entries[0].get("date", "") as String
    var first_day_of_week := _day_of_week(first_date)  # 0=Mon … 6=Sun in GDScript Date
    # Convert to Sunday-first: Mon=0 → 1, Tue=1 → 2, … Sun=6 → 0
    var sun_first_offset: int = (first_day_of_week + 1) % 7

    # Fill leading empty cells
    for _i in range(sun_first_offset):
        var spacer := Control.new()
        spacer.custom_minimum_size = Vector2(_CELL_SIZE, _CELL_SIZE)
        _grid.add_child(spacer)

    # Fill day cells
    for raw in entries:
        if not raw is Dictionary:
            continue
        var entry := raw as Dictionary
        var xp: int       = entry.get("xp", 0) as int
        var intensity: int = entry.get("intensity", 0) as int
        var day_str: String = entry.get("date", "?")

        var cell := ColorRect.new()
        cell.custom_minimum_size = Vector2(_CELL_SIZE, _CELL_SIZE)
        cell.color = _INTENSITY_COLORS[clampi(intensity, 0, 4)]

        # Tooltip-like: show date + XP in a small label on hover (Godot 4 uses tooltip_text)
        var day_num: String = day_str.substr(8, 2)  # last 2 chars of YYYY-MM-DD
        var tooltip: String = "%s: %d XP" % [day_str, xp]
        cell.tooltip_text = tooltip

        # Highlight today
        if day_str == Time.get_date_string_from_system():
            var border := PanelContainer.new()
            border.custom_minimum_size = Vector2(_CELL_SIZE, _CELL_SIZE)
            var style := StyleBoxFlat.new()
            style.border_width_left  = 1
            style.border_width_right = 1
            style.border_width_top   = 1
            style.border_width_bottom = 1
            style.border_color = Color(1, 1, 1, 0.8)
            style.bg_color = _INTENSITY_COLORS[clampi(intensity, 0, 4)]
            border.add_theme_stylebox_override("panel", style)
            _grid.add_child(border)
        else:
            _grid.add_child(cell)


func _day_of_week(iso_date: String) -> int:
    if iso_date.length() < 10:
        return 0
    var year: int  = iso_date.substr(0, 4).to_int()
    var month: int = iso_date.substr(5, 2).to_int()
    var day: int   = iso_date.substr(8, 2).to_int()
    # Godot's Time.get_datetime_dict_from_unix_time is tricky; use Zeller's congruence instead.
    # Returns 0=Mon, 1=Tue, … 6=Sun (ISO weekday)
    if month < 3:
        month += 12
        year -= 1
    var k: int = year % 100
    var j: int = year / 100
    var h: int = (day + (13 * (month + 1)) / 5 + k + k / 4 + j / 4 + 5 * j) % 7
    # Zeller: 0=Sat,1=Sun,2=Mon…6=Fri → convert to ISO (0=Mon)
    # h=1→Sun=6, h=2→Mon=0, h=3→Tue=1, h=4→Wed=2, h=5→Thu=3, h=6→Fri=4, h=0→Sat=5
    return (h + 5) % 7
