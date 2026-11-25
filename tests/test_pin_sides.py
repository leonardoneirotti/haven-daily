"""Close pins stay apart, and each number keeps its side (issue #148).

On the 25 Nov 2026 page, items 4 (Botlekbrug) and 5 (A15, ~4 km west, ~70 px at the opening view)
would overlap, so map.js merged them into one marker on 4's place ("4 5 Botlekbrug · A15"): 5's
number sat east of 4 although its place is west of it, and jumped left when zooming in split them.

Now, before merging two overlapping markers, map.js asks `HavenPins.separateSides` for sides that
keep them apart (the western label to the left, the eastern to the right, first), with a clear
gap and inside the chart; it merges only when none works. And every number keeps the side it had
when the chart re-plans (zoom, fly), unless that would overlap or run off the chart.
"""

import json
import re

from test_pins_geometry import LAPTOP, NODE, ROOT, js  # noqa: F401  (NODE: the skip rule)
from test_pins_geometry import pytestmark  # noqa: F401  skipped without Node, as the geometry tests

MAP_JS = (ROOT / "static" / "map.js").read_text(encoding="utf-8")
ITEM_4 = {"w": 138, "h": 36, "half": 18, "lead": 36}  # "4 Botlekbrug"
ITEM_5 = {"w": 70, "h": 36, "half": 18, "lead": 36}   # "5 A15"
CLEAR = 12  # the gap two separated markers keep (CLEAR_GAP in map.js)
MARGIN = 4


def separate(a, b, size_a=ITEM_5, size_b=ITEM_4, preferred=("right", "right"), chart=LAPTOP, others=()):
    return js(
        f"P.separateSides({json.dumps(a)}, {json.dumps(b)}, {json.dumps(size_a)}, {json.dumps(size_b)},"
        f" {json.dumps(list(preferred))}, {json.dumps(chart)}, {CLEAR}, {MARGIN}, {json.dumps(list(others))})"
    )


def box(point, size, side):
    return js(f"P.boxAt({json.dumps(point)}, {json.dumps(size)}, {json.dumps(side)}, false)")


# 25 Nov 2026, 1440 x 900: 4 Botlekbrug at x 1099, 5 A15 ~70 px west of it (measured in headless Edge).
FIVE, FOUR = {"x": 1029, "y": 600}, {"x": 1099, "y": 596}


def test_the_25_nov_pins_get_their_labels_on_the_outer_sides():
    assert separate(FIVE, FOUR) == ["left", "right"]


def test_their_numbers_then_keep_a_clear_gap():
    a, b = box(FIVE, ITEM_5, "left"), box(FOUR, ITEM_4, "right")
    assert b["left"] - a["right"] >= CLEAR  # 70 px apart, two half numbers of 18 px: 34 px of gap


def test_the_order_of_the_two_points_does_not_matter():
    assert separate(FOUR, FIVE, ITEM_4, ITEM_5) == ["right", "left"]


def test_preferred_sides_that_already_fit_are_kept():
    far_apart = {"x": 700, "y": 300}, {"x": 1000, "y": 600}
    assert separate(*far_apart, preferred=("left", "right")) == ["left", "right"]
    assert separate(*far_apart, preferred=("right", "left")) == ["right", "left"]


def test_a_label_that_would_go_under_the_panel_is_not_chosen():
    # The western pin just right of the panel (416 px): its label can't go left.
    west, east = {"x": 440, "y": 400}, {"x": 520, "y": 400}
    sides = separate(west, east)
    assert sides is None or sides[0] == "right"


def test_pins_too_close_to_separate_give_none_so_they_merge():
    assert separate({"x": 1000, "y": 500}, {"x": 1012, "y": 503}) is None


def test_a_third_marker_in_the_way_is_respected():
    blocker = box({"x": 960, "y": 600}, ITEM_4, "right")  # sits where 5's left label would go
    sides = separate(FIVE, FOUR, others=[blocker])
    assert sides != ["left", "right"]


# --- map.js uses it, and keeps sides between plans -------------------------------------------------


def plan_markers():
    start = MAP_JS.index("function planMarkers()")
    return MAP_JS[start: MAP_JS.index("\n  }\n", start)]


def test_map_js_tries_to_separate_before_merging():
    plan = plan_markers()
    assert "HavenPins.separateSides(" in plan or "pinGeometry.separateSides(" in plan
    assert plan.index("separateSides(") < plan.index("inPlaceOrder(")


def test_map_js_keeps_a_clear_gap_between_separated_markers():
    assert re.search(r"var CLEAR_GAP = 12;", MAP_JS)


def test_map_js_remembers_each_numbers_side_between_plans():
    assert "lastSide" in MAP_JS
    place = MAP_JS[MAP_JS.index("function placeMarker("): MAP_JS.index("function planMarkers()")]
    assert "lastSide[" in place  # the side it had is the one it prefers now
    show = MAP_JS[MAP_JS.index("function showCallouts("):]
    assert re.search(r"lastSide\[[^\]]+\]\s*=", show)  # the shown plan is remembered
