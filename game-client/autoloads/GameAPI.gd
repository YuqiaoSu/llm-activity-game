# game-client/autoloads/GameAPI.gd
extends Node

const BASE_URL := "http://localhost:8765"

var _cached_profile: Dictionary = {}

signal profile_updated(data: Dictionary)
signal inventory_updated(items: Array)
signal notifications_updated(notifs: Array)
signal poll_completed(result: String)
signal equip_updated(item_id: String, equipped: bool)
signal item_discarded(instance_id: String)
signal places_updated(places: Array)
signal stats_updated(data: Dictionary)
signal history_updated(entries: Array)
signal achievements_updated(entries: Array)
signal challenges_updated(entries: Array)
signal daily_stats_updated(entries: Array)
signal inbox_updated(entries: Array)
signal challenge_claimed(ok: bool, challenge_id: String, xp: int)
signal challenge_rerolled(ok: bool, data: Dictionary)
signal collection_updated(entries: Array)
signal suggestions_updated(entries: Array)
signal fuse_completed(ok: bool, data: Dictionary)
signal daily_goals_updated(entries: Array)
signal recap_updated(data: Dictionary)


func fetch_profile() -> void:
    # Emit cached data immediately so the HUD renders without a blank frame on re-entry
    if not _cached_profile.is_empty():
        profile_updated.emit(_cached_profile)
    _http_get("/player/profile", func(data: Dictionary) -> void:
        _cached_profile = data
        profile_updated.emit(data)
    )


func fetch_inventory() -> void:
    _http_get("/inventory", func(data) -> void:
        if data is Array:
            inventory_updated.emit(data as Array)
        else:
            push_error("GameAPI: /inventory response is not an Array")
    )


func fetch_notifications() -> void:
    _http_get("/notifications/pending", func(data) -> void:
        notifications_updated.emit(data as Array)
    )


func ack_all_notifications() -> void:
    _http_post("/notifications/ack-all", func(_code: int, _data: Dictionary) -> void:
        pass
    )


func ack_notification(nid: String) -> void:
    var re := RegEx.new()
    re.compile("^[0-9a-fA-F\\-]{8,40}$")
    if re.search(nid) == null:
        push_error("GameAPI: invalid notification ID: %s" % nid)
        return
    _http_post("/notifications/%s/ack" % nid, func(_code: int, _data: Dictionary) -> void:
        pass
    )


func fetch_stats() -> void:
    _http_get("/stats", func(data: Dictionary) -> void:
        stats_updated.emit(data)
    )


func fetch_history() -> void:
    _http_get("/history", func(data) -> void:
        if data is Array:
            history_updated.emit(data as Array)
        else:
            push_error("GameAPI: /history response is not an Array")
    )


func fetch_achievements() -> void:
	_http_get("/achievements", func(data) -> void:
		if data is Array:
			achievements_updated.emit(data as Array)
		else:
			push_error("GameAPI: /achievements response is not an Array")
	)


func fetch_daily_stats(days: int = 7) -> void:
	_http_get("/stats/daily?days=%d" % days, func(data) -> void:
		if data is Array:
			daily_stats_updated.emit(data as Array)
		else:
			push_error("GameAPI: /stats/daily response is not an Array")
	)


func fetch_inbox(limit: int = 50, event_type: String = "") -> void:
	var path := "/notifications/inbox?limit=%d" % limit
	if not event_type.is_empty():
		path += "&event_type=" + event_type
	_http_get(path, func(data) -> void:
		if data is Array:
			inbox_updated.emit(data as Array)
		else:
			push_error("GameAPI: /notifications/inbox response is not an Array")
	)


func fetch_collection() -> void:
	_http_get("/collection", func(data) -> void:
		if data is Array:
			collection_updated.emit(data as Array)
		else:
			push_error("GameAPI: /collection response is not an Array")
	)


func fetch_weekly_recap(weeks_ago: int = 0) -> void:
	_http_get("/recap/weekly?weeks_ago=%d" % weeks_ago, func(data) -> void:
		if data is Dictionary:
			recap_updated.emit(data as Dictionary)
		else:
			push_error("GameAPI: /recap/weekly response is not a Dictionary")
	)


func fetch_daily_goals() -> void:
	_http_get("/goals/daily", func(data) -> void:
		if data is Array:
			daily_goals_updated.emit(data as Array)
		else:
			push_error("GameAPI: /goals/daily response is not an Array")
	)


func fuse_item(item_id: String) -> void:
	var body_str := JSON.stringify({"item_id": item_id})
	_http_post("/inventory/fuse", func(code: int, data: Dictionary) -> void:
		fuse_completed.emit(code == 200, data)
	, body_str)


func fetch_suggestions() -> void:
	_http_get("/suggestions", func(data) -> void:
		if data is Array:
			suggestions_updated.emit(data as Array)
		else:
			push_error("GameAPI: /suggestions response is not an Array")
	)


func claim_challenge(challenge_id: String) -> void:
	_http_post("/challenges/%s/claim" % challenge_id, func(code: int, data: Dictionary) -> void:
		if code == 200:
			challenge_claimed.emit(true, challenge_id, data.get("xp_awarded", 0))
		else:
			challenge_claimed.emit(false, challenge_id, 0)
	)


func reroll_challenge() -> void:
	_http_post("/challenges/reroll", func(code: int, data: Dictionary) -> void:
		challenge_rerolled.emit(code == 200, data)
	)


func fetch_challenges() -> void:
	_http_get("/challenges", func(data) -> void:
		if data is Array:
			challenges_updated.emit(data as Array)
		else:
			push_error("GameAPI: /challenges response is not an Array")
	)


func fetch_places() -> void:
    _http_get("/places", func(data) -> void:
        if data is Array:
            places_updated.emit(data as Array)
        else:
            push_error("GameAPI: /places response is not an Array")
    )


signal slot_assigned(place: Dictionary)

func assign_slot(place_id: String, slot_id: String, instance_id: Variant) -> void:
    ## Assign or remove an item instance from a place slot.
    ## Pass null for instance_id to remove the current occupant.
    var body := JSON.stringify({"instance_id": instance_id})
    _http_put("/places/%s/slots/%s" % [place_id, slot_id], body, func(code: int, data: Dictionary) -> void:
        if code == 200:
            slot_assigned.emit(data)
        else:
            push_error("GameAPI: assign_slot %s/%s → %d" % [place_id, slot_id, code])
    )


func discard_item(instance_id: String) -> void:
	_http_delete("/inventory/instances/%s" % instance_id, func(code: int, _data: Dictionary) -> void:
		if code == 200:
			item_discarded.emit(instance_id)
		else:
			push_error("GameAPI: discard_item %s → %d" % [instance_id, code])
	)


func equip_item(item_id: String, equipped: bool) -> void:
    var body := JSON.stringify({"equipped": equipped})
    _http_patch("/inventory/%s/equip" % item_id, body, func(code: int, data: Dictionary) -> void:
        if code == 200:
            equip_updated.emit(item_id, data.get("equipped", equipped))
        else:
            push_error("GameAPI: equip %s → %d" % [item_id, code])
    )


func poll_now() -> void:
    _http_post("/sync/poll-now", func(code: int, data: Dictionary) -> void:
        match code:
            200:
                poll_completed.emit(data.get("result", "UNKNOWN"))
            503:
                poll_completed.emit("ON_COOLDOWN")
            _:
                poll_completed.emit("ERROR")
    )


# ── internal helpers ──────────────────────────────────────────────────────────

func _http_get(path: String, on_done: Callable) -> void:
    var http := HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(
        func(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
            http.queue_free()
            if result != HTTPRequest.RESULT_SUCCESS:
                push_error("GameAPI: network error on GET %s" % path)
                return
            if code == 200:
                var parsed = JSON.parse_string(body.get_string_from_utf8())
                if parsed != null:
                    on_done.call(parsed)
            else:
                push_error("GameAPI: GET %s → %d" % [path, code])
    )
    var err := http.request(BASE_URL + path)
    if err != OK:
        push_error("GameAPI: failed to start GET %s" % path)
        http.queue_free()


func _http_patch(path: String, body: String, on_done: Callable) -> void:
    var http := HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(
        func(result: int, code: int, _h: PackedStringArray, body_bytes: PackedByteArray) -> void:
            http.queue_free()
            if result != HTTPRequest.RESULT_SUCCESS:
                push_error("GameAPI: network error on PATCH %s" % path)
                return
            var parsed = JSON.parse_string(body_bytes.get_string_from_utf8())
            on_done.call(code, parsed if parsed != null else {})
    )
    var headers := PackedStringArray(["Content-Type: application/json"])
    var err := http.request(BASE_URL + path, headers, HTTPClient.METHOD_PATCH, body)
    if err != OK:
        push_error("GameAPI: failed to start PATCH %s" % path)
        http.queue_free()


func _http_put(path: String, body: String, on_done: Callable) -> void:
    var http := HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(
        func(result: int, code: int, _h: PackedStringArray, body_bytes: PackedByteArray) -> void:
            http.queue_free()
            if result != HTTPRequest.RESULT_SUCCESS:
                push_error("GameAPI: network error on PUT %s" % path)
                return
            var parsed = JSON.parse_string(body_bytes.get_string_from_utf8())
            on_done.call(code, parsed if parsed != null else {})
    )
    var headers := PackedStringArray(["Content-Type: application/json"])
    var err := http.request(BASE_URL + path, headers, HTTPClient.METHOD_PUT, body)
    if err != OK:
        push_error("GameAPI: failed to start PUT %s" % path)
        http.queue_free()


func _http_delete(path: String, on_done: Callable) -> void:
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(
		func(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
			http.queue_free()
			if result != HTTPRequest.RESULT_SUCCESS:
				push_error("GameAPI: network error on DELETE %s" % path)
				return
			var parsed = JSON.parse_string(body.get_string_from_utf8())
			on_done.call(code, parsed if parsed != null else {})
	)
	var headers := PackedStringArray(["Content-Type: application/json"])
	var err := http.request(BASE_URL + path, headers, HTTPClient.METHOD_DELETE, "")
	if err != OK:
		push_error("GameAPI: failed to start DELETE %s" % path)
		http.queue_free()


func _http_post(path: String, on_done: Callable, body_str: String = "") -> void:
    var http := HTTPRequest.new()
    add_child(http)
    http.request_completed.connect(
        func(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
            http.queue_free()
            if result != HTTPRequest.RESULT_SUCCESS:
                push_error("GameAPI: network error on POST %s" % path)
                return
            var parsed = JSON.parse_string(body.get_string_from_utf8())
            on_done.call(code, parsed if parsed != null else {})
    )
    var headers := PackedStringArray(["Content-Type: application/json"])
    var err := http.request(BASE_URL + path, headers, HTTPClient.METHOD_POST, body_str)
    if err != OK:
        push_error("GameAPI: failed to start POST %s" % path)
        http.queue_free()
