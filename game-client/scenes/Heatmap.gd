# game-client/scenes/Heatmap.gd
extends Control

@onready var _grid:       GridContainer = $VBox/Scroll/Grid
@onready var _title_lbl:  Label         = $VBox/Header/TitleLabel
@onready var _weeks_spin: SpinBox       = $VBox/Controls/WeeksSpin

# Intensity → color (GitHub-style green ramp)
const _INTENSITY_COLORS := [
	Color(0.15, 0.15, 0.15),   # 0 — no activity   (dark grey)
	Color(0.20, 0.40, 0.20),   # 1 — low            (dark green)
	Color(0.20, 0.65, 0.20),   # 2 — medium         (mid green)
	Color(0.20, 0.88, 0.20),   # 3 — high           (bright green)
	Color(0.55, 1.00, 0.40),   # 4 — very high      (lime)
]

const _DAY_NAMES := ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const _CELL_SIZE := 14
const _CELL_GAP  := 2

var _current_weeks: int = 12


func _ready() -> void:
	$VBox/Header/BackButton.pressed.connect(func() -> void:
		get_tree().change_scene_to_file("res://scenes/Main.tscn")
	)
	_weeks_spin.min_value = 4
	_weeks_spin.max_value = 52
	_weeks_spin.step      = 1
	_weeks_spin.value     = _current_weeks
	_weeks_spin.value_changed.connect(func(v: float) -> void:
		_current_weeks = int(v)
		GameAPI.fetch_heatmap(_current_weeks)
	)
	GameAPI.heatmap_updated.connect(_on_heatmap)
	GameAPI.fetch_heatmap(_current_weeks)


func _exit_tree() -> void:
	if GameAPI.heatmap_updated.is_connected(_on_heatmap):
		GameAPI.heatmap_updated.disconnect(_on_heatmap)


func _on_heatmap(entries: Array) -> void:
	_title_lbl.text = "Activity Heatmap (%d weeks)" % _current_weeks

	# Clear old cells
	for child in _grid.get_children():
		child.queue_free()

	# Columns = weeks, each column is one week (7 days top=Mon bottom=Sun).
	# entries are oldest-first, exactly _current_weeks × 7 entries.
	var weeks := _current_weeks
	_grid.columns = weeks

	# Build a 2-D array: week_col[col][row] → entry
	# entries[0] is the oldest day → col 0, row = weekday index (0=Mon)
	# We need to figure out which weekday the first entry falls on so the
	# grid starts on the right day.  For simplicity (no weekday offset needed
	# for the functionality), we just fill column by column, 7 rows each.
	var total := entries.size()

	# We render col-major: column 0 = oldest week, column N-1 = newest week.
	# Row 0 = first day of that week, row 6 = last.
	# GridContainer fills row-major, so we transpose: build a flat row-major list.
	var cells: Array[Dictionary] = []
	cells.resize(total)
	for i in range(total):
		cells[i] = entries[i] as Dictionary

	# GridContainer with `columns = weeks` fills across weeks first.
	# We want each ROW to be the same weekday across all weeks → transpose.
	# entries are col-major (7 per week), we need row-major (weeks per row).
	# cell at (week_col=w, day_row=d) lives at entries index w*7+d.
	# GridContainer fills position r*weeks+w, so we output in order (d, w).
	for day_row in range(7):
		for week_col in range(weeks):
			var idx := week_col * 7 + day_row
			var entry: Dictionary = {}
			if idx < total:
				entry = entries[idx] as Dictionary
			_grid.add_child(_make_cell(entry, day_row, week_col == weeks - 1))


func _make_cell(entry: Dictionary, day_row: int, is_last_week: bool) -> Control:
	var intensity: int = entry.get("intensity", 0) as int
	intensity = clampi(intensity, 0, 4)

	var cell := ColorRect.new()
	cell.custom_minimum_size = Vector2(_CELL_SIZE, _CELL_SIZE)
	cell.color = _INTENSITY_COLORS[intensity]

	# Tooltip showing date + XP
	var d: String = entry.get("date", "")
	var xp: int   = entry.get("total_xp", 0) as int
	if d != "":
		cell.tooltip_text = "%s · %d XP" % [d, xp]

	return cell
