"""How the chart takes the mouse, touchpad, keyboard and touch (issue #111, PR 2).

The owner's decisions (21 Nov 2026, #111): option A, P1 and points 2 to 6, plus the phone fix.

- A plain wheel or two-finger touchpad scroll over the chart scrolls the page and shows a short
  hint; Ctrl + wheel and a touchpad pinch (which the browser sends as Ctrl + wheel) zoom the
  chart, and no longer zoom the whole page.
- Phones keep one-finger drag (P1). A mostly vertical swipe on the chart scrolls the page
  whenever the chart can't move that way, so the page never gets stuck on the chart.
- Edges that give (2), zoom steps of 1 (3), drags that start on a marker move the chart (4),
  the header doesn't come back while the cursor is over the chart (5), one line in the legend (6).

map.js needs Leaflet and a browser, so it is checked here by reading it; the pure part (who takes
a swipe) runs in Node. tools/check_map_input.mjs sends real input in headless Chrome, before and
after, in the speed run (speed.yml).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from haven import render

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
MAP_JS = (STATIC / "map.js").read_text(encoding="utf-8")
SITE_JS = (STATIC / "site.js").read_text(encoding="utf-8")
PINS_JS = STATIC / "pins.js"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
SPEC = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")
SPEED_YML = (ROOT / ".github" / "workflows" / "speed.yml").read_text(encoding="utf-8")
CHECK_TOOL = ROOT / "tools" / "check_map_input.mjs"
NODE = shutil.which("node")
SAMPLE_BRIEFS = ROOT / "data" / "sample" / "briefs"


@pytest.fixture(scope="module")
def today():
    out = Path(__import__("tempfile").mkdtemp())
    render.render_site(SAMPLE_BRIEFS, out)
    return BeautifulSoup((out / "index.html").read_text(encoding="utf-8"), "html.parser")


def map_options():
    start = MAP_JS.index("var map = L.map(el, {")
    return MAP_JS[start:MAP_JS.index("});", start)]


def block(name: str) -> str:
    """A section of map.js from its "// ---------- name" heading to the next heading."""
    start = MAP_JS.index(f"// ---------- {name}")
    end = MAP_JS.find("// ----------", start + 10)
    return MAP_JS[start:end if end > 0 else None]


# ---------- A: the wheel and the touchpad ----------

def test_leaflets_wheel_zoom_is_on_and_only_ctrl_wheel_reaches_it():
    assert re.search(r"scrollWheelZoom: true", map_options())
    wheel = block("Wheel and touchpad")
    # The gate runs before Leaflet's handler (capture, on the chart's frame) and never cancels:
    # a plain wheel scrolls the page as anywhere else.
    assert re.search(r'el\.parentNode\.addEventListener\("wheel", function \(event\) \{', wheel)
    assert re.search(r"\{ capture: true, passive: true \}", wheel)
    assert re.search(r"if \(event\.ctrlKey \|\| event\.metaKey\) return;", wheel)
    assert "event.stopPropagation();" in wheel
    assert "preventDefault" not in wheel


def test_a_plain_wheel_over_the_chart_shows_the_hint_for_a_moment():
    wheel = block("Wheel and touchpad")
    assert re.search(r"showHint\(\)", wheel)
    assert re.search(r"setTimeout\(function \(\) \{ hint\.classList\.remove\(\"is-shown\"\); \}, 1500\)", wheel)


def test_the_hint_is_on_the_chart_and_names_the_key(today):
    hint = today.find(id="chart-hint")
    assert hint is not None and hint.find_parent(class_="chart-frame") is not None
    assert hint.get("aria-hidden") == "true"  # for the mouse; the keyboard has + and -
    assert "needs-map" in hint["class"]
    assert " ".join(hint.get_text().split()) == "Use Ctrl + scroll to zoom the chart"
    assert hint.find(attrs={"data-zoom-key": True}) is not None


def test_on_a_mac_the_key_is_named_command():
    assert re.search(r'var zoomKey = /Mac\|iPhone\|iPad/\.test\(navigator\.platform \|\| ""\) \? "⌘" : "Ctrl";', MAP_JS)
    assert re.search(r"\[data-zoom-key\]", MAP_JS)


def test_the_hint_fades_without_motion_when_motion_is_reduced():
    assert re.search(r"\.chart-hint \{[^}]*opacity: 0;[^}]*pointer-events: none;", CSS, re.S)
    assert re.search(r"\.chart-hint\.is-shown \{[^}]*opacity: 1;", CSS, re.S)
    # The site-wide rule for reduced motion turns every transition off, the hint's included.
    reduced = CSS[CSS.index("@media (prefers-reduced-motion: reduce)"):]
    assert re.search(r"\*::after \{\s*animation: none !important;\s*transition: none !important;", reduced)
    assert re.search(r"\.chart-hint \{[^}]*transition: opacity", CSS, re.S)


# ---------- P1 and the phone fix: one finger ----------

def swipe(dx, dy, north, south):
    script = (
        "const fs = require('fs'), vm = require('vm'); const ctx = {};"
        f"vm.runInNewContext(fs.readFileSync({json.dumps(str(PINS_JS))}, 'utf8'), ctx);"
        f"console.log(JSON.stringify(ctx.HavenPins.swipeTaker({dx}, {dy}, {{ north: {north}, south: {south} }}, 8)));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
@pytest.mark.parametrize("dx, dy, north, south, taker", [
    (2, -5, 0, 0, None),  # too short to tell: the chart waits
    (0, -40, 0, 0, "page"),  # up, and the chart can't move south: the page scrolls
    (0, 40, 0, 0, "page"),  # down, and the chart can't move north
    (0, -40, 0, 300, "map"),  # up, and the chart can move south: the chart moves (P1)
    (0, 40, 300, 0, "map"),  # down, room to the north
    (0, 40, 0, 300, "page"),  # down, room only to the south
    (60, 20, 0, 0, "map"),  # mostly sideways: the chart (it gives at its edges)
    (5, 9, 0, 0, "page"),  # a short, mostly vertical swipe past the threshold
])
def test_a_vertical_swipe_goes_to_the_page_whenever_the_chart_cant_move_that_way(dx, dy, north, south, taker):
    assert swipe(dx, dy, north, south) == taker


def test_one_finger_on_the_chart_is_routed_by_that_rule():
    touch = block("One finger")
    assert re.search(r'el\.addEventListener\("touchstart", function \(event\) \{', touch)
    assert "pinGeometry.swipeTaker(" in touch
    assert re.search(r"window\.scrollBy\(0, -", touch)
    # A second finger leaves it to Leaflet's pinch; the page's swipes never reach Leaflet.
    assert re.search(r"event\.touches\.length !== 1", touch)
    assert "event.stopPropagation();" in touch
    # The glide after a flick is left out with reduced motion.
    assert "reduceMotion" in touch


def test_one_finger_drag_still_moves_the_chart():
    # P1: Leaflet's own dragging stays on, for mouse and touch alike.
    assert "dragging: false" not in map_options()
    assert "touchZoom: false" not in map_options()


# ---------- 2, 3, 4: edges, steps, markers ----------

def test_the_edges_give_a_little_and_spring_back():
    assert re.search(r"maxBoundsViscosity: 0\.8,", map_options())


def test_buttons_double_click_and_keys_zoom_one_level():
    assert re.search(r"zoomDelta: 1,", map_options())
    assert re.search(r"zoomSnap: 0,", map_options())  # flying to an item still lands exactly


def test_a_drag_that_starts_on_a_marker_moves_the_chart():
    assert "disableClickPropagation(marker.getElement())" not in MAP_JS
    # Only a double-click on a number is kept from zooming the chart.
    assert re.search(r'L\.DomEvent\.on\(marker\.getElement\(\), "dblclick", L\.DomEvent\.stopPropagation\)', MAP_JS)


def test_releasing_a_drag_on_a_number_does_not_pick_the_item():
    wiring = block("Wiring")
    assert re.search(r'event\.target\.closest\("\.leaflet-marker-pane"\) && map\.dragging\.moved\(\)', wiring)


# ---------- 5: the header ----------

def test_the_header_does_not_come_back_while_the_cursor_is_over_the_chart():
    move = SITE_JS[SITE_JS.index('addEventListener("mousemove"'):]
    move = move[:move.index("});")]
    assert re.search(r'event\.target\.closest\("\.chart"\)', move)
    assert "NEAR_TOP" in move


def test_the_change_to_the_header_decision_is_recorded_in_the_spec():
    assert re.search(r"\(owner, 21 Nov 2026, #111\)[^\n]*over the chart", SPEC)


# ---------- 6: the legend ----------

def test_the_legend_says_how_to_move_and_zoom(today):
    how = today.select_one(".chart-legend .legend-how")
    assert how is not None and "needs-map" in how["class"]
    fine, touch = how.select_one(".how-fine"), how.select_one(".how-touch")
    assert " ".join(fine.get_text().split()) == "Drag to move · Ctrl + scroll or pinch to zoom"
    assert " ".join(touch.get_text().split()) == "Drag to move · pinch to zoom"
    assert re.search(r"@media \(pointer: coarse\) \{\s*\.how-fine \{\s*display: none;", CSS)


# ---------- The spec and the check in the speed run ----------

def test_the_spec_describes_the_new_input():
    assert "Scroll-wheel zoom off" not in SPEC
    assert re.search(r"Ctrl \+ wheel[^\n]*pinch", SPEC)
    assert re.search(r"`zoomDelta: 1`", SPEC)
    assert re.search(r"`maxBoundsViscosity: 0\.8`", SPEC)
    assert re.search(r"vertical swipe[^\n]*scrolls the page", SPEC)


def test_the_speed_run_checks_the_map_input_before_and_after():
    assert CHECK_TOOL.exists()
    assert re.search(r'node tools/check_map_input\.mjs "\$RUNNER_TEMP/before" "\$RUNNER_TEMP/after"', SPEED_YML)
    assert "tools/check_map_input.mjs" in SPEED_YML.split("paths:")[1].split("permissions")[0]
