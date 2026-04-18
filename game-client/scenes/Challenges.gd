# game-client/scenes/Challenges.gd
extends Control

@onready var _count_label: Label            = $VBox/Header/CountLabel
@onready var _challenge_list: VBoxContainer = $VBox/Scroll/ChallengeList
@onready var _reroll_btn: Button            = $VBox/Header/RerollButton

const _COLOR_DONE     := Color(0.20, 0.80, 1.00)  # cyan-blue
const _COLOR_PROGRESS := Color(0.85, 0.85, 0.85)  # light grey
const _COLOR_LOCKED   := Color(0.45, 0.45, 0.45)  # dim grey
const _COLOR_CLAIMED  := Color(0.40, 0.80, 0.40)  # green

var _reroll_used: bool = false


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	_reroll_btn.pressed.connect(_on_reroll)
	GameAPI.challenges_updated.connect(_on_challenges)
	GameAPI.challenge_claimed.connect(_on_claim_result)
	GameAPI.challenge_rerolled.connect(_on_reroll_result)
	GameAPI.fetch_challenges()


func _exit_tree() -> void:
	if GameAPI.challenges_updated.is_connected(_on_challenges):
		GameAPI.challenges_updated.disconnect(_on_challenges)
	if GameAPI.challenge_claimed.is_connected(_on_claim_result):
		GameAPI.challenge_claimed.disconnect(_on_claim_result)
	if GameAPI.challenge_rerolled.is_connected(_on_reroll_result):
		GameAPI.challenge_rerolled.disconnect(_on_reroll_result)


func _on_challenges(entries: Array) -> void:
	var done_count := 0
	for raw in entries:
		if raw is Dictionary and (raw as Dictionary).get("completed", false):
			done_count += 1
	_count_label.text = "Challenges (%d / %d done this week)" % [done_count, entries.size()]

	for child in _challenge_list.get_children():
		child.queue_free()
	for raw in entries:
		if raw is Dictionary:
			_challenge_list.add_child(_make_row(raw as Dictionary))


func _on_reroll() -> void:
	_reroll_btn.disabled = true
	GameAPI.reroll_challenge()


func _on_reroll_result(ok: bool, data: Dictionary) -> void:
	if ok:
		_reroll_used = true
		_reroll_btn.disabled = true
		_reroll_btn.text = "Rerolled"
		GameAPI.fetch_challenges()
	else:
		_reroll_btn.disabled = _reroll_used
		push_warning("Challenges: reroll failed: %s" % data.get("detail", "unknown"))


func _on_claim_result(ok: bool, challenge_id: String, xp: int) -> void:
	if ok:
		GameAPI.fetch_challenges()
	else:
		push_warning("Challenges: claim %s failed" % challenge_id)


func _make_row(entry: Dictionary) -> Control:
	var completed: bool    = entry.get("completed", false)
	var reward_given: bool = entry.get("reward_given", false)
	var progress: int      = entry.get("progress", 0)
	var threshold: int     = entry.get("threshold", 1)
	var metric: String     = entry.get("metric", "xp")
	var challenge_id: String = entry.get("challenge_id", "")

	var vbox := VBoxContainer.new()

	# ── main row ─────────────────────────────────────────────────────────────
	var hbox := HBoxContainer.new()

	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(12, 12)
	if reward_given:
		dot.color = _COLOR_CLAIMED
	elif completed:
		dot.color = _COLOR_DONE
	else:
		dot.color = _COLOR_PROGRESS

	var name_lbl := Label.new()
	name_lbl.text = ("✓ " if completed else "  ") + entry.get("name", "?")
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.modulate = _COLOR_CLAIMED if reward_given else (_COLOR_DONE if completed else _COLOR_PROGRESS)

	var status_lbl := Label.new()
	if reward_given:
		status_lbl.text = "Claimed"
		status_lbl.modulate = _COLOR_CLAIMED
	elif completed:
		status_lbl.text = "Done!"
		status_lbl.modulate = _COLOR_DONE
	else:
		status_lbl.text = _progress_text(progress, threshold, metric)
		status_lbl.modulate = _COLOR_LOCKED

	hbox.add_child(dot)
	hbox.add_child(name_lbl)
	hbox.add_child(status_lbl)

	# Claim button — only visible when completed and not yet claimed
	if completed and not reward_given:
		var claim_btn := Button.new()
		claim_btn.text = "Claim"
		claim_btn.pressed.connect(func() -> void:
			claim_btn.disabled = true
			GameAPI.claim_challenge(challenge_id)
		)
		hbox.add_child(claim_btn)

	var lb_btn := Button.new()
	lb_btn.text = "🏆"
	lb_btn.pressed.connect(func() -> void:
		GameAPI.last_challenge_id = challenge_id
		get_tree().change_scene_to_file("res://scenes/ChallengeLeaderboard.tscn")
	)
	hbox.add_child(lb_btn)

	vbox.add_child(hbox)

	# ── description (smaller, indented) ──────────────────────────────────────
	var desc_lbl := Label.new()
	desc_lbl.text = "    " + entry.get("description", "")
	desc_lbl.modulate = Color(0.65, 0.65, 0.65) if not completed else Color(0.85, 0.85, 0.85)
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vbox.add_child(desc_lbl)

	var sep := HSeparator.new()
	sep.modulate = Color(1, 1, 1, 0.12)
	vbox.add_child(sep)

	return vbox


func _progress_text(progress: int, threshold: int, metric: String) -> String:
	match metric:
		"xp":        return "%d / %d XP" % [progress, threshold]
		"total_xp":  return "%d / %d total XP" % [progress, threshold]
		"categories": return "%d / %d categories" % [progress, threshold]
		_:           return "%d / %d" % [progress, threshold]
