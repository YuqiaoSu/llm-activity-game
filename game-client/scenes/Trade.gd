# game-client/scenes/Trade.gd
extends Control

@onready var _list:       VBoxContainer = $VBox/Scroll/List
@onready var _status_lbl: Label         = $VBox/StatusLabel

const _COLOR_AFFORD   := Color(0.3, 0.85, 0.3)
const _COLOR_UNAFFORD := Color(0.6, 0.6, 0.6)
const _COLOR_GOLD     := Color(1.0, 0.85, 0.2)


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	GameAPI.trade_offers_updated.connect(_on_offers)
	GameAPI.trade_accepted.connect(_on_trade_result)
	GameAPI.fetch_trade_offers()


func _exit_tree() -> void:
	if GameAPI.trade_offers_updated.is_connected(_on_offers):
		GameAPI.trade_offers_updated.disconnect(_on_offers)
	if GameAPI.trade_accepted.is_connected(_on_trade_result):
		GameAPI.trade_accepted.disconnect(_on_trade_result)


func _on_trade_result(ok: bool, data: Dictionary) -> void:
	if ok:
		var granted: Array = data.get("granted", [])
		var item_id: String = ""
		if granted.size() > 0:
			item_id = str((granted[0] as Dictionary).get("item_id", "?"))
		_status_lbl.text = "✓ Trade complete! Received: %s" % item_id
		_status_lbl.modulate = _COLOR_AFFORD
	else:
		var detail: String = data.get("detail", "Trade failed")
		_status_lbl.text = "✗ %s" % detail
		_status_lbl.modulate = Color(1.0, 0.4, 0.4)
	# Refresh offers to update availability counts
	GameAPI.fetch_trade_offers()


func _on_offers(offers: Array) -> void:
	for child in _list.get_children():
		child.queue_free()

	if offers.is_empty():
		var lbl := Label.new()
		lbl.text = "No trade offers available."
		_list.add_child(lbl)
		return

	# Group by trader_name
	var by_trader: Dictionary = {}
	for raw in offers:
		if not raw is Dictionary:
			continue
		var offer := raw as Dictionary
		var trader: String = offer.get("trader_name", "Unknown Trader")
		if not by_trader.has(trader):
			by_trader[trader] = []
		by_trader[trader].append(offer)

	for trader_name in by_trader:
		# Trader header
		var hdr := Label.new()
		hdr.text = "── %s ──" % trader_name
		hdr.modulate = _COLOR_GOLD
		hdr.add_theme_font_size_override("font_size", 13)
		_list.add_child(hdr)

		for offer in by_trader[trader_name] as Array:
			_list.add_child(_make_offer_row(offer as Dictionary))

		var sep := HSeparator.new()
		sep.modulate = Color(1, 1, 1, 0.15)
		_list.add_child(sep)


func _make_offer_row(offer: Dictionary) -> Control:
	var can_afford: bool = offer.get("have_enough", false) as bool
	var have: int        = offer.get("have_qty", 0) as int
	var need: int        = offer.get("from_qty", 0) as int

	var row := HBoxContainer.new()

	var label_txt: String = offer.get("label", "?")
	var offer_lbl := Label.new()
	offer_lbl.text = label_txt
	offer_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	offer_lbl.modulate = _COLOR_AFFORD if can_afford else _COLOR_UNAFFORD

	var have_lbl := Label.new()
	have_lbl.text = "(%d / %d)" % [have, need]
	have_lbl.modulate = _COLOR_AFFORD if can_afford else _COLOR_UNAFFORD
	have_lbl.add_theme_font_size_override("font_size", 10)

	var accept_btn := Button.new()
	accept_btn.text = "Trade"
	accept_btn.disabled = not can_afford
	var offer_id: String = offer.get("offer_id", "")
	accept_btn.pressed.connect(func() -> void:
		_status_lbl.text = "Trading…"
		_status_lbl.modulate = Color(1, 1, 1)
		GameAPI.accept_trade(offer_id)
	)

	row.add_child(offer_lbl)
	row.add_child(have_lbl)
	row.add_child(accept_btn)
	return row
