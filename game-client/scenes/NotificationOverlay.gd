# game-client/scenes/NotificationOverlay.gd
extends CanvasLayer

const RarityColor := preload("res://utils/RarityColor.gd")

@onready var _panel: Panel          = $Panel
@onready var _rarity_bar: ColorRect = $Panel/VBox/RarityBar
@onready var _item_name: Label      = $Panel/VBox/ItemNameLabel
@onready var _rarity_label: Label   = $Panel/VBox/RarityLabel
@onready var _ok_button: Button     = $Panel/VBox/OKButton

var _pending_nid: String = ""
var _queue: Array[Dictionary] = []


func _ready() -> void:
	_panel.visible = false
	NotificationBus.item_dropped.connect(_show_drop)
	_ok_button.pressed.connect(_on_ok)


func _show_drop(notif: Dictionary) -> void:
	if _panel.visible:
		_queue.append(notif)
		return
	_display(notif)


func _display(notif: Dictionary) -> void:
	_pending_nid = notif.get("notification_id", "")
	var payload_str: String = notif.get("payload", "{}")
	var payload: Dictionary = JSON.parse_string(payload_str) if not payload_str.is_empty() else {}
	if not payload is Dictionary:
		payload = {}
	var rarity: String = payload.get("rarity", "COMMON")
	_item_name.text = payload.get("item_name", payload.get("item_id", "Unknown Item"))
	_rarity_label.text = rarity
	_rarity_bar.color = RarityColor.for_rarity(rarity)
	# Reset bar to zero-width so the tween grows it in from the left
	_rarity_bar.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	_rarity_bar.custom_minimum_size.x = 0
	_panel.visible = true
	# Wait one frame so the layout pass completes, then animate
	await get_tree().process_frame
	_animate_rarity_bar()


func _animate_rarity_bar() -> void:
	var target_width: float = (_rarity_bar.get_parent() as Control).size.x
	var tween := create_tween()
	tween.tween_property(_rarity_bar, "custom_minimum_size:x", target_width, 0.4).set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_QUART)


func _on_ok() -> void:
	_panel.visible = false
	if not _pending_nid.is_empty():
		GameAPI.ack_notification(_pending_nid)
		_pending_nid = ""
	if not _queue.is_empty():
		_display(_queue.pop_front())
