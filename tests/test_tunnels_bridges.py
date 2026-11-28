"""The main road tunnels and bridges around the port on the place list (issue #170, owner 28 Nov 2026).

Found in the dry run of 28 Nov (run 46147095911): item 2, "Noordtunnel, Van Brienenoordbrug main
carriageway and A59 closed for maintenance this weekend" (Medium), had no number on the map: none of
the three was on the list. The owner asked for Noordtunnel, Van Brienenoordbrug, Beneluxtunnel,
Botlektunnel, Maastunnel, Heinenoordtunnel, Drechttunnel, Thomassentunnel, Ketheltunnel, Kethelplein
and Calandbrug (skipping any already listed), positions from OpenStreetMap, more specific than the
A15/A20 road fallback (#138).

- Calandbrug was already on the list.
- Noordtunnel (4.653° E) and Drechttunnel (4.648° E) lie east of the chart sheet (to 4.62° E,
  spec §8.1), so they can't be pinned. Item 2 still gets a number: the next place it names, the Van
  Brienenoordbrug.
- Tunnels get the kind "tunnel", Kethelplein (a motorway junction) "junction": neither is a road.

Positions: OpenStreetMap through Overpass, 28 Nov 2026, the centre of the element in `osm`.
"""

import json
from pathlib import Path

import pytest

from haven.config import PLACE_KINDS, SHEET_BBOX, load_places
from haven.places import named_first, prefer_specific
from test_summarise import answer, item, run

ROOT = Path(__file__).resolve().parent.parent
SPEC = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")
PLACES = {p.id: p for p in load_places()}

NEW = {  # id: (label, kind, osm, lat, lon)
    "beneluxtunnel": ("Beneluxtunnel", "tunnel", "relation/18813183", 51.8993, 4.3736),
    "botlektunnel": ("Botlektunnel", "tunnel", "relation/19147166", 51.8730, 4.3328),
    "heinenoordtunnel": ("Heinenoordtunnel", "tunnel", "relation/19147158", 51.8324, 4.5127),
    "kethelplein": ("Kethelplein", "junction", "way/939303640", 51.9257, 4.3655),
    "ketheltunnel": ("Ketheltunnel", "tunnel", "relation/19142968", 51.9364, 4.3610),
    "maastunnel": ("Maastunnel", "tunnel", "relation/11840239", 51.8999, 4.4686),
    "thomassentunnel": ("Thomassentunnel", "tunnel", "relation/19142970", 51.9003, 4.2272),
    "van-brienenoordbrug": ("Van Brienenoordbrug", "bridge", "relation/18645127", 51.9039, 4.5434),
}


@pytest.mark.parametrize("place_id", sorted(NEW))
def test_each_new_place_is_listed_with_its_openstreetmap_position(place_id):
    label, kind, osm, lat, lon = NEW[place_id]
    place = PLACES[place_id]
    assert (place.label, place.kind, place.osm, place.lat, place.lon) == (label, kind, osm, lat, lon)


@pytest.mark.parametrize("place_id", sorted(NEW))
def test_each_new_place_is_on_the_chart_sheet_and_not_a_road(place_id):
    place = PLACES[place_id]
    south, west, north, east = SHEET_BBOX
    assert south <= place.lat <= north and west <= place.lon <= east
    assert place.kind != "road"  # more specific than the A15/A20 fallback (#138)


def test_tunnel_and_junction_are_place_kinds():
    assert "tunnel" in PLACE_KINDS and "junction" in PLACE_KINDS


def test_calandbrug_is_listed_once_and_the_two_tunnels_off_the_sheet_are_not():
    assert [p.id for p in PLACES.values() if p.label == "Calandbrug"] == ["calandbrug"]
    labels = {p.label for p in PLACES.values()}
    assert "Noordtunnel" not in labels and "Drechttunnel" not in labels


# The dry run's item 2, as stored in its brief: the headline and Haven Daily's own summary.
ITEM_2_HEADLINE = "Let op! Deze wegen en tunnel zijn dit weekend dicht door werkzaamheden"
ITEM_2_SUMMARY = ("Road maintenance this weekend closes the Noordtunnel, the main carriageway of the Van "
                  "Brienenoordbrug and the A59 in Brabant. Drivers should mainly expect disruption on Friday "
                  "evening and Saturday.")
ITEM_2_IMPACT = ("Trucks around Rotterdam could face detours or delays on Friday evening and Saturday, especially "
                 "where the Van Brienenoordbrug or Noordtunnel are used.")


def item_2_answer(place):
    return answer(json.dumps({"summary": ITEM_2_SUMMARY, "impact": ITEM_2_IMPACT, "severity": "medium",
                              "place": place, "tags": ["Truck pickups", "Hinterland"], "strike": None}))


def test_the_dry_runs_item_2_gets_a_number():
    result, _ = run([item(headline=ITEM_2_HEADLINE, text="Invented lead about weekend road works.")],
                    item_2_answer("none"))
    ai = result.items[0].ai
    assert ai["map"]["label"] == "Van Brienenoordbrug"  # the Noordtunnel is off the sheet
    assert ai["place_named"] == "Van Brienenoordbrug"


@pytest.mark.parametrize("road", ["a15", "a20"])
def test_a_named_tunnel_or_bridge_beats_the_road_the_ai_picked(road):
    assert prefer_specific(road, ITEM_2_SUMMARY) == "van-brienenoordbrug"
    assert prefer_specific(road, "Invented: the A20 is closed at the Kethelplein tonight.") == "kethelplein"
    assert prefer_specific(road, "Invented: the A15 Botlektunnel is closed tonight.") == "botlektunnel"


def test_the_first_tunnel_named_wins():
    assert named_first("Invented: the Maastunnel and the Beneluxtunnel are busy.") == "maastunnel"


def test_the_spec_lists_the_new_places():
    assert "*(#170" in SPEC and "Van Brienenoordbrug" in SPEC and "Noordtunnel" in SPEC
