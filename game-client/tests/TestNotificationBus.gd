# game-client/tests/TestNotificationBus.gd
extends Node

var _passed := 0
var _failed := 0
var _dropped: Array = []
var _dropped_callable: Callable


func _ready() -> void:
	# Stop the autostart timer so it cannot fire during synchronous assertions
	for child in NotificationBus.get_children():
		if child is Timer:
			child.stop()

	# Reset autoload state
	NotificationBus._seen_ids = {}

	_dropped_callable = func(n: Dictionary) -> void:
		_dropped.append(n)
	NotificationBus.item_dropped.connect(_dropped_callable)

	var n1 := {"notification_id": "aaa", "event_type": "item_drop", "payload": "{}"}
	var n2 := {"notification_id": "bbb", "event_type": "item_drop", "payload": "{}"}

	# Scenario 1: both IDs are new → 2 signals
	NotificationBus._on_notifications([n1, n2])
	_check("both new notifs emitted", _dropped.size() == 2)

	# Scenario 2: same IDs again → 0 new signals
	_dropped.clear()
	NotificationBus._on_notifications([n1, n2])
	_check("duplicate notifs not re-emitted", _dropped.size() == 0)

	# Scenario 3: one old, one new → exactly 1 signal with the new ID
	_dropped.clear()
	var n3 := {"notification_id": "ccc", "event_type": "item_drop", "payload": "{}"}
	NotificationBus._on_notifications([n1, n3])
	_check("only new notif emitted", _dropped.size() == 1)
	_check("emitted notif is ccc", _dropped[0].get("notification_id") == "ccc")

	print("NotificationBus: %d passed, %d failed" % [_passed, _failed])
	NotificationBus.item_dropped.disconnect(_dropped_callable)
	get_tree().quit(1 if _failed > 0 else 0)


func _check(label: String, ok: bool) -> void:
	if ok:
		_passed += 1
		print("  PASS: %s" % label)
	else:
		_failed += 1
		push_error("  FAIL: %s" % label)
