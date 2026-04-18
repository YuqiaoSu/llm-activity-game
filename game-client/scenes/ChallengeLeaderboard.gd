# game-client/scenes/ChallengeLeaderboard.gd
extends Control

@onready var _title_label: Label      = $VBox/Header/TitleLabel
@onready var _list: VBoxContainer     = $VBox/Scroll/List

const _GOLD := Color(1.00, 0.84, 0.00)
const _BLUE := Color(0.35, 0.65, 1.00)
const _DIM  := Color(0.55, 0.55, 0.55)
const _GREEN := Color(0.30, 0.85, 0.30)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Challenges.tscn")
	)
	GameAPI.challenge_leaderboard_updated.connect(_on_data)
	var cid := GameAPI.last_challenge_id
	if cid.is_empty():
		_title_label.text = "Leaderboard"
		_show_error("No challenge selected.")
	else:
		_title_label.text = "Leaderboard"
		GameAPI.fetch_challenge_leaderboard(cid)


func _exit_tree() -> void:
	if GameAPI.challenge_leaderboard_updated.is_connected(_on_data):
		GameAPI.challenge_leaderboard_updated.disconnect(_on_data)


func _on_data(data: Dictionary) -> void:
	for child in _list.get_children():
		child.queue_free()

	var threshold: int    = data.get("threshold", 0)
	var player_score: int = data.get("player_score", 0)
	var your_rank: int    = data.get("your_rank", 0)
	var total: int        = data.get("total_entries", 0)
	var ghosts: Array     = data.get("ghosts", []) as Array

	_title_label.text = "Leaderboard — %s" % data.get("challenge_id", "").replace("_", " ").capitalize()

	# Build combined list: player + ghosts, sorted by score desc
	var entries: Array = []
	entries.append({
		"name":  "You",
		"score": player_score,
		"rank":  your_rank,
		"is_player": true,
	})
	for g in ghosts:
		var gd := g as Dictionary
		entries.append({
			"name":  gd.get("name", "?"),
			"score": gd.get("score", 0),
			"rank":  gd.get("rank", 0),
			"is_player": false,
		})
	entries.sort_custom(func(a, b): return a["rank"] < b["rank"])

	for entry in entries:
		_list.add_child(_make_row(entry as Dictionary, threshold))

	# Footer: your rank summary
	var footer := Label.new()
	footer.text = "Your rank: #%d of %d" % [your_rank, total]
	footer.modulate = _GREEN if your_rank == 1 else Color.WHITE
	footer.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_list.add_child(footer)


func _make_row(entry: Dictionary, threshold: int) -> Control:
	var hbox := HBoxContainer.new()
	hbox.add_theme_constant_override("separation", 8)

	var rank_lbl := Label.new()
	rank_lbl.text = "#%d" % entry.get("rank", 0)
	rank_lbl.custom_minimum_size.x = 28
	rank_lbl.modulate = _GOLD if entry.get("rank", 0) == 1 else _DIM

	var name_lbl := Label.new()
	name_lbl.text = entry.get("name", "?")
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if entry.get("is_player", false):
		name_lbl.modulate = _BLUE
	elif entry.get("rank", 0) == 1:
		name_lbl.modulate = _GOLD

	var score: int = entry.get("score", 0)
	var score_lbl := Label.new()
	score_lbl.text = "%d / %d" % [score, threshold]
	score_lbl.modulate = _GREEN if score >= threshold else Color.WHITE

	hbox.add_child(rank_lbl)
	hbox.add_child(name_lbl)
	hbox.add_child(score_lbl)
	return hbox


func _show_error(msg: String) -> void:
	var lbl := Label.new()
	lbl.text = msg
	lbl.modulate = _DIM
	_list.add_child(lbl)
