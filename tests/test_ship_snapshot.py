"""Ships on the map, part 1 (issue #156, owner's plan of 26 Nov 2026): the shared morning ship snapshot,
the `ships` switch, and count badges plus single ships on the chart.

- **One snapshot format for any source** (`haven/ships.py`): the Port of Rotterdam and aisstream.io
  adapters (built once they give permission) both return it. Every ship has a `place` (a place id
  from config/places.toml, or null), so "ships at the terminal in the news" is a lookup.
- **The switch** `ships` in config/site.toml: off on the live site; on is refused without a recorded
  written permission. Off: both sites (real and /sample/) render exactly as before, and a real
  brief's ships are ignored.
- **The chart** (switch on, or a local preview of the sample site): at the opening view one count
  badge per place, at the centre of its ships; single ships from zoom 12 or for a selected item.
  Ships and badges have their own pane under the news numbers, which never move for them; a badge
  that would cover a number hides.

All ships here are invented.
"""

import json
import re
from pathlib import Path

import pytest

from haven import render, ships
from haven.config import ConfigError, load_places, load_site
from test_pins_geometry import NODE, js
from test_render_real import make_brief, render_days

ROOT = Path(__file__).resolve().parent.parent
MAP_JS = (ROOT / "static" / "map.js").read_text(encoding="utf-8")
PLACE_IDS = {p.id for p in load_places()}


def vessel(**fields):
    base = {"name": "Invented Star", "type": "container", "status": "moored", "place": "ect-delta",
            "lat": 51.96, "lon": 4.03, "heading": 90, "speed_kn": 0.0, "length_m": 300, "flag": "NL",
            "area": "Maasvlakte", "destination_raw": "", "destination": None}
    base.update(fields)
    return base


def snapshot(*vessels, **fields):
    base = {"source_id": "sample", "source_name": "Sample AIS data", "kind": "positions",
            "snapshot_start": "2026-11-27T06:28:00+01:00", "snapshot_end": "2026-11-27T06:38:00+01:00",
            "vessels": list(vessels) or [vessel()], "expected": None}
    base.update(fields)
    return base


# --- the shared format -------------------------------------------------------------------------


def test_a_good_snapshot_has_no_problems():
    assert ships.check_snapshot(snapshot(), PLACE_IDS) == []


def test_it_works_for_both_kinds_of_source():
    assert ships.KINDS == ("berths", "positions")
    berths = snapshot(vessel(heading=None, speed_kn=None), kind="berths", source_id="port-arrivals",
                      expected=[{"name": "Invented Arrival", "type": "tanker", "eta": "2026-11-27T14:00:00+01:00",
                                 "place": "botlek", "length_m": None}])
    assert ships.check_snapshot(berths, PLACE_IDS) == []


@pytest.mark.parametrize("change, problem", [
    ({"kind": "live"}, "kind"),
    ({"source_id": ""}, "source_id"),
    ({"vessels": "many"}, "vessels"),
    ({"expected": [{"name": "X", "type": "tanker", "place": None}]}, "eta"),
])
def test_a_bad_snapshot_is_named(change, problem):
    assert any(problem in p for p in ships.check_snapshot(snapshot(**change), PLACE_IDS))


@pytest.mark.parametrize("change, problem", [
    ({"type": "yacht"}, "type"),
    ({"status": "expected"}, "status"),
    ({"place": "nowhere"}, "place"),
    ({"lat": None}, "lat"),
    ({"name": ""}, "name"),
])
def test_a_bad_vessel_is_named(change, problem):
    assert any(problem in p for p in ships.check_snapshot(snapshot(vessel(**change)), PLACE_IDS))


def test_ais_cargo_is_a_type_of_its_own():
    # AIS can't tell container from bulk (owner's choice: Cargo / Tanker for AIS, #156).
    assert "cargo" in ships.TYPES and ships.check_snapshot(snapshot(vessel(type="cargo")), PLACE_IDS) == []
    assert "cargo" in render.SHIP_TYPES and "cargo" in render.SHIP_DECKS


def test_a_ship_without_a_place_is_fine():
    assert ships.check_snapshot(snapshot(vessel(place=None, status="underway")), PLACE_IDS) == []


def test_badges_count_the_ships_per_place_at_the_centre_of_its_ships():
    group = ships.by_place([vessel(lat=51.96, lon=4.02), vessel(lat=51.98, lon=4.04, type="tanker"),
                            vessel(place="botlek", lat=51.88, lon=4.26), vessel(place=None, status="underway")],
                           load_places())
    assert [(b["place"], b["count"]) for b in group] == [("ect-delta", 2), ("botlek", 1)]  # most ships first
    ect = group[0]
    assert (ect["lat"], ect["lon"]) == (pytest.approx(51.97), pytest.approx(4.03))
    assert ect["label"] == next(p.label for p in load_places() if p.id == "ect-delta")
    assert ect["by_type"] == {"container": 1, "tanker": 1}


def test_a_badge_takes_the_most_severe_linked_item():
    group = ships.by_place([vessel(news_item=3), vessel(news_item=1)], load_places())
    assert group[0]["news_item"] == 1


@pytest.mark.parametrize("day", ["2026-10-28", "2026-10-29"])
def test_the_sample_snapshots_follow_the_format(day):
    brief = json.loads((ROOT / "data" / "sample" / "briefs" / f"{day}.json").read_text(encoding="utf-8"))
    assert ships.check_snapshot(brief["ships"], PLACE_IDS) == []
    moored = [v for v in brief["ships"]["vessels"] if v["status"] != "underway"]
    assert moored and all(v["place"] for v in moored)   # every ship at a berth or anchor has its place


# --- the switch ------------------------------------------------------------------------------------


def test_the_switch_is_off_on_the_live_site():
    site = load_site()
    assert site.ships is False and site.ships_permission is None
    assert re.search(r"^ships = false$", (ROOT / "config" / "site.toml").read_text(encoding="utf-8"), re.M)


SITE = (ROOT / "config" / "site.toml").read_text(encoding="utf-8")


def site_with(tmp_path, lines):
    path = tmp_path / "site.toml"
    path.write_text(re.sub(r"^ships = false$", lines, SITE, flags=re.M), encoding="utf-8")
    return path


def test_on_is_refused_without_a_recorded_written_permission(tmp_path):
    with pytest.raises(ConfigError, match="permission"):
        load_site(site_with(tmp_path, "ships = true"))
    with pytest.raises(ConfigError, match="permission"):
        load_site(site_with(tmp_path, 'ships = true\nships_permission = "docs/permissions/2099-01-01-nobody.md"'))
    with pytest.raises(ConfigError, match="ships_permission"):
        load_site(site_with(tmp_path, 'ships = true\nships_permission = "notes.txt"'))


def test_on_with_a_permission_file_loads(tmp_path):
    existing = sorted((ROOT / "docs" / "permissions").glob("*.md"))[0].relative_to(ROOT).as_posix()
    site = load_site(site_with(tmp_path, f'ships = true\nships_permission = "{existing}"'))
    assert site.ships is True and site.ships_permission == existing


def test_the_switch_must_be_true_or_false(tmp_path):
    with pytest.raises(ConfigError, match="ships"):
        load_site(site_with(tmp_path, 'ships = "no"'))


def test_the_old_code_constant_is_gone():
    assert not hasattr(render, "AIS_SNAPSHOT_BUILT")


# --- the page with the switch off: exactly as before ---------------------------------------------


def day_html(tmp_path, brief):
    return render_days(tmp_path, brief)[brief["date"]]


def map_data(html):
    return json.loads(re.search(r'<script type="application/json" id="map-data">(.*?)</script>', html, re.S).group(1))


def test_off_a_real_briefs_ships_are_ignored(tmp_path):
    html = day_html(tmp_path, make_brief(ships=snapshot(vessel(name="Invented Real Ship"))))
    assert "Invented Real Ship" not in html
    assert map_data(html)["ships"] is None
    assert "Ships in the port area" not in html


def test_off_the_map_data_has_nothing_new(tmp_path):
    html = day_html(tmp_path, make_brief(sample=True, ships=snapshot()))
    data = map_data(html)
    assert "ship_view" not in data and "ship_places" not in data
    assert all("place" not in s for s in data["ships"])     # the ship list as before


# --- the preview (and later the switch on): badges and single ships ----------------------------------


def preview_html(tmp_path, brief):
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / f"{brief['date']}.json").write_text(json.dumps(brief), encoding="utf-8")
    render.render_site(briefs, tmp_path / "site", preview_ships=True)
    return (tmp_path / "site" / "days" / f"{brief['date']}.html").read_text(encoding="utf-8")


def test_the_preview_adds_the_badges_and_each_ships_place(tmp_path):
    data = map_data(preview_html(tmp_path, make_brief(sample=True, ships=snapshot(vessel(), vessel(name="B")))))
    assert data["ship_view"] == "badges"
    assert data["ship_zoom"] == 12
    [badge] = data["ship_places"]
    assert (badge["place"], badge["count"]) == ("ect-delta", 2)
    assert all(s["place"] == "ect-delta" for s in data["ships"])


def test_the_preview_is_only_for_the_sample_site(tmp_path):
    with pytest.raises(ValueError, match="sample"):
        preview_html(tmp_path, make_brief(ships=snapshot()))


def test_the_preview_can_be_asked_for_from_the_command_line():
    source = Path(render.__file__).read_text(encoding="utf-8")
    assert '"--preview-ships"' in source


def test_a_snapshot_that_breaks_the_format_shows_as_failed_not_half_drawn(tmp_path):
    html = preview_html(tmp_path, make_brief(sample=True, ships=snapshot(vessel(type="yacht"))))
    assert map_data(html)["ships"] is None


# --- the chart (static/map.js, static/pins.js) -------------------------------------------------------


def test_ships_have_their_own_pane_under_the_news_numbers():
    pane = re.search(r'createPane\("ships"\)\.style\.zIndex = (\d+)', MAP_JS)
    assert pane and int(pane.group(1)) < 600                 # Leaflet's marker pane (the numbers) is 600
    assert 'pane: "ships"' in MAP_JS


def test_the_badge_view_only_runs_when_the_data_asks_for_it():
    assert 'data.ship_view === "badges"' in MAP_JS          # otherwise the ships are drawn as before


def test_single_ships_from_zoom_12_or_for_a_selected_item():
    assert "data.ship_zoom" in MAP_JS
    assert re.search(r"function showShipView\(", MAP_JS)


def test_the_number_layout_never_looks_at_ships():
    plan = MAP_JS[MAP_JS.index("function planMarkers("):]
    plan = plan[: plan.index("\n  }\n")]
    assert "ship" not in plan.lower()


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_a_badge_that_would_cover_a_number_hides():
    numbers = [{"left": 100, "top": 100, "right": 124, "bottom": 124}]
    badges = [{"left": 110, "top": 110, "right": 170, "bottom": 130},   # covers the number
              {"left": 300, "top": 300, "right": 360, "bottom": 320},   # clear
              {"left": 126, "top": 100, "right": 180, "bottom": 120}]   # 2 px gap: too close
    assert js(f"P.coveredBadges({json.dumps(badges)}, {json.dumps(numbers)}, 4)") == [0, 2]


# --- the checks in Actions -----------------------------------------------------------------------------

PIN_CHECK = (ROOT / "tools" / "check_map_pins.py").read_text(encoding="utf-8")
SPEED_YML = (ROOT / ".github" / "workflows" / "speed.yml").read_text(encoding="utf-8")


def test_the_pin_check_has_a_ships_on_run():
    assert '"--ships"' in PIN_CHECK
    assert "badge-over-number" in PIN_CHECK
    assert "check_map_pins.py --ships" in SPEED_YML


def test_the_speed_run_measures_the_badge_view_and_a_busy_day():
    assert "--preview-ships" in SPEED_YML
    assert "make_busy_ships.py" in SPEED_YML
    busy = (ROOT / "tools" / "make_busy_ships.py").read_text(encoding="utf-8")
    assert "250" in busy and "data/sample" not in busy.replace("data/sample/briefs\" (read only)", "")
