"""Ships on the map, part 2 (issue #156, owner's plan of 26 Nov 2026): the Ships dial, with counts per
terminal, and the ship filter, on the shared morning snapshot.

Only in the ship layer (the `ships` switch on, or `--preview-ships` on the sample site). With the
switch off, both sites render exactly as before (the dial, filter and list of the sample site today).

- **The dial:** the number of ships, then "N at a berth · N at anchor · N under way" (each shows those
  ships on the chart), "N expected in the next 24 h" when the source gives arrivals (berth data
  only), the **counts per place**, grouped as terminals, anchorages and other areas (each flies to its
  ships; a place with a ship linked to a news item links that item), then the snapshot time and source.
- **The filter:** All, then every type present: container, tanker, bulk, cargo. A morning of AIS data
  therefore shows All / Cargo / Tanker (owner's choice, #156).
- **The ship list:** each ship's place, and the expected arrivals.

All ships here are invented.
"""

import json
import re
from pathlib import Path

from haven import render, ships
from haven.config import load_places
from test_render_real import make_brief, news, render_days, text_of
from test_ship_snapshot import PLACE_IDS, preview_html, snapshot, vessel

ROOT = Path(__file__).resolve().parent.parent
MAP_JS = (ROOT / "static" / "map.js").read_text(encoding="utf-8")
LABELS = {p.id: p.label for p in load_places()}


def fleet():
    return snapshot(
        vessel(name="A1", place="ect-delta"), vessel(name="A2", place="ect-delta", type="tanker"),
        vessel(name="A3", place="euromax"),
        vessel(name="B1", place="anchorage-4-east", status="anchored"),
        vessel(name="C1", place="botlek", type="bulk"),
        vessel(name="U1", place=None, status="underway", speed_kn=12.0),
    )


def dial(html):
    start = html.index('data-key="ships"')
    return html[start: html.index("</li>", html.index('class="dial-meta"', start))]


def chart_filter(html):
    start = html.index('class="chart-filter')
    return html[start: html.index("</div>", start)]


# --- the dial ---------------------------------------------------------------------------------------


def test_the_dial_counts_ships_at_a_berth_at_anchor_and_under_way(tmp_path):
    part = dial(preview_html(tmp_path, make_brief(sample=True, ships=fleet())))
    assert '<p class="dial-value">6</p>' in part
    for status, words in (("moored", "4 at a berth"), ("anchored", "1 at anchor"), ("underway", "1 under way")):
        assert f'data-action="show-ships" data-status="{status}"' in part
        assert words in text_of(part)


def test_the_dial_lists_the_ships_per_place_grouped_by_kind(tmp_path):
    part = dial(preview_html(tmp_path, make_brief(sample=True, ships=fleet())))
    text = text_of(part)
    terminals = text.index("At terminals")
    anchorages = text.index("At anchorages")
    elsewhere = text.index("Elsewhere in the port")
    assert terminals < anchorages < elsewhere
    assert text.index(f"{LABELS['ect-delta']} 2") < text.index(f"{LABELS['euromax']} 1") < anchorages  # most first
    assert f"{LABELS['anchorage-4-east']} 1" in text[anchorages:elsewhere]
    assert f"{LABELS['botlek']} 1" in text[elsewhere:]
    for place in ("ect-delta", "euromax", "anchorage-4-east", "botlek"):
        assert f'data-action="show-place" data-place="{place}"' in part


def test_a_place_with_a_ship_in_the_news_links_the_item(tmp_path):
    brief = make_brief(sample=True, items=[news("high", "Invented terminal strike")],
                       ships=snapshot(vessel(name="A1", place="ect-delta", news_item=1)))
    part = dial(preview_html(tmp_path, brief))
    assert 'href="#item-1"' in part and "item 1" in text_of(part)


def test_expected_arrivals_are_counted_when_the_source_gives_them(tmp_path):
    berths = dict(fleet(), kind="berths", expected=[
        {"name": "Invented Arrival", "type": "tanker", "eta": "2026-11-20T14:00:00+01:00", "place": "botlek",
         "length_m": 250},
        {"name": "Invented Second", "type": "container", "eta": "2026-11-21T02:30:00+01:00", "place": None,
         "length_m": None}])
    html = preview_html(tmp_path, make_brief(sample=True, ships=berths))
    assert "2 expected in the next 24 h" in text_of(dial(html))
    expected = html[html.index('id="expected-title"'):]
    expected = text_of(expected[: expected.index("</table>")])
    assert "Invented Arrival" in expected and "14:00" in expected and LABELS["botlek"] in expected


def test_no_expected_line_without_arrivals_in_the_data(tmp_path):
    html = preview_html(tmp_path, make_brief(sample=True, ships=fleet()))   # AIS: expected is null
    assert "expected in the next 24 h" not in text_of(html) and 'id="expected-title"' not in html


def test_the_dial_says_where_the_ships_come_from(tmp_path):
    ais = text_of(dial(preview_html(tmp_path / "a", make_brief(sample=True, ships=fleet()))))
    berths = text_of(dial(preview_html(tmp_path / "b", make_brief(sample=True, ships=dict(fleet(), kind="berths")))))
    assert "AIS positions" in ais and "berth list" in berths


# --- the filter ------------------------------------------------------------------------------------------


def test_the_filter_has_every_type_present_cargo_too(tmp_path):
    part = chart_filter(preview_html(tmp_path, make_brief(sample=True, ships=snapshot(
        vessel(name="C1", type="cargo"), vessel(name="C2", type="cargo"), vessel(name="T1", type="tanker")))))
    buttons = re.findall(r'data-ship-filter="(\w+)"[^>]*>([^<]+)<span>(\d+)</span>', part)
    assert [(kind, label.strip(), count) for kind, label, count in buttons] == [
        ("all", "All", "3"), ("tanker", "Tanker", "1"), ("cargo", "Cargo", "2")]   # AIS: All / Cargo / Tanker


def test_the_chart_can_show_a_places_ships_and_the_ships_at_a_berth():
    assert 'action === "show-place"' in MAP_JS and "function showPlace(" in MAP_JS
    words = re.search(r"var words = \{([^}]*)\}\[status\]", MAP_JS).group(1)
    assert 'moored: "at a berth"' in words


# --- the ship list -------------------------------------------------------------------------------------------


def test_the_ship_list_names_each_ships_place(tmp_path):
    html = preview_html(tmp_path, make_brief(sample=True, ships=fleet()))
    table = html[html.index('id="ships-title"'):]
    table = table[: table.index("</table>")]
    assert "<th>Place</th>" in table or ">Place<" in table
    assert LABELS["ect-delta"] in text_of(table)


# --- switch off: exactly as before ---------------------------------------------------------------------------


def test_off_the_sample_dial_and_filter_are_as_before(tmp_path):
    html = render_days(tmp_path, make_brief(sample=True, ships=fleet()))[make_brief()["date"]]
    assert "dial-places" not in html and "at a berth" not in html and 'data-action="show-place"' not in html
    filters = re.findall(r'data-ship-filter="(\w+)"', chart_filter(html))
    assert filters == ["all", "container", "tanker", "bulk"]                   # the three filter types, as before
    assert "<th>Place</th>" not in html


# --- the sample data ------------------------------------------------------------------------------------------


def test_the_sample_day_has_a_few_invented_expected_arrivals():
    brief = json.loads((ROOT / "data" / "sample" / "briefs" / "2026-10-29.json").read_text(encoding="utf-8"))
    assert brief["ships"]["expected"] and ships.check_snapshot(brief["ships"], PLACE_IDS) == []


def test_the_places_are_grouped_in_code_not_in_the_template():
    assert "def ship_places(" in Path(render.__file__).read_text(encoding="utf-8")
