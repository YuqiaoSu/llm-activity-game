# game-client/autoloads/GameAPI.gd
extends Node

const BASE_URL := "http://localhost:8765"

signal profile_updated(data: Dictionary)
signal inventory_updated(items: Array)
signal notifications_updated(notifs: Array)
signal poll_completed(result: String)
signal equip_updated(item_id: String, equipped: bool)
signal places_updated(places: Array)


func fetch_profile() -> void:
    _http_get("/player/profile", func(data: Dictionary) -> void:
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


func ack_notification(nid: String) -> void:
    var re := RegEx.new()
    re.compile("^[0-9a-fA-F\\-]{8,40}$")
    if re.search(nid) == null:
        push_error("GameAPI: invalid notification ID: %s" % nid)
        return
    _http_post("/notifications/%s/ack" % nid, func(_code: int, _data: Dictionary) -> void:
        pass
    )


func fetch_places() -> void:
    _http_get("/places", func(data) -> void:
        if data is Array:
            places_updated.emit(data as Array)
        else:
            push_error("GameAPI: /places response is not an Array")
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


func _http_post(path: String, on_done: Callable) -> void:
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
    var err := http.request(BASE_URL + path, headers, HTTPClient.METHOD_POST, "")
    if err != OK:
        push_error("GameAPI: failed to start POST %s" % path)
        http.queue_free()
