# game-client/autoloads/NotificationBus.gd
extends Node

signal item_dropped(notification: Dictionary)

const POLL_INTERVAL_SEC := 3.0

var _seen_ids: PackedStringArray = []


func _ready() -> void:
    GameAPI.notifications_updated.connect(_on_notifications)
    var timer := Timer.new()
    timer.wait_time = POLL_INTERVAL_SEC
    timer.autostart = true
    timer.timeout.connect(func() -> void: GameAPI.fetch_notifications())
    add_child(timer)


func _on_notifications(notifs: Array) -> void:
    for notif: Dictionary in notifs:
        var nid: String = notif.get("notification_id", "")
        if nid.is_empty() or nid in _seen_ids:
            continue
        _seen_ids.append(nid)
        item_dropped.emit(notif)
