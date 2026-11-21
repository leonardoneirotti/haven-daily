"""Site speed, part 2 (issue #104; docs/site-speed.md): a lighter basemap and cheaper water lines.

static/basemap.js is the biggest file of the site. It now holds simpler shapes in a compact
text form (tools/build_basemap.py): 88 KB as sent instead of 238 KB. The 41 places
must stay where they were on the chart: on land or on water as before, and as far from the
shore as before, give or take the simplification (side-by-side pictures in the PR).

The lines in the water come from a distance map worked out once per zoom level (map.js),
instead of wide strokes of the whole coastline on every move. map.js can't run here; its
parts are checked by reading it, and tools/measure_speed.mjs measures it in a browser.
"""

import gzip
import json
import math
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BASEMAP_JS = (ROOT / "static" / "basemap.js").read_text(encoding="utf-8")
MAP_JS = (ROOT / "static" / "map.js").read_text(encoding="utf-8")
WATER_JS = (ROOT / "static" / "water.js").read_text(encoding="utf-8") if (ROOT / "static" / "water.js").exists() else ""
PLACES = tomllib.loads((ROOT / "config" / "places.toml").read_text(encoding="utf-8"))["place"]
# The finer land, kept by tools/build_basemap.py as the reference (not sent to browsers).
REFERENCE_LAND = json.loads((ROOT / "data" / "basemap" / "land.geojson").read_text(encoding="utf-8"))

SIZE_TARGET_KB = 90  # as sent (gzip, as GitHub Pages does); was 238 KB. Owner's target: about 80.
# How far the chart's shore may move from the finer outline near a place: the simplification
# tolerance (0.0004 degrees, at most ~45 m) plus the grid (~10 m); measured: 29 m at most.
SHORE_SLACK_M = 60


@pytest.fixture(scope="module")
def basemap():
    return json.loads(BASEMAP_JS[BASEMAP_JS.index("{"):BASEMAP_JS.rindex("}") + 1])


# ---------- The same decoding as map.js, written out again ----------

def numbers(text):
    out, value, shift = [], 0, 0
    for letter in text:
        c = ord(letter) - 63
        value |= (c & 0x1F) << shift
        if c & 0x20:
            shift += 5
            continue
        out.append(~(value >> 1) if value & 1 else value >> 1)
        value, shift = 0, 0
    return out


def shapes(texts):
    result, start = [], (0, 0)
    for text in texts:
        steps = numbers(text)
        x, y = start
        points = []
        for i in range(0, len(steps), 2):
            x, y = x + steps[i], y + steps[i + 1]
            points.append((x, y))
        result.append(points)
        start = points[0]
    return result


def to_lon_lat(basemap, point):
    south, west = basemap["bbox"][0], basemap["bbox"][1]
    return west + point[0] / basemap["grid"], south + point[1] / basemap["grid"]


# ---------- Geometry, small and slow but enough for 41 points ----------

def inside(rings, lon, lat):
    """Even-odd rule, as the chart fills the land."""
    crossings = 0
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                crossings += 1
    return crossings % 2 == 1


def shore_distance_m(rings, lon, lat):
    kx, ky = 111_320 * math.cos(math.radians(lat)), 110_540
    best = math.inf
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            ax, ay, bx, by = (x1 - lon) * kx, (y1 - lat) * ky, (x2 - lon) * kx, (y2 - lat) * ky
            dx, dy = bx - ax, by - ay
            t = 0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


@pytest.fixture(scope="module")
def chart_rings(basemap):
    return [[to_lon_lat(basemap, p) for p in ring] for ring in shapes(basemap["land"])]


@pytest.fixture(scope="module")
def reference_rings():
    return [[tuple(p) for p in ring] for polygon in REFERENCE_LAND["coordinates"] for ring in polygon]


# ---------- The file ----------

def test_the_basemap_is_much_smaller():
    sent = len(gzip.compress(BASEMAP_JS.encode("utf-8"), 6)) / 1024
    assert sent <= SIZE_TARGET_KB, f"basemap.js sends {sent:.0f} KB, target {SIZE_TARGET_KB} KB"


def test_the_basemap_keeps_its_credit_and_its_parts(basemap):
    assert "OpenStreetMap contributors, ODbL" in BASEMAP_JS
    assert basemap["grid"] == 10_000
    assert basemap["bbox"] == [51.74, 3.4, 52.16, 4.62]
    assert all(isinstance(text, str) for text in basemap["land"])
    for kind in ("major", "minor", "rail", "jetty"):
        assert basemap["detail"][kind] and all(isinstance(text, str) for text in basemap["detail"][kind])
    assert isinstance(basemap["detail"]["tanks"], str)
    assert len(basemap["labels"]) == 13


def test_every_point_lies_on_the_sheet(basemap):
    south, west, north, east = basemap["bbox"]
    columns, rows = round((east - west) * basemap["grid"]), round((north - south) * basemap["grid"])
    every = shapes(basemap["land"]) + [s for kind in ("major", "minor", "rail", "jetty") for s in shapes(basemap["detail"][kind])]
    for shape in every:
        assert len(shape) >= 2
        for x, y in shape:
            assert 0 <= x <= columns and 0 <= y <= rows, (x, y)


def test_land_rings_are_closed(basemap):
    for ring in shapes(basemap["land"]):
        assert len(ring) >= 4 and ring[0] == ring[-1]


def test_tanks_decode_to_points_on_the_sheet_with_a_radius(basemap):
    values = numbers(basemap["detail"]["tanks"])
    assert len(values) % 3 == 0 and len(values) // 3 > 4000
    x = y = 0
    for i in range(0, len(values), 3):
        x, y = x + values[i], y + values[i + 1]
        assert 0 <= x <= 12_200 and 0 <= y <= 4_200 and 4 <= values[i + 2] < 200


# ---------- The 41 places ----------

def test_there_are_41_places():
    assert len(PLACES) == 41


@pytest.mark.parametrize("place", PLACES, ids=[p["id"] for p in PLACES])
def test_each_place_stays_on_land_or_water_as_before(place, chart_rings, reference_rings):
    was = inside(reference_rings, place["lon"], place["lat"])
    now = inside(chart_rings, place["lon"], place["lat"])
    if was != now:  # allowed only right at the shore, within the simplification
        assert shore_distance_m(reference_rings, place["lon"], place["lat"]) <= SHORE_SLACK_M, place["id"]


@pytest.mark.parametrize("place", PLACES, ids=[p["id"] for p in PLACES])
def test_the_shore_near_each_place_moves_little(place, chart_rings, reference_rings):
    was = shore_distance_m(reference_rings, place["lon"], place["lat"])
    now = shore_distance_m(chart_rings, place["lon"], place["lat"])
    assert abs(now - was) <= SHORE_SLACK_M, f"{place['id']}: shore {was:.0f} m away before, {now:.0f} m now"


# ---------- map.js ----------

def test_map_js_reads_the_compact_form():
    assert "function numbers(text)" in MAP_JS
    assert "basemap.land.coordinates" not in MAP_JS


def test_water_lines_come_from_a_distance_map_not_wide_strokes():
    # Since #111 the distance map is worked out in a background worker (static/water.js,
    # tests/test_water.py).
    assert "function distanceMap(" in WATER_JS
    # No more strokes as wide as twice the distance from the shore.
    assert not re.search(r"lineWidth\s*=\s*2\s*\*\s*distance", MAP_JS)


def test_the_water_is_worked_out_once_per_zoom_and_reused_while_moving():
    # Since #111 every repaint checks the water picture (checkWater), which asks the worker
    # for a new one only for a new zoom or when the view has left it.
    paint = MAP_JS[MAP_JS.index("function paint(ctx)"):]
    paint = paint[:paint.index("\n  }\n")]
    assert "checkWater();" in paint
    check = MAP_JS[MAP_JS.index("function checkWater()"):]
    check = check[:check.index("\n  }\n")]
    assert re.search(r"water\.zoom === zoom", check)
    assert "wantWater(" in check and "if (!inside)" in check


def test_canvas_paths_use_small_numbers():
    # The canvas keeps about seven digits; world pixels reach millions at the closest zoom,
    # so every path is drawn shifted to the screen's own coordinates.
    assert "ctx.translate(-origin.x" not in MAP_JS
    # (The land mask for the water lines is made in the worker since #111, without a canvas.)
    assert MAP_JS.count("outline(") >= 3 and "shift.x" in MAP_JS
