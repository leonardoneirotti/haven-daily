"""A smooth fly-to (issue #150).

Part 1, measuring (in Actions, tools/measure_speed.mjs): during a fly-to the speed run records, frame by
frame, the frame times and long tasks, the zoom path (read from the scale Leaflet gives the basemap
canvas while it moves), the marker rebuilds, when the pin card opens, and any page or panel
scrolling at the same time. tools/speed_compare.mjs shows them, with the owner's target: no frame
longer than 50 ms during a fly-to on the laptop profile.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEASURE = (ROOT / "tools" / "measure_speed.mjs").read_text(encoding="utf-8")
COMPARE = (ROOT / "tools" / "speed_compare.mjs").read_text(encoding="utf-8")


# --- part 1: what the speed run records during a fly-to -------------------------------------------


def test_the_speed_run_has_a_flight_probe():
    assert "FLIGHT_PROBE" in MEASURE
    probe = MEASURE[MEASURE.index("const FLIGHT_PROBE"):]
    probe = probe[: probe.index("`;") + 2]
    for watched in (".leaflet-basemap-pane canvas",   # the zoom path, from the canvas's scale
                    ".leaflet-marker-pane",            # marker rebuilds
                    ".leaflet-popup-pane",             # when the pin card opens
                    "scrollY", ".panel-items",         # page and panel scrolling
                    "requestAnimationFrame"):          # one sample per frame
        assert watched in probe, watched


def test_both_ways_of_starting_a_flight_are_measured():
    assert 'flight("select an item (chart flies)"' in MEASURE         # a number on the chart
    assert 'flight("select an item in the panel (chart flies)"' in MEASURE  # an entry in the panel


def test_the_flight_summary_names_what_can_make_it_feel_glitchy():
    summary = MEASURE[MEASURE.index("function flightSummary"):]
    summary = summary[: summary.index("\n}\n")]
    for key in ("longestFrame", "framesOver25", "framesOver50", "longTasks", "zoomsOutFirst", "overshoot",
                "markerRebuildsDuring", "markerRebuildsAfter", "cardAfterFlightMs", "pageScrollPx", "panelScrollPx",
                "flightMs"):
        assert key in summary, key


def test_the_comparison_shows_the_flight_with_the_laptop_target():
    assert re.search(r'TARGETS = profile === "laptop" \? \{[^}]*flyFrame: 50', COMPARE)
    for row in ("Fly-to: longest frame", "Fly-to: frames > 50 ms", "Fly-to: zooms out first",
                "Fly-to: markers rebuilt during the flight", "Fly-to: card opens after the flight"):
        assert row in COMPARE, row


# --- measuring right: no extra work from the probe, real clicks, named timings ----------------------

MAP_JS = (ROOT / "static" / "map.js").read_text(encoding="utf-8")


def test_the_probe_reads_leaflets_inline_transform_not_the_computed_style():
    probe = MEASURE[MEASURE.index("const FLIGHT_PROBE"):]
    probe = probe[: probe.index("`;") + 2]
    assert "getComputedStyle" not in probe  # it made the browser recalculate styles on every frame
    assert ".style.transform" in probe


def test_a_number_on_the_chart_is_clicked_with_real_mouse_events():
    # map.js tells a click from a drag by the mouse presses, so element.click() starts no flight.
    block = MEASURE[MEASURE.index('await flight("select an item (chart flies)"'):]
    block = block[: block.index("await flight(", 10)]
    assert "mousePressed" in block and "mouseReleased" in block


def test_map_js_names_the_work_done_when_a_flight_lands():
    for name in ("paint", "markers", "water", "card"):
        assert f'timing("{name}"' in MAP_JS, name
    assert "performance.measure(" in MAP_JS


def test_the_flight_summary_attributes_the_landing_work():
    summary = MEASURE[MEASURE.index("function flightSummary"):]
    summary = summary[: summary.index("\n}\n")]
    assert "timings" in summary


# --- part 2: the fixes ---------------------------------------------------------------------------------

import json  # noqa: E402

from test_pins_geometry import NODE, js  # noqa: E402,F401  (skipped without Node, as the geometry tests)


def map_function(name):
    start = MAP_JS.index(f"function {name}(")
    return MAP_JS[start: MAP_JS.index("\n  }\n", start)]


def test_the_easing_is_one_smooth_in_out_curve():
    values = js("[0, 0.1, 0.25, 0.5, 0.75, 0.9, 1].map(P.glideEase)")
    assert values[0] == 0 and values[-1] == 1 and abs(values[3] - 0.5) < 1e-9
    assert values == sorted(values)                       # never goes back
    assert values[1] < 0.1 and values[5] > 0.9             # starts and ends gently
    assert abs(values[2] + values[4] - 1) < 1e-9           # the same in as out


def test_the_duration_grows_with_the_distance_within_sensible_limits():
    short, long, far = js("[P.glideDuration(40, 0), P.glideDuration(400, 1), P.glideDuration(5000, 6)]")
    assert 450 <= short < long <= far <= 900


def test_a_selection_glides_straight_without_leafets_fly_arc():
    fly = map_function("flyTo")
    assert "flyToBounds" not in fly and "map.flyTo(" not in fly
    assert "glideTo(" in fly
    assert "flyToBounds" not in MAP_JS and "map.flyTo(" not in MAP_JS


def test_the_glide_uses_leaflets_own_move_steps_and_can_be_stopped():
    glide = map_function("glideTo")
    for step in ("map._moveStart(", "map._move(", "._moveEnd(", "map._flyToFrame =", "pinGeometry.glideEase(",
                 "pinGeometry.glideDuration("):
        assert step in glide, step


def test_reduced_motion_jumps_without_moving():
    fly = map_function("flyTo")
    assert re.search(r"if \(reduceMotion\)[^\n]*(fitBounds|setView)[^\n]*", fly)


def test_the_card_opens_after_the_landing_without_moving_the_chart_again():
    select = map_function("selectItem")
    assert "cardPadding(" in select                      # room for the card is part of the flight's target
    still = map_function("whenStill")
    assert "requestAnimationFrame" in still              # after the frames that land the chart


def test_the_markers_are_placed_in_the_frame_after_the_basemap():
    assert re.search(r'map\.on\("moveend", function \(\) \{[^}]*requestAnimationFrame', MAP_JS)


def test_the_free_chart_is_measured_once_per_plan():
    plan = map_function("planMarkers")
    assert "planChart = " in plan
    assert "planChart ||" in map_function("freeChart")
