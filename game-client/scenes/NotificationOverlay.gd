# game-client/scenes/NotificationOverlay.gd
extends CanvasLayer

const RarityColor := preload("res://utils/RarityColor.gd")

@onready var _panel: Panel          = $Panel
@onready var _rarity_bar: ColorRect = $Panel/VBox/RarityBar
@onready var _item_name: Label      = $Panel/VBox/ItemNameLabel
@onready var _rarity_label: Label   = $Panel/VBox/RarityLabel
@onready var _ok_button: Button     = $Panel/VBox/OKButton

var _pending_nid: String = ""


func _ready() -> void:
	_panel.visible = false
	NotificationBus.item_dropped.connect(_show_drop)
	_ok_button.pressed.connect(_on_ok)


func _show_drop(notif: Dictionary) -> void:
	_pending_nid = notif.get("notification_id", "")
	var payload_str: String = notif.get("payload", "{}")
	var payload: Dictionary = JSON.parse_string(payload_str) if not payload_str.is_empty() else {}
	if not payload is Dictionary:
		payload = {}
	var rarity: String = payload.get("rarity", "COMMON")
	_item_name.text = payload.get("item_name", payload.get("item_id", "Unknown Item"))
	_rarity_label.text = rarity
	_rarity_bar.color = RarityColor.for_rarity(rarity)
	_panel.visible = true


func _on_ok() -> void:
	_panel.visible = false
	if not _pending_nid.is_empty():
		GameAPI.ack_notification(_pending_nid)
		_pending_nid = ""
