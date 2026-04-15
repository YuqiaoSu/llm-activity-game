# game-client/scenes/History.gd
extends Control

const RarityColor := preload("res://utils/RarityColor.gd")

# Category → accent colour (matches HUD bar palette)
const _CAT_COLORS := {
    "WORK":    Color(0.27, 0.58, 1.00),
    "GAME":    Color(0.18, 0.80, 0.44),
    "STUDY":   Color(0.64, 0.19, 0.85),
    "SOCIAL":  Color(1.00, 0.50, 0.00),
    "FITNESS": Color(0.96, 0.26, 0.21),
    "CREATIVE":Color(0.99, 0.76, 0.03),
    "OTHER":   Color(0.60, 0.60, 0.60),
}

@onready var _count_label: Label        = $VBox/Header/CountLabel
@onready var _entry_list: VBoxContainer = $VBox/Scroll/EntryList


func _ready() -> void:
    $VBox/Header/BackButton.pressed.connect(func() -> void:
        get_tree().change_scene_to_file("res://scenes/Main.tscn")
    )
    GameAPI.history_updated.connect(_on_history)
    GameAPI.fetch_history()


func _exit_tree() -> void:
    if GameAPI.history_updated.is_connected(_on_history):
        GameAPI.history_updated.disconnect(_on_history)


func _on_history(entries: Array) -> void:
    _count_label.text = "Activity History (%d)" % entries.size()
    for child in _entry_list.get_children():
        child.queue_free()
    for raw in entries:
        if not raw is Dictionary:
            continue
        _entry_list.add_child(_make_row(raw as Dictionary))


func _make_row(entry: Dictionary) -> Control:
    var hbox := HBoxContainer.new()

    # Category colour dot
    var dot := ColorRect.new()
    dot.custom_minimum_size = Vector2(10, 10)
    var cat: String = entry.get("category", "OTHER")
    dot.color = _CAT_COLORS.get(cat, _CAT_COLORS["OTHER"])

    # Category label
    var cat_lbl := Label.new()
    cat_lbl.text = cat.capitalize()
    cat_lbl.custom_minimum_size.x = 72

    # XP gained
    var xp_lbl := Label.new()
    xp_lbl.text = "+%d XP" % entry.get("xp_awarded", 0)
    xp_lbl.custom_minimum_size.x = 64

    # Duration in minutes
    var dur_min: int = entry.get("duration_sec", 0) / 60
    var dur_lbl := Label.new()
    dur_lbl.text = "%dm" % dur_min
    dur_lbl.custom_minimum_size.x = 40

    # Drop count
    var drops: int = entry.get("drops", 0)
    var drop_lbl := Label.new()
    drop_lbl.text = "%d drop%s" % [drops, "s" if drops != 1 else ""]
    drop_lbl.custom_minimum_size.x = 56

    # Timestamp (HH:MM)
    var ts_lbl := Label.new()
    ts_lbl.text = _format_time(entry.get("processed_at", ""))
    ts_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    ts_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

    hbox.add_child(dot)
    hbox.add_child(cat_lbl)
    hbox.add_child(xp_lbl)
    hbox.add_child(dur_lbl)
    hbox.add_child(drop_lbl)
    hbox.add_child(ts_lbl)
    return hbox


func _format_time(iso: String) -> String:
    # iso is like "2026-04-15T09:30:00+00:00" — extract HH:MM
    var t_idx := iso.find("T")
    if t_idx == -1 or iso.length() < t_idx + 6:
        return iso
    return iso.substr(t_idx + 1, 5)   # "HH:MM"
