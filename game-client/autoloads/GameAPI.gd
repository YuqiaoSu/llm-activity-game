# game-client/autoloads/GameAPI.gd
extends Node

const BASE_URL := "http://localhost:8765"

var _cached_profile: Dictionary = {}

signal profile_updated(data: Dictionary)
signal inventory_updated(items: Array)
signal notifications_updated(notifs: Array)
signal poll_completed(result: String)
signal poll_summary_ready(summary: Dictionary)
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
signal craft_completed(ok: bool, data: Dictionary)
signal daily_goals_updated(entries: Array)
signal goal_streak_updated(data: Dictionary)
signal streak_reward_claimed(data: Dictionary)
signal recap_updated(data: Dictionary)
signal catalogue_updated(items: Array)
signal leaderboard_updated(data: Dictionary)
signal daily_chart_updated(entries: Array)
signal events_updated(entries: Array)
signal active_events_updated(entries: Array)
signal donation_completed(ok: bool, data: Dictionary)
signal heatmap_updated(entries: Array)
signal trade_offers_updated(offers: Array)
signal trade_accepted(ok: bool, data: Dictionary)
signal seasonal_leaderboard_updated(data: Dictionary)
signal recipes_updated(entries: Array)
signal pinned_achievements_updated(entries: Array)
signal achievement_pinned(data: Dictionary)
signal achievement_unpinned(data: Dictionary)
signal wishlist_updated(entries: Array)
signal wishlist_toggled(data: Dictionary)
signal daily_recap_updated(data: Dictionary)
signal compare_updated(data: Dictionary)
signal race_updated(data: Dictionary)
signal feed_updated(entries: Array)
signal stats_summary_updated(data: Dictionary)
signal drop_odds_updated(entries: Array)
signal item_sets_updated(entries: Array)
signal challenge_leaderboard_updated(data: Dictionary)
signal multipliers_updated(entries: Array)
signal challenge_history_updated(entries: Array)
signal titles_updated(entries: Array)
signal title_equipped(data: Dictionary)
signal daily_bonus_updated(data: Dictionary)

var last_challenge_id: String = ""


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


func ack_notifications_by_type(event_type: String) -> void:
	var body := JSON.stringify({"event_type": event_type})
	_http_post("/notifications/ack-by-type", func(_code: int, _data: Dictionary) -> void:
		pass
	, body)


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


func fetch_daily_chart(days: int = 14) -> void:
	_http_get("/history/daily?days=%d" % days, func(data) -> void:
		if data is Array:
			daily_chart_updated.emit(data as Array)
		else:
			push_error("GameAPI: /history/daily response is not an Array")
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


func fetch_leaderboard(weeks: int = 8) -> void:
	_http_get("/leaderboard/weekly?weeks=%d" % weeks, func(data) -> void:
		if data is Dictionary:
			leaderboard_updated.emit(data as Dictionary)
		else:
			push_error("GameAPI: /leaderboard/weekly response is not a Dictionary")
	)


func fetch_catalogue(category: String = "") -> void:
	var path := "/catalogue"
	if not category.is_empty():
		path = "/catalogue/by-category/" + category
	_http_get(path, func(data) -> void:
		if data is Array:
			catalogue_updated.emit(data as Array)
		else:
			push_error("GameAPI: /catalogue response is not an Array")
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


func fetch_goal_streak() -> void:
	_http_get("/goals/streak", func(data) -> void:
		if data is Dictionary:
			goal_streak_updated.emit(data as Dictionary)
		else:
			push_error("GameAPI: /goals/streak response is not a Dictionary")
	)


func claim_streak_reward() -> void:
	_http_post("/goals/claim-streak-reward", func(code: int, data: Dictionary) -> void:
		streak_reward_claimed.emit(data)
	)


func craft_items(item_id_a: String, item_id_b: String) -> void:
	var body_str := JSON.stringify({"item_id_a": item_id_a, "item_id_b": item_id_b})
	_http_post("/inventory/craft", func(code: int, data: Dictionary) -> void:
		craft_completed.emit(code == 200, data)
	, body_str)


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


func fetch_events() -> void:
	_http_get("/events", func(data) -> void:
		if data is Array:
			events_updated.emit(data as Array)
		else:
			push_error("GameAPI: /events response is not an Array")
	)


func donate_item_to_place(place_id: String, instance_id: String) -> void:
	var body_str := JSON.stringify({"instance_id": instance_id})
	_http_post("/places/%s/donate" % place_id, func(code: int, data: Dictionary) -> void:
		donation_completed.emit(code == 200, data)
	, body_str)


func fetch_active_events() -> void:
	_http_get("/events/active", func(data) -> void:
		if data is Array:
			active_events_updated.emit(data as Array)
		else:
			push_error("GameAPI: /events/active response is not an Array")
	)


func fetch_recipes() -> void:
	_http_get("/inventory/recipes", func(data) -> void:
		if data is Array:
			recipes_updated.emit(data as Array)
		else:
			push_error("GameAPI: /inventory/recipes response is not an Array")
	)


func fetch_pinned_achievements() -> void:
	_http_get("/achievements/pinned", func(data) -> void:
		if data is Array:
			pinned_achievements_updated.emit(data as Array)
		else:
			push_error("GameAPI: /achievements/pinned response is not an Array")
	)


func pin_achievement(achievement_id: String) -> void:
	_http_post("/achievements/%s/pin" % achievement_id, func(code: int, data: Dictionary) -> void:
		if code == 200:
			achievement_pinned.emit(data)
		else:
			push_error("GameAPI: pin_achievement %s → %d" % [achievement_id, code])
	)


func unpin_achievement(achievement_id: String) -> void:
	_http_delete("/achievements/%s/pin" % achievement_id, func(code: int, data: Dictionary) -> void:
		if code == 200:
			achievement_unpinned.emit(data)
		else:
			push_error("GameAPI: unpin_achievement %s → %d" % [achievement_id, code])
	)


func fetch_wishlist() -> void:
	_http_get("/catalogue/wishlist", func(data) -> void:
		if data is Array:
			wishlist_updated.emit(data as Array)
		else:
			push_error("GameAPI: /catalogue/wishlist response is not an Array")
	)


func add_to_wishlist(item_id: String) -> void:
	_http_post("/catalogue/%s/wishlist" % item_id, func(code: int, data: Dictionary) -> void:
		if code == 200:
			wishlist_toggled.emit(data)
		else:
			push_error("GameAPI: add_to_wishlist %s → %d" % [item_id, code])
	)


func fetch_feed(limit: int = 20) -> void:
	_http_get("/feed?limit=%d" % limit, func(data) -> void:
		if data is Array:
			feed_updated.emit(data as Array)
		else:
			push_error("GameAPI: /feed response is not an Array")
	)


func fetch_item_sets() -> void:
	_http_get("/inventory/sets", func(data) -> void:
		if data is Array:
			item_sets_updated.emit(data as Array)
		else:
			push_error("GameAPI: /inventory/sets response is not an Array")
	)


func fetch_drop_odds(category: String) -> void:
	_http_get("/inventory/drop-odds?category=%s" % category, func(data) -> void:
		if data is Array:
			drop_odds_updated.emit(data as Array)
		else:
			push_error("GameAPI: /inventory/drop-odds response is not an Array")
	)


func fetch_titles() -> void:
	_http_get("/player/titles", func(data) -> void:
		if data is Array:
			titles_updated.emit(data as Array)
		else:
			push_error("GameAPI: /player/titles response is not an Array")
	)


func equip_title(title_id: String) -> void:
	_http_post("/player/titles/%s/equip" % title_id, func(code: int, data: Dictionary) -> void:
		if code == 200:
			title_equipped.emit(data)
		else:
			push_error("GameAPI: equip_title %s → %d" % [title_id, code])
	)


func fetch_daily_bonus() -> void:
	_http_get("/challenges/daily-bonus", func(data: Dictionary) -> void:
		if data is Dictionary:
			daily_bonus_updated.emit(data)
		else:
			push_error("GameAPI: /challenges/daily-bonus response is not a Dictionary")
	)


func fetch_challenge_history(weeks: int = 8) -> void:
	_http_get("/challenges/history?weeks=%d" % weeks, func(data) -> void:
		if data is Array:
			challenge_history_updated.emit(data as Array)
		else:
			push_error("GameAPI: /challenges/history response is not an Array")
	)


func fetch_multipliers() -> void:
	_http_get("/sync/multipliers", func(data) -> void:
		if data is Array:
			multipliers_updated.emit(data as Array)
		else:
			push_error("GameAPI: /sync/multipliers response is not an Array")
	)


func fetch_challenge_leaderboard(challenge_id: String) -> void:
	_http_get("/challenges/leaderboard?challenge_id=%s" % challenge_id, func(data) -> void:
		if data is Dictionary:
			challenge_leaderboard_updated.emit(data as Dictionary)
		else:
			push_error("GameAPI: /challenges/leaderboard response is not a Dictionary")
	)


func fetch_stats_summary() -> void:
	_http_get("/stats/summary", func(data) -> void:
		if data is Dictionary:
			stats_summary_updated.emit(data as Dictionary)
		else:
			push_error("GameAPI: /stats/summary response is not a Dictionary")
	)


func fetch_race(other_id: String) -> void:
	_http_get("/leaderboard/race?other_id=%s" % other_id, func(data) -> void:
		if data is Dictionary:
			race_updated.emit(data as Dictionary)
		else:
			push_error("GameAPI: /leaderboard/race response is not a Dictionary")
	)


func fetch_compare(other_id: String) -> void:
	_http_get("/leaderboard/compare?other_id=%s" % other_id, func(data) -> void:
		if data is Dictionary:
			compare_updated.emit(data as Dictionary)
		else:
			push_error("GameAPI: /leaderboard/compare response is not a Dictionary")
	)


func fetch_daily_recap() -> void:
	_http_get("/recap/daily", func(data) -> void:
		if data is Dictionary:
			daily_recap_updated.emit(data as Dictionary)
		else:
			push_error("GameAPI: /recap/daily response is not a Dictionary")
	)


func remove_from_wishlist(item_id: String) -> void:
	_http_delete("/catalogue/%s/wishlist" % item_id, func(code: int, data: Dictionary) -> void:
		if code == 200:
			wishlist_toggled.emit(data)
		else:
			push_error("GameAPI: remove_from_wishlist %s → %d" % [item_id, code])
	)


func fetch_seasonal_leaderboard(months: int = 6) -> void:
	_http_get("/leaderboard/seasonal?months=%d" % months, func(data: Dictionary) -> void:
		seasonal_leaderboard_updated.emit(data)
	)


func fetch_trade_offers() -> void:
	_http_get("/trade/offers", func(data) -> void:
		if data is Array:
			trade_offers_updated.emit(data as Array)
		else:
			push_error("GameAPI: /trade/offers response is not an Array")
	)


func accept_trade(offer_id: String) -> void:
	var body_str := JSON.stringify({"offer_id": offer_id})
	_http_post("/trade/accept", func(code: int, data: Dictionary) -> void:
		trade_accepted.emit(code == 200, data)
	, body_str)


func fetch_heatmap(weeks: int = 12) -> void:
	_http_get("/history/heatmap?weeks=%d" % weeks, func(data) -> void:
		if data is Array:
			heatmap_updated.emit(data as Array)
		else:
			push_error("GameAPI: /history/heatmap response is not an Array")
	)


func poll_now() -> void:
	_http_post("/sync/poll-now", func(code: int, data: Dictionary) -> void:
		match code:
			200:
				var result: String = data.get("result", "UNKNOWN")
				poll_completed.emit(result)
				if result == "OK":
					poll_summary_ready.emit(data)
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
