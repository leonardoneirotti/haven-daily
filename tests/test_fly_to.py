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


def test_the_cards_room_below_matches_what_its_auto_pan_asks_for():
    # The phone measurement (after the first fix): 64 px below the number was less than the card's
    # auto-pan wants (attribution + number + gaps), so it still moved the chart after opening.
    padding = map_function("cardPadding")
    assert "room.bottom" in padding
    assert "var bottom = 64" not in padding


# --- part 3: a glide between two items at the same zoom (#161) -------------------------------------
# Owner, 27 Nov 2026: in full screen (and the phone's expanded chart), with one item's card open, a
# click on another number flew to a wrong-looking place and the number sat in the wrong spot for a
# moment. Found in a headless browser: the two items share the zoom (11.8, or 13.6 with ships; on a
# phone the card's room keeps the zoom where it is), and Leaflet's `_move` fires "zoom" only when the
# zoom changes. The numbers (Leaflet markers), the ship layer and the water follow the chart on that
# event, so for the whole glide they stood still while the chart's centre moved, then jumped.

LEAFLET_JS = (ROOT / "static" / "vendor" / "leaflet" / "leaflet.js").read_text(encoding="utf-8")
PINS_JS = ROOT / "static" / "pins.js"
MAP_JS_PATH = ROOT / "static" / "map.js"


def test_leaflets_move_step_fires_zoom_only_when_the_zoom_changes():
    # The cause, in the bundled 1.9.4: `o` is "the zoom changed"; "move" alone moves no marker.
    move = LEAFLET_JS[LEAFLET_JS.index("_move:function(t,e,i,n){"):]
    move = move[: move.index("},_moveEnd")]
    assert "var o=this._zoom!==e" in move
    assert '(o||i&&i.pinch)&&this.fire("zoom",i)' in move


def glide(z0, z1, dx):
    """Run map.js's glideTo in Node against a map that does what Leaflet 1.9.4's steps do (above),
    from zoom z0 to z1 and dx pixels east. Returns the events in order, with the centre at each."""
    script = """
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(%(map)s, 'utf8').replace(/\\r\\n/g, '\\n');
const start = src.indexOf('function glideTo(');
const glideSrc = src.slice(start, src.indexOf('\\n  }\\n', start) + 4);
const pins = {}; vm.runInNewContext(fs.readFileSync(%(pins)s, 'utf8'), pins);
class P { constructor(x, y) { this.x = x; this.y = y; }
  add(o) { return new P(this.x + o.x, this.y + o.y); } subtract(o) { return new P(this.x - o.x, this.y - o.y); }
  multiplyBy(k) { return new P(this.x * k, this.y * k); } distanceTo(o) { return Math.hypot(this.x - o.x, this.y - o.y); } }
const events = [];
const map = { _zoom: %(z0)s, _lastCenter: { lat: 0, lng: 0 },
  getZoom() { return this._zoom; }, getCenter() { return this._lastCenter; },
  project(c, z) { const s = Math.pow(2, z); return new P(c.lng * s, -c.lat * s); },
  unproject(p, z) { const s = Math.pow(2, z); return { lat: -p.y / s, lng: p.x / s }; },
  fire(name) { events.push([name, +this._lastCenter.lng.toFixed(9)]); return this; },
  _stop() {},
  _moveStart(t, e) { if (t) this.fire('zoomstart'); if (!e) this.fire('movestart'); return this; },
  _move(t, e, i, n) { if (e === undefined) e = this._zoom; const o = this._zoom !== e;
    this._zoom = e; this._lastCenter = t;
    if (n) { if (i && i.pinch) this.fire('zoom', i); } else { if (o || (i && i.pinch)) this.fire('zoom', i); this.fire('move', i); }
    return this; },
  _moveEnd(t) { if (t) this.fire('zoomend'); return this.fire('moveend'); } };
let now = 0; const frames = [];
const ctx = { map, pinGeometry: pins.HavenPins, performance: { now: () => now },
  showCallouts() { events.push(['plan for the landing', 0]); },  // part 4: planned before the chart moves
  L:{ Util: { requestAnimFrame(f) { frames.push(f); return frames.length; } } } };
vm.runInNewContext(glideSrc + '; glideTo({ lat: 0, lng: %(dx)s / Math.pow(2, %(z0)s) }, %(z1)s);', ctx);
for (let i = 0; frames.length && i < 500; i++) { now += 16; frames.shift()(); }
console.log(JSON.stringify(events));
""" % {"map": json.dumps(str(MAP_JS_PATH)), "pins": json.dumps(str(PINS_JS)), "z0": z0, "z1": z1, "dx": dx}
    done = __import__("subprocess").run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def numbers_follow_every_step(events):
    """Every "move" to a new centre comes with a "zoom" at that centre: the markers were placed for it.
    (The first frame, at t = 0, moves nowhere.)"""
    moves = [i for i, e in enumerate(events) if e[0] == "move"]
    assert len(moves) > 10  # a real glide, many frames
    placed = 0  # where the markers were placed: the start
    for i in moves:
        if events[i - 1] == ["zoom", events[i][1]]:
            placed = events[i][1]
        elif events[i][1] != placed:
            return False
    return True


def test_a_glide_at_the_same_zoom_moves_the_numbers_every_frame():
    # Item A's card open at 11.8, item B's number clicked: B lands at 11.8 too.
    events = glide(11.8, 11.8, 300)
    assert numbers_follow_every_step(events), events[:6]


def test_a_glide_that_zooms_still_moves_them_every_frame():
    events = glide(10.7, 11.8, 300)
    assert numbers_follow_every_step(events), events[:6]


def test_a_glide_at_the_same_zoom_ends_as_leaflets_flyto_does():
    # zoomstart before and zoomend after, as Leaflet's own flyTo always sends them: the water, the
    # scale bar and the ships' sizes settle on zoomend.
    events = [e[0] for e in glide(11.8, 11.8, 300)]
    # The markers are planned for the landing before anything moves (part 4).
    assert events[:3] == ["plan for the landing", "zoomstart", "movestart"]
    assert events.count("plan for the landing") == 1
    assert events[-2:] == ["zoomend", "moveend"]


def test_the_browser_check_clicks_a_second_number_with_a_card_open():
    check = (ROOT / "tools" / "check_map_input.mjs").read_text(encoding="utf-8")
    for row in ("Laptop, full screen: item 2's card open, then item 3's number",
                "Laptop, expanded chart: item 2's card open, then item 3's number",
                "Phone, expanded chart: tap item 1's number"):
        assert row in check, row
    # What it reports: how far the number is from its place on the chart while it moves, and after.
    assert "off its place" in check


def test_the_spec_records_the_fix():
    spec = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")
    assert re.search(r"#161[^\n]*same zoom", spec)


# --- part 4: the landing side is chosen before the glide (#161, owner, 27 Nov 2026) -----------------
# On a phone (25 Nov, item 4's card open, then 5) number 5's label switched from right to left at
# landing, because 4 is next to it there (#148), moving the number 48 px as the chart stopped. The
# owner: choose the landing side before the glide, so any shift happens at the start, not at the end.


def test_the_glide_shows_the_markers_planned_for_where_it_lands_before_it_moves():
    glide_src = map_function("glideTo")
    plan = glide_src.index("showCallouts(false, { center: center, zoom: zoom })")
    assert plan < glide_src.index("map._moveStart(")


def test_planning_reads_every_place_through_one_point_function():
    # pointOf: where a place is on the chart now, or once the chart stands at the planned view.
    for name in ("placeMarker", "planMarkers"):
        body = map_function(name)
        assert "map.latLngToContainerPoint(" not in body, name
        assert "pointOf(" in body, name
    point = map_function("pointOf")
    assert "planView" in point and "map.latLngToContainerPoint(" in point
    # Leaflet's own sums after a move: the projected place rounded, less the rounded pixel origin.
    assert "getPosition(map.getPane(\"mapPane\"))" in point and ".round()" in point


def test_placing_the_markers_can_plan_for_another_view_and_then_forgets_it():
    place = map_function("placeCallouts")
    assert "planView = view" in place
    assert "planView = null" in place


def test_the_browser_check_tells_a_shift_at_the_start_from_a_jump_at_the_end():
    check = (ROOT / "tools" / "check_map_input.mjs").read_text(encoding="utf-8")
    assert "at the start" in check
    assert "changes side at landing" in check and "keeps its side at landing" in check
