# game-client/scenes/Stats.gd
extends Control

@onready var _stat_list: VBoxContainer = $VBox/Scroll/StatList


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.stats_updated.connect(_on_stats)
	GameAPI.fetch_stats()


func _exit_tree() -> void:
	if GameAPI.stats_updated.is_connected(_on_stats):
		GameAPI.stats_updated.disconnect(_on_stats)


func _on_stats(data: Dictionary) -> void:
	for child in _stat_list.get_children():
		child.queue_free()

	var stage_names := ["Hatchling", "Growing", "Mature", "Legendary"]
	var stage := mini(data.get("evolution_stage", 0) as int, stage_names.size() - 1)

	_add_row("Level", str(data.get("level", 1)))
	_add_row("Stage", stage_names[stage])
	_add_row("Total XP", "%d" % data.get("total_xp", 0))
	_add_row("Top Category", str(data.get("top_category", "—")).capitalize())
	_add_row("Sessions Processed", str(data.get("chunks_processed", 0)))
	_add_row("Items Dropped", str(data.get("drops_total", 0)))
	_add_row("Places Unlocked", str(data.get("places_unlocked", 0)))

	var cur_streak: int = data.get("current_streak", 0)
	var long_streak: int = data.get("longest_streak", 0)
	var streak_text: String = "%d day%s" % [cur_streak, "s" if cur_streak != 1 else ""]
	_add_row("Current Streak", streak_text)
	_add_row("Longest Streak", "%d day%s" % [long_streak, "s" if long_streak != 1 else ""])

	var cat_xp: Dictionary = data.get("category_xp", {})
	for category: String in cat_xp:
		var xp: int = cat_xp[category] as int
		if xp > 0:
			_add_row(category.capitalize() + " XP", str(xp))


func _add_row(label: String, value: String) -> void:
	var hbox := HBoxContainer.new()
	var lbl := Label.new()
	lbl.text = label
	lbl.custom_minimum_size.x = 160
	var val := Label.new()
	val.text = value
	val.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hbox.add_child(lbl)
	hbox.add_child(val)
	_stat_list.add_child(hbox)
