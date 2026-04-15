# game-client/autoloads/NotificationBus.gd
extends Node

signal item_dropped(notification: Dictionary)
signal level_up_occurred(notification: Dictionary)
signal place_unlocked(notification: Dictionary)

const POLL_INTERVAL_SEC := 3.0
const MAX_SEEN_IDS := 200

var _seen_ids: Dictionary = {}


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
		if nid.is_empty() or _seen_ids.has(nid):
			continue
		if _seen_ids.size() >= MAX_SEEN_IDS:
			_seen_ids.erase(_seen_ids.keys()[0])
		_seen_ids[nid] = true
		match notif.get("event_type", "item_drop"):
			"item_drop":
				item_dropped.emit(notif)
			"level_up":
				level_up_occurred.emit(notif)
			"place_unlock":
				place_unlocked.emit(notif)
			var unknown:
				push_warning("NotificationBus: unknown event_type '%s'" % unknown)
				item_dropped.emit(notif)  # fall back so it surfaces rather than silently drops
