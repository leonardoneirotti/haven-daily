"""Safeguard for decision 6 of PR #91 (spec §8.5): the home view uses two of Leaflet's internal
map methods, `_getBoundsCenterZoom` and `_limitCenter`, to work out a view without moving the
chart. They are not public API, so they are only trusted in the bundled Leaflet 1.9.4.
Confirmed by the owner, 3 Nov 2026 (PR #91). Since #150 the glide to a selected item also uses
the steps of Leaflet's own flyTo: `_moveStart`, `_move`, `_moveEnd`, `_stop`, and the
`_flyToFrame` property that `_stop` cancels.

Leaflet needs a browser, so the bundled (minified) file is read as text.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAFLET_JS = ROOT / "static" / "vendor" / "leaflet" / "leaflet.js"
MAP_JS = ROOT / "static" / "map.js"

VERSION = "1.9.4"
INTERNALS = {"_getBoundsCenterZoom", "_limitCenter", "_moveStart", "_move", "_moveEnd", "_stop"}
# Set by the glide, cancelled by _stop (#150); the ship layer's canvas hull overrides _updatePath and
# reads the canvas renderer's _drawing and _ctx (#156).
PROPERTIES = {"_flyToFrame", "_updatePath", "_drawing", "_ctx"}
RECHECK = ("Recheck decision 6 (spec §8.5, PR #91, #150, #156) before updating Leaflet: static/map.js uses "
           "Leaflet's internal map methods " + ", ".join(sorted(INTERNALS)) + " and " + ", ".join(sorted(PROPERTIES)) + ".")


def leaflet_problems(source: str) -> list[str]:
    """What is wrong with a Leaflet build for the home view: its version, and missing internals."""
    problems = []
    versions = re.findall(r'\.version\s*=\s*"([^"]+)"', source)
    if versions != [VERSION]:
        problems.append(f"bundled Leaflet is {versions or 'of unknown version'}, expected {VERSION}")
    for name in sorted(INTERNALS):
        if not re.search(rf"\b{name}\s*:\s*function\s*\(", source):
            problems.append(f"Leaflet's map method {name} is missing")
    for name in sorted(PROPERTIES):
        if name not in source:
            problems.append(f"Leaflet's map property {name} is missing")
    return problems


def test_the_bundled_leaflet_is_1_9_4_with_the_internals_the_home_view_uses():
    problems = leaflet_problems(LEAFLET_JS.read_text(encoding="utf-8"))
    assert not problems, "; ".join(problems) + ". " + RECHECK


def test_map_js_uses_no_other_leaflet_internals():
    # A new internal call would not be covered by this safeguard: add it to INTERNALS and to
    # decision 6 in the spec first.
    # Any `._name(` call, chained ones included (`map._move(...)._moveEnd(...)`, #150).
    used = set(re.findall(r"\.(_[A-Za-z]\w*)\s*\(", MAP_JS.read_text(encoding="utf-8")))
    assert used == INTERNALS, f"map.js calls Leaflet internals {sorted(used)}. " + RECHECK


# ---------- The safeguard itself fails when it should ----------

GOOD = ('t.version="1.9.4",x={_getBoundsCenterZoom:function(t,e){},_limitCenter:function(t,e,i){},'
        '_moveStart:function(t,e){},_move:function(t,e,i){},_moveEnd:function(t){},'
        '_stop:function(){cancelAnimFrame(this._flyToFrame)}},'
        'y={_updatePath:function(){this._renderer._updateCircle(this)}},z={_updateCircle:function(t){if(!this._drawing)'
        'return;var e=this._ctx}}')


def test_a_build_like_the_bundled_one_passes():
    assert leaflet_problems(GOOD) == []


def test_another_leaflet_version_fails():
    assert leaflet_problems(GOOD.replace("1.9.4", "2.0.0")) == ["bundled Leaflet is ['2.0.0'], expected 1.9.4"]
    assert leaflet_problems(GOOD.replace('t.version="1.9.4",', "")) == [
        "bundled Leaflet is of unknown version, expected 1.9.4"]


def test_a_missing_internal_fails():
    assert leaflet_problems(GOOD.replace("_limitCenter:function", "_clampCenter:function")) == [
        "Leaflet's map method _limitCenter is missing"]
    assert leaflet_problems(GOOD.replace("_getBoundsCenterZoom", "_fitCenterZoom")) == [
        "Leaflet's map method _getBoundsCenterZoom is missing"]
