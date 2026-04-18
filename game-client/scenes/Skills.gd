# game-client/scenes/Skills.gd
# Passive skill tree — browse and unlock permanent bonuses.
extends Control

@onready var _list: VBoxContainer = $VBox/Scroll/List
@onready var _xp_label: Label     = $VBox/Header/XPLabel

const _COLOR_UNLOCKED   := Color(0.30, 0.85, 0.30)
const _COLOR_AVAILABLE  := Color(1.00, 0.84, 0.00)
const _COLOR_LOCKED     := Color(0.50, 0.50, 0.50)
const _COLOR_EFFECT     := Color(0.60, 0.85, 1.00)

var _total_xp: int = 0


func _ready() -> void:
    $VBox/Header/BackButton.pressed.connect(func() -> void:
        get_tree().change_scene_to_file("res://scenes/Main.tscn")
    )
    GameAPI.skills_updated.connect(_on_skills)
    GameAPI.skill_unlocked.connect(_on_skill_unlocked)
    GameAPI.profile_updated.connect(_on_profile)
    GameAPI.fetch_skills()
    GameAPI.fetch_profile()


func _exit_tree() -> void:
    if GameAPI.skills_updated.is_connected(_on_skills):
        GameAPI.skills_updated.disconnect(_on_skills)
    if GameAPI.skill_unlocked.is_connected(_on_skill_unlocked):
        GameAPI.skill_unlocked.disconnect(_on_skill_unlocked)
    if GameAPI.profile_updated.is_connected(_on_profile):
        GameAPI.profile_updated.disconnect(_on_profile)


func _on_profile(data: Dictionary) -> void:
    _total_xp = data.get("total_xp", 0) as int
    _xp_label.text = "Total XP: %d" % _total_xp


func _on_skill_unlocked(_data: Dictionary) -> void:
    pass  # skills_updated fires automatically after unlock via GameAPI


func _on_skills(entries: Array) -> void:
    for child in _list.get_children():
        child.queue_free()

    if entries.is_empty():
        var lbl := Label.new()
        lbl.text = "No skills available yet."
        lbl.modulate = _COLOR_LOCKED
        _list.add_child(lbl)
        return

    for raw in entries:
        if not raw is Dictionary:
            continue
        _list.add_child(_make_row(raw as Dictionary))


func _make_row(skill: Dictionary) -> Control:
    var unlocked: bool  = skill.get("unlocked", false)
    var can_unlock: bool = skill.get("can_unlock", false)
    var xp_cost: int    = skill.get("xp_cost", 0) as int
    var effect_type: String = skill.get("effect_type", "")
    var params: Dictionary  = skill.get("effect_params", {}) as Dictionary

    var vbox := VBoxContainer.new()

    # ── header row ───────────────────────────────────────────────────────────
    var hbox := HBoxContainer.new()

    var dot := ColorRect.new()
    dot.custom_minimum_size = Vector2(12, 12)
    dot.color = _COLOR_UNLOCKED if unlocked else (_COLOR_AVAILABLE if can_unlock else _COLOR_LOCKED)
    dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER

    var name_lbl := Label.new()
    name_lbl.text = skill.get("name", "?")
    name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    if unlocked:
        name_lbl.modulate = _COLOR_UNLOCKED
    elif not can_unlock:
        name_lbl.modulate = _COLOR_LOCKED

    var cost_lbl := Label.new()
    cost_lbl.text = "%d XP" % xp_cost
    cost_lbl.modulate = _COLOR_AVAILABLE if can_unlock and not unlocked else _COLOR_LOCKED
    cost_lbl.add_theme_font_size_override("font_size", 11)

    hbox.add_child(dot)
    hbox.add_child(name_lbl)
    hbox.add_child(cost_lbl)
    vbox.add_child(hbox)

    # ── description + effect ────────────────────────────────────────────────
    var desc_lbl := Label.new()
    desc_lbl.text = "  " + skill.get("description", "")
    desc_lbl.modulate = Color(0.75, 0.75, 0.75)
    desc_lbl.add_theme_font_size_override("font_size", 11)
    desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    vbox.add_child(desc_lbl)

    var effect_lbl := Label.new()
    effect_lbl.text = "  Effect: " + _format_effect(effect_type, params)
    effect_lbl.modulate = _COLOR_EFFECT if unlocked else _COLOR_LOCKED
    effect_lbl.add_theme_font_size_override("font_size", 10)
    vbox.add_child(effect_lbl)

    # ── unlock button ────────────────────────────────────────────────────────
    if unlocked:
        var badge := Label.new()
        badge.text = "  ✓ Unlocked"
        badge.modulate = _COLOR_UNLOCKED
        badge.add_theme_font_size_override("font_size", 11)
        vbox.add_child(badge)
    else:
        var btn := Button.new()
        btn.text = "Unlock (%d XP)" % xp_cost
        btn.disabled = not can_unlock
        var sid: String = skill.get("skill_id", "")
        btn.pressed.connect(func() -> void:
            GameAPI.unlock_skill(sid)
        )
        vbox.add_child(btn)

    var sep := HSeparator.new()
    sep.modulate = Color(1, 1, 1, 0.12)
    vbox.add_child(sep)

    return vbox


func _format_effect(effect_type: String, params: Dictionary) -> String:
    match effect_type:
        "xp_multiplier":
            return "%.0f%% more XP" % ((params.get("factor", 1.0) - 1.0) * 100.0)
        "drop_weight_mod":
            var r: String = str(params.get("rarity", "?")).capitalize()
            var f: float = params.get("factor", 1.0)
            return "%.0f%% more %s drops" % [(f - 1.0) * 100.0, r]
        "category_xp_bonus":
            var cat: String = str(params.get("category", "?")).capitalize()
            var f: float = params.get("factor", 1.0)
            return "%.0f%% more %s XP" % [(f - 1.0) * 100.0, cat]
        "extra_roll":
            return "+%d extra drop roll(s) per chunk" % int(params.get("rolls", 1))
        _:
            return effect_type
