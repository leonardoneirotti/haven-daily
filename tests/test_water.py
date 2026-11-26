"""The lines in the water, worked out in a background worker (issue #111, PR 1).

Since #106 every new zoom level worked out the lines in the water again on the page's own
thread, from a distance map: 1.3-1.8 s with the page frozen after every zoom step on a laptop
(diagnosis in #111). Now static/water.js does that work in a background worker, and map.js
shows the previous picture, scaled, until the new one arrives. The page's own thread only
draws pictures.

water.js is pure JavaScript (no page, no canvas, no Leaflet), so its parts run here in Node.
The rest is checked by reading map.js; tools/measure_speed.mjs measures the result in a real
browser (speed.yml, laptop and phone). Skipped where Node isn't installed (GitHub's runners have it).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
WATER_JS_PATH = STATIC / "water.js"
WATER_JS = WATER_JS_PATH.read_text(encoding="utf-8") if WATER_JS_PATH.exists() else ""
MAP_JS = (STATIC / "map.js").read_text(encoding="utf-8")
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def js(body: str):
    """Run `body` (a function body that returns a value) with W = the HavenWater functions."""
    script = (
        "const fs = require('fs'), vm = require('vm'); const ctx = {};"
        f"vm.runInNewContext(fs.readFileSync({json.dumps(str(WATER_JS_PATH))}, 'utf8'), ctx);"
        f"const W = ctx.HavenWater; console.log(JSON.stringify((() => {{ {body} }})()));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# A ring as map.js makes them: world pixels at zoom 0 and the box around them.
RING = """function ring(points) {
  const pts = new Float64Array(points.flat());
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  return { pts, minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) };
}
function count(mask) { let n = 0; for (const v of mask) n += v; return n; }
"""


# ---------- The land mask ----------

@needs_node
def test_a_square_of_land_fills_the_pixels_whose_centres_lie_inside():
    result = js(RING + """
      const mask = W.landMask([ring([[2, 2], [6, 2], [6, 6], [2, 6]])], 1, { minX: 0, minY: 0, maxX: 10, maxY: 10 }, 0);
      const on = []; for (let i = 0; i < mask.length; i++) if (mask[i]) on.push([i % 10, Math.floor(i / 10)]);
      return { size: mask.length, on };
    """)
    assert result["size"] == 100
    assert sorted(result["on"]) == [[x, y] for x in range(2, 6) for y in range(2, 6)]


@needs_node
def test_a_hole_in_the_land_stays_water():
    # Outer edges and holes alike are filled "evenodd", as on the canvas.
    result = js(RING + """
      const rings = [ring([[0, 0], [10, 0], [10, 10], [0, 10]]), ring([[3, 3], [7, 3], [7, 7], [3, 7]])];
      const mask = W.landMask(rings, 1, { minX: 0, minY: 0, maxX: 10, maxY: 10 }, 0);
      return { land: count(mask), hole: mask[5 * 10 + 5], edge: mask[0] };
    """)
    assert result == {"land": 100 - 16, "hole": 0, "edge": 1}


@needs_node
def test_the_mask_is_scaled_and_shifted_to_the_box():
    # At scale 4 the square 2..6 covers world pixels 8..24; the box starts at (8, 8).
    result = js(RING + """
      const mask = W.landMask([ring([[2, 2], [6, 2], [6, 6], [2, 6]])], 4, { minX: 8, minY: 8, maxX: 24, maxY: 24 }, 0);
      return { land: count(mask), size: mask.length };
    """)
    assert result == {"land": 256, "size": 256}


@needs_node
def test_land_outside_the_box_is_left_out():
    result = js(RING + """
      const mask = W.landMask([ring([[50, 50], [60, 50], [60, 60], [50, 60]])], 1, { minX: 0, minY: 0, maxX: 10, maxY: 10 }, 0);
      return count(mask);
    """)
    assert result == 0


# ---------- The distance map ----------

@needs_node
def test_every_water_pixel_gets_its_squared_distance_to_the_nearest_land_pixel():
    result = js("""
      const w = 7, h = 5, cells = new Float32Array(w * h).fill(1e20);
      cells[2 * w + 3] = 0;
      W.distanceMap(cells, w, h);
      return Array.from(cells);
    """)
    expected = [(x - 3) ** 2 + (y - 2) ** 2 for y in range(5) for x in range(7)]
    assert result == expected


# ---------- The picture ----------

# A straight coast: land everywhere left of world pixel x = 50. One metre = 6/25 px, so the
# closest lines (every 25 m) are 6 px apart; 120 px of reach = 20 lines.
PICTURE = RING + """
  const land = [ring([[-1000, -1000], [50, -1000], [50, 1000], [-1000, 1000]])];
  const job = { id: 7, zoom: 12.5, s: 1, x: 0, y: 0, w: 200, h: 4, worldPerMetre: 6 / 25,
                sea: [219, 231, 237], line: [111, 151, 173] };
  const out = W.waterPicture(job, land);
  const px = (x) => Array.from(out.pixels.slice(4 * x, 4 * x + 4));
"""


@needs_node
def test_the_picture_has_the_requested_size_and_place():
    result = js(PICTURE + "return { id: out.id, zoom: out.zoom, x: out.x, y: out.y, w: out.w, h: out.h, length: out.pixels.length };")
    assert result == {"id": 7, "zoom": 12.5, "x": 0, "y": 0, "w": 200, "h": 4, "length": 200 * 4 * 4}


@needs_node
def test_lines_follow_the_shore_at_fixed_distances_and_fade_out_far_from_it():
    result = js(PICTURE + "return { near: px(52), line: px(55), far: px(190), alpha: px(120)[3] };")
    sea = [219, 231, 237, 255]
    assert result["near"] == sea  # 2.5 px from the shore: between the shore and the first line
    assert result["line"] != sea  # about 6 px out: on the first line
    assert result["far"] == sea  # past the last line (120 px)
    assert result["alpha"] == 255


@needs_node
def test_closer_zoom_spaces_the_lines_by_doubling_the_metres():
    # At 6/50 px per metre, 25 m is only 3 px: the closest spacing still 6 px apart is 50 m.
    result = js("""
      return W.lineSpacing(6 / 50);
    """)
    assert result["metres"] == 50 and result["count"] == 20
    assert result["gap"] == pytest.approx(6)


# ---------- The worker ----------

@needs_node
def test_as_a_worker_it_takes_the_land_once_then_answers_each_request_with_a_picture():
    script = (
        "const fs = require('fs'), vm = require('vm');"
        "const sent = [];"
        "class WorkerGlobalScope {}"
        "const self = Object.create(WorkerGlobalScope.prototype);"
        "self.postMessage = (data, transfer) => sent.push({ data, transfer });"
        "const ctx = vm.createContext({ self, WorkerGlobalScope });"
        f"vm.runInContext(fs.readFileSync({json.dumps(str(WATER_JS_PATH))}, 'utf8'), ctx);"
        "const ring = { pts: new Float64Array([-1000, -1000, 50, -1000, 50, 1000, -1000, 1000]), minX: -1000, minY: -1000, maxX: 50, maxY: 1000 };"
        "self.onmessage({ data: { land: [ring] } });"
        "const quiet = sent.length;"
        "self.onmessage({ data: { id: 3, zoom: 11, s: 1, x: 0, y: 0, w: 100, h: 2, worldPerMetre: 6 / 25, sea: [1, 2, 3], line: [9, 9, 9] } });"
        "const m = sent[0];"
        "console.log(JSON.stringify({ quiet, replies: sent.length, id: m.data.id, zoom: m.data.zoom, w: m.data.w, h: m.data.h,"
        " length: m.data.pixels.length, transferred: m.transfer.length === 1 && m.transfer[0] === m.data.pixels.buffer }));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {"quiet": 0, "replies": 1, "id": 3, "zoom": 11, "w": 100, "h": 2,
                                       "length": 100 * 2 * 4, "transferred": True}


def test_water_js_is_plain_javascript_that_loads_nothing():
    # One self-contained file: no imports (the privacy check forbids loading scripts, #14).
    assert WATER_JS, "static/water.js is missing"
    assert "HavenWater" in WATER_JS
    assert not re.search(r"\b(import|require)\s*\(|\bimport\s+[\w{*]", WATER_JS)


# ---------- map.js: the page's own thread only draws pictures ----------

def test_map_js_starts_the_worker_from_water_js_next_to_it():
    assert re.search(r"new Worker\(\s*folder\s*\+\s*\"water\.js\"\s*\)", MAP_JS)
    assert re.search(r"var folder = .*document\.currentScript", MAP_JS)


def test_no_water_work_is_left_on_the_pages_own_thread():
    for name in ("distanceMap", "distances1d", "getImageData", "landMask", "paintWater("):
        assert name not in MAP_JS, name


def test_the_land_goes_to_the_worker_once():
    assert len(re.findall(r"\.postMessage\(\{\s*land:", MAP_JS)) == 1


def function(name: str) -> str:
    body = MAP_JS[MAP_JS.index(f"function {name}("):]
    return body[:body.index("\n  }\n")]


def test_the_water_is_a_layer_of_its_own_under_the_basemap():
    # Measured in the first speed run of this PR (#111): repainting the whole basemap canvas when
    # a new picture arrived was itself a long task without a graphics chip. So the land canvas
    # draws no water, and the picture is a <canvas> of its own in a pane just under it.
    assert re.search(r'map\.createPane\("water"\)\.style\.zIndex = 240;', MAP_JS)
    assert re.search(r'map\.createPane\("basemap"\)\.style\.zIndex = 250;', MAP_JS)
    assert "drawImage(water" not in function("paint")


def test_a_new_picture_is_handed_over_and_repaints_nothing_else():
    take = function("takeWater")
    assert "transferFromImageBitmap(picture)" in take
    assert 'getContext("bitmaprenderer")' in take
    assert "redraw" not in take


def test_until_the_new_picture_arrives_the_previous_one_is_shown_scaled():
    place = function("placeWater")
    assert re.search(r"var k = map\.getZoomScale\(zoom, water\.zoom\);", place)
    assert re.search(r"L\.DomUtil\.setTransform\(waterEl, L\.point\(water\.x \* k - origin\.x, water\.y \* k - origin\.y\), k\)", place)


def test_the_picture_moves_with_every_kind_of_zoom_using_leaflets_public_parts():
    assert re.search(r'map\.on\("zoomanim", function \(event\) \{', MAP_JS)
    assert re.search(r'L\.DomUtil\.getPosition\(map\.getPane\("mapPane"\)\)', MAP_JS)
    assert re.search(r'map\.on\("zoom viewreset zoomend", function \(\) \{ placeWater\(map\.getZoom\(\), map\.getPixelOrigin\(\)\); \}\);', MAP_JS)
    assert "_getNewPixelOrigin" not in MAP_JS and "_getMapPanePos" not in MAP_JS


def test_one_picture_is_worked_out_at_a_time():
    want = MAP_JS[MAP_JS.index("function wantWater("):]
    want = want[:want.index("\n  }\n")]
    assert re.search(r"if \(!waterWorker \|\| waterJob\) return;", want)


def test_if_the_worker_cannot_start_or_fails_the_chart_shows_plain_water():
    assert re.search(r"try \{\s*waterWorker = new Worker", MAP_JS)
    assert re.search(r"waterWorker\.onerror = function", MAP_JS)


# ---------- The speed run measures the laptop too ----------

SPEED_YML = (ROOT / ".github" / "workflows" / "speed.yml").read_text(encoding="utf-8")
COMPARE = (ROOT / "tools" / "speed_compare.mjs").read_text(encoding="utf-8")
MEASURE = (ROOT / "tools" / "measure_speed.mjs").read_text(encoding="utf-8")


def test_the_speed_run_measures_the_phone_and_the_laptop():
    assert SPEED_YML.count("--profiles phone,laptop") == 2
    assert "--profile phone" in SPEED_YML and "--profile laptop" in SPEED_YML
    assert '"issue-111-*"' in SPEED_YML


def test_every_zoom_step_is_measured_and_the_laptop_target_is_100_ms():
    for step in ("zoom in (button)", "zoom in again (button)", "zoom out (button)"):
        assert f'phase("{step}"' in MEASURE
    assert re.search(r'profile === "laptop" \? \{ zoom: 100\b', COMPARE)  # #150 added flyFrame: 50
    assert '"Zoom step: longest task"' in COMPARE
