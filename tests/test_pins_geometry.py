"""Where a numbered marker sits on the chart (static/pins.js, issue #85).

The geometry is pure JavaScript (no Leaflet, no page), so it runs here in Node. The rest of
the chart is checked in headless Edge with tools/check_map_pins.py (not in CI).
Skipped when Node isn't installed (GitHub's Ubuntu runners have it).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PINS_JS = ROOT / "static" / "pins.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")

# A phone chart (390 x 523 px, no panel over it) and a laptop chart (panel covers 416 px).
PHONE = {"left": 0, "top": 0, "right": 390, "bottom": 523}
LAPTOP = {"left": 416, "top": 0, "right": 1440, "bottom": 812}
ONE_ITEM = {"w": 150, "h": 36, "half": 18, "lead": 36}  # "1 4 East Anchorage"
MARGIN = 4


def js(expression: str):
    """Evaluate `expression` with P = the HavenPins functions from static/pins.js."""
    script = (
        "const fs = require('fs'), vm = require('vm'); const ctx = {};"
        f"vm.runInNewContext(fs.readFileSync({json.dumps(str(PINS_JS))}, 'utf8'), ctx);"
        f"const P = ctx.HavenPins; console.log(JSON.stringify({expression}));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def nudged(point, size=ONE_ITEM, side="right", rows=False, chart=PHONE):
    """The nudge for a marker at `point`, and its box after the nudge."""
    return js(
        f"(() => {{ const box = P.boxAt({json.dumps(point)}, {json.dumps(size)}, {json.dumps(side)}, {json.dumps(rows)});"
        f" const n = P.nudgeInside(box, {json.dumps(point)}, {json.dumps(chart)}, {MARGIN});"
        " return { nudge: n, box: { left: box.left + n.x, right: box.right + n.x, top: box.top + n.y,"
        " bottom: box.bottom + n.y } }; })()"
    )


def inside(box, chart):
    return (box["left"] >= chart["left"] and box["right"] <= chart["right"]
            and box["top"] >= chart["top"] and box["bottom"] <= chart["bottom"])


# ---------- Nudging markers inward at the chart's edges ----------

def test_a_pin_just_below_the_top_edge_is_moved_down_so_its_number_is_whole():
    # 5 East Anchorage on a phone: 0.0099 degrees below the sheet's north edge = 12 px from the top,
    # so a 36 px number centred on it stuck out 6 px. Owner, 3 Nov 2026 (PR #91): nudge it inward.
    result = nudged({"x": 200, "y": 12})
    assert result["nudge"] == {"x": 0, "y": 10}
    assert result["box"]["top"] == MARGIN
    assert inside(result["box"], PHONE)


def test_a_pin_near_the_bottom_or_the_sides_is_moved_inward():
    for point in ({"x": 200, "y": 515}, {"x": 6, "y": 300}, {"x": 385, "y": 300}):
        result = nudged(point, side="left" if point["x"] > 300 else "right")
        assert inside(result["box"], PHONE), point


def test_shared_rows_running_off_the_bottom_move_up_until_they_fit():
    rows = {"w": 220, "h": 4 * 36 + 3 * 4, "half": 18, "lead": 36}
    result = nudged({"x": 100, "y": 450}, size=rows, rows=True)
    assert result["box"]["bottom"] == PHONE["bottom"] - MARGIN
    assert inside(result["box"], PHONE)


def test_a_marker_already_inside_is_not_moved():
    assert nudged({"x": 200, "y": 300})["nudge"] == {"x": 0, "y": 0}


def test_a_place_off_the_chart_or_under_the_panel_is_not_pulled_into_view():
    # Zoomed in elsewhere, or under the news panel: the marker stays where its place is.
    assert nudged({"x": 200, "y": -40})["nudge"] == {"x": 0, "y": 0}
    assert nudged({"x": 500, "y": 300})["nudge"] == {"x": 0, "y": 0}  # right of a phone chart
    assert nudged({"x": 300, "y": 400}, chart=LAPTOP)["nudge"] == {"x": 0, "y": 0}  # under the panel


def test_a_pin_just_right_of_the_panel_is_moved_clear_of_it():
    result = nudged({"x": 420, "y": 400}, chart=LAPTOP)
    assert result["nudge"]["x"] > 0
    assert result["box"]["left"] == LAPTOP["left"] + MARGIN


# ---------- Which pins the home view counts as shown ----------
# Owner, 3 Nov 2026 (PR #91): the home view keeps an item whose number the edge nudge makes
# visible. Before, it asked for 18 px (half a number) between a pin and the chart's edge, so on
# a phone it dropped 5 East Anchorage (12 px below the top edge) from 10 pairs that fit on screen.

def shown(point, chart=PHONE):
    return js(f"P.onChart({json.dumps(point)}, {json.dumps(chart)})")


def test_a_pin_near_the_edge_that_the_nudge_makes_whole_counts_as_shown():
    assert shown({"x": 200, "y": 12}) is True  # 5 East Anchorage on a phone
    assert shown({"x": 3, "y": 300}) is True
    assert shown({"x": 200, "y": 523}) is True  # on the bottom edge itself
    assert shown({"x": 420, "y": 400}, chart=LAPTOP) is True  # just right of the panel


def test_a_place_off_the_chart_or_under_the_panel_does_not_count_as_shown():
    assert shown({"x": 200, "y": -1}) is False
    assert shown({"x": 391, "y": 300}) is False
    assert shown({"x": 415, "y": 400}, chart=LAPTOP) is False


def test_the_home_view_counts_as_shown_exactly_the_pins_the_nudge_makes_whole():
    # Across both charts, edges included: a point that counts as shown gets its whole marker
    # inside the chart after the nudge; any other point is not moved (and so stays off the chart).
    mismatches = js(
        "(() => { const out = [];"
        f" for (const chart of [{json.dumps(PHONE)}, {json.dumps(LAPTOP)}]) {{"
        "  for (let x = chart.left - 30; x <= chart.right + 30; x += 7) {"
        "   for (let y = chart.top - 30; y <= chart.bottom + 30; y += 7) {"
        "    const point = {x: x, y: y};"
        f"    const box = P.boxAt(point, {json.dumps(ONE_ITEM)}, x > chart.right - 200 ? 'left' : 'right', false);"
        f"    const n = P.nudgeInside(box, point, chart, {MARGIN});"
        "    const whole = box.left + n.x >= chart.left && box.right + n.x <= chart.right"
        "      && box.top + n.y >= chart.top && box.bottom + n.y <= chart.bottom;"
        "    const moved = n.x !== 0 || n.y !== 0;"
        "    if (P.onChart(point, chart) ? !whole : moved) out.push([chart.right, x, y]);"
        "   } } }"
        " return out; })()"
    )
    assert mismatches == []


def test_map_js_home_view_uses_the_shared_rule():
    # map.js can't run in Node (Leaflet, the page); this ties its home view to the tested rule.
    source = (ROOT / "static" / "map.js").read_text(encoding="utf-8")
    shows_pins = source[source.index("function showsPins"):source.index("function goHome")]
    assert "pinGeometry.onChart(" in shows_pins
    assert "NUM_HALF" not in shows_pins


# ---------- The marker box and overlaps (as map.js uses them) ----------

def test_box_one_line_right_and_shared_line_left():
    assert js("P.boxAt({x: 100, y: 100}, {w: 150, h: 36, half: 18, lead: 36}, 'right', false)") == {
        "left": 82, "right": 232, "top": 82, "bottom": 118}
    # Labels on the left of "3 4": the first number (lead = both numbers, 76 px) stays on the place.
    assert js("P.boxAt({x: 300, y: 100}, {w: 300, h: 36, half: 18, lead: 76}, 'left', false)") == {
        "left": 58, "right": 358, "top": 82, "bottom": 118}


def test_rows_run_down_from_the_first_number():
    assert js("P.boxAt({x: 100, y: 100}, {w: 200, h: 112, half: 18, lead: 36}, 'right', true)")["top"] == 82


def test_overlap_keeps_a_gap_between_markers():
    a = {"left": 0, "right": 100, "top": 0, "bottom": 36}
    touching = {"left": 102, "right": 200, "top": 0, "bottom": 36}
    apart = {"left": 105, "right": 200, "top": 0, "bottom": 36}
    assert js(f"P.overlaps({json.dumps(a)}, {json.dumps(touching)}, 4)") is True
    assert js(f"P.overlaps({json.dumps(a)}, {json.dumps(apart)}, 4)") is False


def test_the_day_page_loads_pins_js_before_map_js():
    template = (ROOT / "templates" / "day.html").read_text(encoding="utf-8")
    assert template.index("static/pins.js") < template.index("static/map.js")
