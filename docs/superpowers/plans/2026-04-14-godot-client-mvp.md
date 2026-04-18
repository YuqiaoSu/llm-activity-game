# LLM Activity Game — Godot Client (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the minimum Godot 4.6 client that shows the companion with evolution stage, displays per-category XP, lets the player trigger reward syncs, shows item-drop popups, and lists inventory.

**Architecture:** Godot 4.6.1 project in `game-client/`; two persistent autoloads (`GameAPI` for all HTTP, `NotificationBus` for a 3-second polling loop); three scenes (Main, Inventory, NotificationOverlay registered as a CanvasLayer autoload so it persists across scene changes). All data comes from `localhost:8765`. Companion and rarity badges use placeholder ColorRects — no art assets required. Task 1 enriches the services inventory endpoint and notification payload so the client has item names and rarities.

**Tech Stack:** Godot 4.6.1 (`C:\Users\Simon\Desktop\MCP\Godot_v4.6.1-stable_win64.exe`), GDScript, Python game services on `localhost:8765`.

---

## File Map

```
game-client/
  project.godot                         # 640×480 window, three autoloads, main scene
  .gitignore                            # Excludes .godot/ cache and *.import
  icon.svg                              # Placeholder blue square icon
  autoloads/
    GameAPI.gd                          # All HTTP; emits profile_updated, inventory_updated,
                                        #   notifications_updated, poll_completed signals
    NotificationBus.gd                  # 3s Timer; deduplicates seen notification IDs;
                                        #   emits item_dropped(notif: Dictionary)
  scenes/
    Main.tscn                           # Root: companion ColorRect, level/XP labels,
                                        #   per-category XP bars, poll + inventory buttons
    Main.gd                             # Connects to GameAPI signals; rebuilds XP bars on data
    Inventory.tscn                      # Scrollable item list screen
    Inventory.gd                        # Fetches inventory; builds item cards dynamically
    NotificationOverlay.tscn            # CanvasLayer (layer=10); hidden Panel shown on drop
    NotificationOverlay.gd              # Listens to NotificationBus; sets rarity color; acks on OK
  utils/
    RarityColor.gd                      # class_name RarityColor; static for_rarity(str)->Color
  tests/
    TestRarityColor.tscn                # Headless test scene (root: Node)
    TestRarityColor.gd                  # _ready() asserts all 5 rarity colors; quits with exit code
    TestNotificationBus.tscn            # Headless test scene (root: Node)
    TestNotificationBus.gd             # Tests dedup logic by calling _on_notifications() directly

Also modifies:
  services/api/routers/inventory.py    # JOIN with item_definitions; adds name/rarity/category/icon
  services/reward_ledger/ledger.py     # Adds item_name + category to notification payload
  services/tests/test_api.py           # Asserts enriched inventory fields
```

---

## Task 1: Enrich Services for the Client

**Files:**
- Modify: `services/api/routers/inventory.py`
- Modify: `services/reward_ledger/ledger.py`
- Modify: `services/tests/test_api.py`

The `/inventory` endpoint currently returns raw table rows without item names or rarities. The notification payload lacks item name. Both must be enriched before the Godot client can display meaningful data.

- [ ] **Step 1: Update test_api.py — assert enriched inventory fields (RED)**

In `services/tests/test_api.py`, replace `test_get_inventory`:

```python
def test_get_inventory(client):
    r = client.get("/inventory")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["item_id"] == "scroll_001"
    assert items[0]["name"] == "Scroll"      # enriched from item_definitions JSON
    assert items[0]["rarity"] == "COMMON"    # enriched from item_definitions JSON
    assert items[0]["category"] == "WORK"    # enriched from item_definitions JSON
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd C:\Users\Simon\Desktop\llm-activity-project\llm-activity-game
python -m pytest services/tests/test_api.py::test_get_inventory -v
```

Expected: FAIL — `KeyError: 'name'` (the column does not exist yet).

- [ ] **Step 3: Rewrite inventory.py to JOIN item_definitions**

```python
# services/api/routers/inventory.py
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def get_inventory(request: Request) -> list[dict]:
    db = request.app.state.db
    rows = db.execute(
        """
        SELECT
            i.instance_id, i.character_id, i.item_id,
            i.acquired_at, i.source_chunk, i.equipped, i.placed_in,
            json_extract(d.data, '$.name')     AS name,
            json_extract(d.data, '$.rarity')   AS rarity,
            json_extract(d.data, '$.category') AS category,
            json_extract(d.data, '$.icon')     AS icon
        FROM inventory i
        LEFT JOIN item_definitions d ON i.item_id = d.item_id
        WHERE i.character_id = 'player_default'
        ORDER BY i.acquired_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 4: Update ledger.py — add item_name and category to notification payload**

In `services/reward_ledger/ledger.py`, replace the payload block inside `record_drop`:

```python
    # Replace this:
    payload = json.dumps({
        "item_id": item.item_id,
        "instance_id": instance_id,
        "rarity": item.rarity.value,
    })

    # With this:
    payload = json.dumps({
        "item_id": item.item_id,
        "instance_id": instance_id,
        "item_name": item.name,
        "rarity": item.rarity.value,
        "category": item.category.value,
    })
```

- [ ] **Step 5: Run full test suite (GREEN)**

```bash
python -m pytest services/tests/ -v
```

Expected: 93 passed. (`test_get_inventory` now passes with enriched fields.)

- [ ] **Step 6: Commit**

```bash
git add services/api/routers/inventory.py services/reward_ledger/ledger.py services/tests/test_api.py
git commit -m "feat: enrich inventory endpoint and notification payload for Godot client"
```

---

## Task 2: Godot Project Bootstrap & RarityColor

**Files:**
- Create: `game-client/project.godot`
- Create: `game-client/.gitignore`
- Create: `game-client/icon.svg`
- Create: `game-client/utils/RarityColor.gd`
- Create: `game-client/scenes/NotificationOverlay.tscn` (stub — replaced in Task 5)
- Create: `game-client/tests/TestRarityColor.gd`
- Create: `game-client/tests/TestRarityColor.tscn`

The stub NotificationOverlay must exist before `project.godot` registers it as an autoload; Godot errors on startup if the autoload path is missing.

- [ ] **Step 1: Write TestRarityColor.gd (RED — RarityColor doesn't exist yet)**

```gdscript
# game-client/tests/TestRarityColor.gd
extends Node

var _passed := 0
var _failed := 0


func _ready() -> void:
    _check("COMMON is gray",      RarityColor.for_rarity("COMMON")    == Color(0.70, 0.70, 0.70))
    _check("UNCOMMON is green",   RarityColor.for_rarity("UNCOMMON")  == Color(0.18, 0.80, 0.44))
    _check("RARE is blue",        RarityColor.for_rarity("RARE")      == Color(0.27, 0.58, 1.00))
    _check("EPIC is purple",      RarityColor.for_rarity("EPIC")      == Color(0.64, 0.19, 0.85))
    _check("LEGENDARY is orange", RarityColor.for_rarity("LEGENDARY") == Color(1.00, 0.50, 0.00))
    _check("unknown is gray",     RarityColor.for_rarity("MYSTERY")   == Color(0.70, 0.70, 0.70))
    print("RarityColor: %d passed, %d failed" % [_passed, _failed])
    get_tree().quit(1 if _failed > 0 else 0)


func _check(label: String, ok: bool) -> void:
    if ok:
        _passed += 1
        print("  PASS: %s" % label)
    else:
        _failed += 1
        push_error("  FAIL: %s" % label)
```

- [ ] **Step 2: Create project.godot**

```ini
; Engine configuration file.
config_version=5

[application]

config/name="LLM Activity Game"
run/main_scene="res://scenes/Main.tscn"
config/features=PackedStringArray("4.6", "GL Compatibility")
config/icon="res://icon.svg"

[autoload]

GameAPI="*res://autoloads/GameAPI.gd"
NotificationBus="*res://autoloads/NotificationBus.gd"
NotificationOverlay="*res://scenes/NotificationOverlay.tscn"

[display]

window/size/viewport_width=640
window/size/viewport_height=480
window/size/resizable=false

[rendering]

renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
```

- [ ] **Step 3: Create .gitignore**

```
# Godot cache
.godot/
*.import

# Export
export_presets.cfg
```

- [ ] **Step 4: Create icon.svg**

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128">
  <rect width="128" height="128" fill="#3d7eed" rx="20"/>
</svg>
```

- [ ] **Step 5: Create stub scenes/NotificationOverlay.tscn (placeholder — full version in Task 5)**

```
[gd_scene format=3]

[node name="NotificationOverlay" type="CanvasLayer"]
layer = 10
```

- [ ] **Step 6: Create tests/TestRarityColor.tscn**

```
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://tests/TestRarityColor.gd" id="1"]

[node name="TestRarityColor" type="Node"]
script = ExtResource("1")
```

- [ ] **Step 7: Run test — expect FAIL (RarityColor not defined)**

```bash
"C:\Users\Simon\Desktop\MCP\Godot_v4.6.1-stable_win64.exe" --headless --path "C:\Users\Simon\Desktop\llm-activity-project\llm-activity-game\game-client" res://tests/TestRarityColor.tscn 2>&1
```

Expected: Error — `Identifier "RarityColor" not declared in the current scope` or similar parser error.

- [ ] **Step 8: Create utils/RarityColor.gd (GREEN)**

```gdscript
# game-client/utils/RarityColor.gd
class_name RarityColor

const _COLORS := {
    "COMMON":    Color(0.70, 0.70, 0.70),
    "UNCOMMON":  Color(0.18, 0.80, 0.44),
    "RARE":      Color(0.27, 0.58, 1.00),
    "EPIC":      Color(0.64, 0.19, 0.85),
    "LEGENDARY": Color(1.00, 0.50, 0.00),
}


static func for_rarity(rarity: String) -> Color:
    return _COLORS.get(rarity, Color(0.70, 0.70, 0.70))
```

- [ ] **Step 9: Run test — expect PASS**

```bash
"C:\Users\Simon\Desktop\MCP\Godot_v4.6.1-stable_win64.exe" --headless --path "C:\Users\Simon\Desktop\llm-activity-project\llm-activity-game\game-client" res://tests/TestRarityColor.tscn 2>&1
```

Expected output:
```
  PASS: COMMON is gray
  PASS: UNCOMMON is green
  PASS: RARE is blue
  PASS: EPIC is purple
  PASS: LEGENDARY is orange
  PASS: unknown is gray
RarityColor: 6 passed, 0 failed
```

- [ ] **Step 10: Commit**

```bash
git add game-client/
git commit -m "feat: godot project bootstrap, RarityColor utility, stub overlay"
```

---

## Task 3: GameAPI & NotificationBus Autoloads

**Files:**
- Create: `game-client/autoloads/GameAPI.gd`
- Create: `game-client/autoloads/NotificationBus.gd`
- Create: `game-client/tests/TestNotificationBus.gd`
- Create: `game-client/tests/TestNotificationBus.tscn`

- [ ] **Step 1: Write TestNotificationBus.gd (RED — NotificationBus doesn't exist yet)**

```gdscript
# game-client/tests/TestNotificationBus.gd
extends Node

var _passed := 0
var _failed := 0
var _dropped: Array = []


func _ready() -> void:
    # Reset autoload state between test scenarios
    NotificationBus._seen_ids = PackedStringArray()
    NotificationBus.item_dropped.connect(func(n: Dictionary) -> void:
        _dropped.append(n)
    )

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
    get_tree().quit(1 if _failed > 0 else 0)


func _check(label: String, ok: bool) -> void:
    if ok:
        _passed += 1
        print("  PASS: %s" % label)
    else:
        _failed += 1
        push_error("  FAIL: %s" % label)
```

- [ ] **Step 2: Create tests/TestNotificationBus.tscn**

```
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://tests/TestNotificationBus.gd" id="1"]

[node name="TestNotificationBus" type="Node"]
script = ExtResource("1")
```

- [ ] **Step 3: Create autoloads/GameAPI.gd**

```gdscript
# game-client/autoloads/GameAPI.gd
extends Node

const BASE_URL := "http://localhost:8765"

signal profile_updated(data: Dictionary)
signal inventory_updated(items: Array)
signal notifications_updated(notifs: Array)
signal poll_completed(result: String)


func fetch_profile() -> void:
    _get("/player/profile", func(data: Dictionary) -> void:
        profile_updated.emit(data)
    )


func fetch_inventory() -> void:
    _get("/inventory", func(data) -> void:
        inventory_updated.emit(data as Array)
    )


func fetch_notifications() -> void:
    _get("/notifications/pending", func(data) -> void:
        notifications_updated.emit(data as Array)
    )


func ack_notification(nid: String) -> void:
    _post("/notifications/%s/ack" % nid, func(_code: int, _data: Dictionary) -> void:
        pass
    )


func poll_now() -> void:
    _post("/sync/poll-now", func(code: int, data: Dictionary) -> void:
        match code:
            200:
                poll_completed.emit(data.get("result", "UNKNOWN"))
            503:
                poll_completed.emit("ON_COOLDOWN")
            _:
                poll_completed.emit("ERROR")
    )


# ── internal helpers ──────────────────────────────────────────────────────────

func _get(path: String, on_done: Callable) -> void:
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


func _post(path: String, on_done: Callable) -> void:
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
```

- [ ] **Step 4: Create autoloads/NotificationBus.gd**

```gdscript
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
```

- [ ] **Step 5: Run NotificationBus test — expect PASS**

```bash
"C:\Users\Simon\Desktop\MCP\Godot_v4.6.1-stable_win64.exe" --headless --path "C:\Users\Simon\Desktop\llm-activity-project\llm-activity-game\game-client" res://tests/TestNotificationBus.tscn 2>&1
```

Expected:
```
  PASS: both new notifs emitted
  PASS: duplicate notifs not re-emitted
  PASS: only new notif emitted
  PASS: emitted notif is ccc
NotificationBus: 4 passed, 0 failed
```

- [ ] **Step 6: Commit**

```bash
git add game-client/autoloads/ game-client/tests/TestNotificationBus.gd game-client/tests/TestNotificationBus.tscn
git commit -m "feat: add GameAPI and NotificationBus autoloads"
```

---

## Task 4: Main Scene

**Files:**
- Create: `game-client/scenes/Main.tscn`
- Create: `game-client/scenes/Main.gd`

- [ ] **Step 1: Create scenes/Main.tscn**

```
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scenes/Main.gd" id="1"]

[node name="Main" type="Control"]
anchor_right = 1.0
anchor_bottom = 1.0
script = ExtResource("1")

[node name="VBox" type="VBoxContainer" parent="."]
anchor_right = 1.0
anchor_bottom = 1.0
offset_left = 16
offset_top = 16
offset_right = -16
offset_bottom = -16

[node name="TitleLabel" type="Label" parent="VBox"]
text = "LLM Activity Game"

[node name="CompanionArea" type="Control" parent="VBox"]
custom_minimum_size = Vector2(128, 128)

[node name="CompanionRect" type="ColorRect" parent="VBox/CompanionArea"]
anchor_right = 1.0
anchor_bottom = 1.0
color = Color(0.8, 0.8, 0.9, 1)

[node name="EvolutionLabel" type="Label" parent="VBox/CompanionArea"]
anchor_left = 0.5
anchor_top = 0.5
anchor_right = 0.5
anchor_bottom = 0.5
offset_left = -40
offset_top = -10
offset_right = 40
offset_bottom = 10
text = "Hatchling"
horizontal_alignment = 1
vertical_alignment = 1

[node name="LevelLabel" type="Label" parent="VBox"]
text = "Level 1"

[node name="XPLabel" type="Label" parent="VBox"]
text = "0 XP total"

[node name="CategoryContainer" type="VBoxContainer" parent="VBox"]

[node name="PollStatus" type="Label" parent="VBox"]
text = ""

[node name="Buttons" type="HBoxContainer" parent="VBox"]

[node name="PollButton" type="Button" parent="VBox/Buttons"]
text = "Check Rewards"

[node name="InventoryButton" type="Button" parent="VBox/Buttons"]
text = "Inventory →"
```

- [ ] **Step 2: Create scenes/Main.gd**

```gdscript
# game-client/scenes/Main.gd
extends Control

@onready var _companion_rect: ColorRect       = $VBox/CompanionArea/CompanionRect
@onready var _evolution_label: Label          = $VBox/CompanionArea/EvolutionLabel
@onready var _level_label: Label              = $VBox/LevelLabel
@onready var _xp_label: Label                 = $VBox/XPLabel
@onready var _category_container: VBoxContainer = $VBox/CategoryContainer
@onready var _poll_status: Label              = $VBox/PollStatus
@onready var _poll_button: Button             = $VBox/Buttons/PollButton

const _STAGE_COLORS := [
    Color(0.80, 0.80, 0.90),  # 0 — Hatchling  (pale blue)
    Color(0.50, 0.80, 0.50),  # 1 — Growing    (green)
    Color(0.30, 0.60, 1.00),  # 2 — Mature     (bright blue)
    Color(0.80, 0.40, 1.00),  # 3 — Legendary  (purple)
]
const _STAGE_NAMES := ["Hatchling", "Growing", "Mature", "Legendary"]
const _MAX_XP_PER_CAT := 5000


func _ready() -> void:
    GameAPI.profile_updated.connect(_on_profile)
    GameAPI.poll_completed.connect(_on_poll_result)
    _poll_button.pressed.connect(_on_poll_pressed)
    $VBox/Buttons/InventoryButton.pressed.connect(func() -> void:
        get_tree().change_scene_to_file("res://scenes/Inventory.tscn")
    )
    GameAPI.fetch_profile()


func _on_profile(data: Dictionary) -> void:
    var stage := mini(data.get("evolution_stage", 0) as int, _STAGE_COLORS.size() - 1)
    _companion_rect.color = _STAGE_COLORS[stage]
    _evolution_label.text = _STAGE_NAMES[stage]
    _level_label.text = "Level %d" % data.get("level", 1)
    _xp_label.text = "%d XP total" % data.get("total_xp", 0)
    _rebuild_xp_bars(data.get("category_xp", {}) as Dictionary)


func _rebuild_xp_bars(category_xp: Dictionary) -> void:
    for child in _category_container.get_children():
        child.queue_free()
    for category: String in category_xp:
        var hbox := HBoxContainer.new()
        var lbl := Label.new()
        lbl.text = category.capitalize()
        lbl.custom_minimum_size.x = 80
        var bar := ProgressBar.new()
        bar.max_value = _MAX_XP_PER_CAT
        bar.value = category_xp[category] as int
        bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        bar.show_percentage = false
        hbox.add_child(lbl)
        hbox.add_child(bar)
        _category_container.add_child(hbox)


func _on_poll_pressed() -> void:
    _poll_button.disabled = true
    _poll_status.text = "Checking..."
    GameAPI.poll_now()


func _on_poll_result(result: String) -> void:
    _poll_button.disabled = false
    match result:
        "OK":
            _poll_status.text = "Rewards processed!"
            GameAPI.fetch_profile()
        "NO_NEW_CHUNKS":
            _poll_status.text = "No new activity"
        "ON_COOLDOWN":
            _poll_status.text = "On cooldown — try again shortly"
        _:
            _poll_status.text = "Sync error — is the tracker running?"
```

- [ ] **Step 3: Start services and run the game**

```bash
# Terminal 1: start services (run from llm-activity-game/)
python -m services.seeds
python -m uvicorn services.api.main:app --host 0.0.0.0 --port 8765

# Terminal 2: open game
"C:\Users\Simon\Desktop\MCP\Godot_v4.6.1-stable_win64.exe" --path "C:\Users\Simon\Desktop\llm-activity-project\llm-activity-game\game-client"
```

Expected: 640×480 window opens. Companion rect is pale blue. "Level 1", "0 XP total". "Check Rewards" button is clickable. Clicking it disables the button, shows "Checking...", then shows "No new activity" (since the tracker isn't running). "Inventory →" changes to Inventory scene (may show error until Task 6 — OK for now).

- [ ] **Step 4: Commit**

```bash
git add game-client/scenes/Main.tscn game-client/scenes/Main.gd
git commit -m "feat: add main scene with companion display, XP bars, and sync button"
```

---

## Task 5: Notification Overlay

**Files:**
- Replace: `game-client/scenes/NotificationOverlay.tscn` (was a stub)
- Create: `game-client/scenes/NotificationOverlay.gd`

- [ ] **Step 1: Replace NotificationOverlay.tscn with full version**

```
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scenes/NotificationOverlay.gd" id="1"]

[node name="NotificationOverlay" type="CanvasLayer"]
layer = 10
script = ExtResource("1")

[node name="Panel" type="Panel" parent="."]
anchor_left = 0.5
anchor_top = 0.5
anchor_right = 0.5
anchor_bottom = 0.5
offset_left = -140
offset_top = -110
offset_right = 140
offset_bottom = 110
visible = false

[node name="VBox" type="VBoxContainer" parent="Panel"]
anchor_right = 1.0
anchor_bottom = 1.0
offset_left = 12
offset_top = 12
offset_right = -12
offset_bottom = -12

[node name="TitleLabel" type="Label" parent="Panel/VBox"]
text = "Item Dropped!"
horizontal_alignment = 1

[node name="RarityBar" type="ColorRect" parent="Panel/VBox"]
custom_minimum_size = Vector2(0, 6)
color = Color(0.7, 0.7, 0.7, 1)

[node name="ItemNameLabel" type="Label" parent="Panel/VBox"]
text = ""
horizontal_alignment = 1

[node name="RarityLabel" type="Label" parent="Panel/VBox"]
text = ""
horizontal_alignment = 1

[node name="OKButton" type="Button" parent="Panel/VBox"]
text = "OK"
```

- [ ] **Step 2: Create scenes/NotificationOverlay.gd**

```gdscript
# game-client/scenes/NotificationOverlay.gd
extends CanvasLayer

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
```

- [ ] **Step 3: Manually test — inject a notification and watch the popup appear**

With services and game running, insert a notification directly into the database:

```bash
cd C:\Users\Simon\Desktop\llm-activity-project\llm-activity-game
python -c "
import sqlite3, json, uuid
from datetime import datetime, timezone
conn = sqlite3.connect('game.db')
nid = str(uuid.uuid4())
payload = json.dumps({'item_id': 'focus_crystal_rare', 'item_name': 'Radiant Focus Crystal', 'rarity': 'RARE', 'instance_id': str(uuid.uuid4())})
now = datetime.now(timezone.utc).isoformat()
conn.execute(\"INSERT INTO pending_notifications (notification_id, character_id, event_type, payload, created_at) VALUES (?, 'player_default', 'item_drop', ?, ?)\", (nid, payload, now))
conn.commit(); conn.close(); print('Inserted:', nid)
"
```

Expected: Within 3 seconds, a panel appears over the game window:
- "Item Dropped!" title
- Blue rarity bar (RARE)
- "Radiant Focus Crystal"
- "RARE"
- "OK" button — clicking it dismisses the panel

- [ ] **Step 4: Commit**

```bash
git add game-client/scenes/NotificationOverlay.tscn game-client/scenes/NotificationOverlay.gd
git commit -m "feat: add notification overlay with rarity color and ack on dismiss"
```

---

## Task 6: Inventory Screen

**Files:**
- Create: `game-client/scenes/Inventory.tscn`
- Create: `game-client/scenes/Inventory.gd`

- [ ] **Step 1: Create scenes/Inventory.tscn**

```
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scenes/Inventory.gd" id="1"]

[node name="Inventory" type="Control"]
anchor_right = 1.0
anchor_bottom = 1.0
script = ExtResource("1")

[node name="VBox" type="VBoxContainer" parent="."]
anchor_right = 1.0
anchor_bottom = 1.0
offset_left = 16
offset_top = 16
offset_right = -16
offset_bottom = -16

[node name="Header" type="HBoxContainer" parent="VBox"]

[node name="BackButton" type="Button" parent="VBox/Header"]
text = "← Back"

[node name="CountLabel" type="Label" parent="VBox/Header"]
text = "Inventory"
size_flags_horizontal = 3

[node name="Scroll" type="ScrollContainer" parent="VBox"]
size_flags_vertical = 3

[node name="ItemList" type="VBoxContainer" parent="VBox/Scroll"]
size_flags_horizontal = 3
```

- [ ] **Step 2: Create scenes/Inventory.gd**

```gdscript
# game-client/scenes/Inventory.gd
extends Control

@onready var _count_label: Label       = $VBox/Header/CountLabel
@onready var _item_list: VBoxContainer = $VBox/Scroll/ItemList


func _ready() -> void:
    $VBox/Header/BackButton.pressed.connect(func() -> void:
        get_tree().change_scene_to_file("res://scenes/Main.tscn")
    )
    GameAPI.inventory_updated.connect(_on_inventory)
    GameAPI.fetch_inventory()


func _on_inventory(items: Array) -> void:
    _count_label.text = "Inventory (%d)" % items.size()
    for child in _item_list.get_children():
        child.queue_free()
    for item: Dictionary in items:
        _item_list.add_child(_make_card(item))


func _make_card(item: Dictionary) -> Control:
    var hbox := HBoxContainer.new()

    var dot := ColorRect.new()
    dot.custom_minimum_size = Vector2(14, 14)
    dot.color = RarityColor.for_rarity(item.get("rarity", "COMMON"))

    var name_lbl := Label.new()
    name_lbl.text = item.get("name", item.get("item_id", "?"))
    name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL

    var cat_lbl := Label.new()
    cat_lbl.text = (item.get("category", "") as String).capitalize()

    hbox.add_child(dot)
    hbox.add_child(name_lbl)
    hbox.add_child(cat_lbl)
    return hbox
```

- [ ] **Step 3: Run the game and navigate to inventory**

With services running, open the game and click "Inventory →".

Expected: Screen changes to Inventory. "Inventory (0)" if no items. "← Back" returns to Main.

To add items, use the Python seed script and then poll:

```bash
# From llm-activity-game/
python -c "
import sqlite3, json, uuid
from datetime import datetime, timezone
conn = sqlite3.connect('game.db')
for item_id in ['focus_crystal_common', 'moonstone_common', 'lucky_die_common']:
    iid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(\"INSERT OR IGNORE INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) VALUES (?, 'player_default', ?, ?, 'manual')\", (iid, item_id, now))
conn.commit(); conn.close(); print('Seeded 3 inventory items')
"
```

Then click "← Back" and "Inventory →" again to refresh. Expected: "Inventory (3)" with rows:
- Gray dot — Focus Crystal — Work
- Gray dot — Moonstone — Sleep
- Gray dot — Lucky Die — Game

- [ ] **Step 4: Commit**

```bash
git add game-client/scenes/Inventory.tscn game-client/scenes/Inventory.gd
git commit -m "feat: add inventory screen with rarity-colored item cards"
```

---

## What This Plan Defers

| Feature | When |
|---|---|
| Places screen (home study, slots) | Plan 2 — place tables and service already exist |
| Real companion sprites | When art assets are created; replace ColorRect with Sprite2D |
| Background auto-polling (no manual trigger needed) | Requires tracker running locally; add APScheduler call to SyncAgent |
| Steam integration | After Godot client is stable |
| Dungeon / quest systems | After home system |
