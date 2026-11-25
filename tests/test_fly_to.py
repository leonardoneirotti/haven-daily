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
