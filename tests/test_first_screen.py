"""The day page's first screen (issue #81; design review M1, M2, S4; spec §7.4, §7.8).

- M1: on a day with nothing to show on the chart (no callouts and no ships) the chart is a
  short strip with one line saying no item has a place on it; days with pins are unchanged.
- M2: the brief comes first: the panel (head, item list, mini status) is before the chart
  in the page, and phones no longer hide the panel's item list.
- S4: in v1 (`AIS_SNAPSHOT_BUILT = False`) no box over the chart, one grey line under it;
  from v2 a failed snapshot is a note in the chart's corner, not over the port.

Headlines are invented.
"""

import re
from pathlib import Path

import pytest

from haven import render
from test_render_real import make_brief, news, render_day, render_days, text_of

CSS = (Path(__file__).resolve().parent.parent / "static" / "style.css").read_text(encoding="utf-8")

PLACE = {"place": "ect-delta", "lat": 51.96, "lon": 4.03, "label": "ECT Delta"}
SHIPS = {
    "source_name": "Sample AIS data",
    "snapshot_start": "2026-11-20T06:00:00+01:00",
    "snapshot_end": "2026-11-20T06:12:00+01:00",
    "vessels": [{"name": "INVENTED ONE", "type": "container", "status": "moored", "lat": 51.96, "lon": 4.03,
                 "heading": 90, "speed_kn": 0, "length_m": 300, "flag": "LR", "area": "Maasvlakte",
                 "destination": "Rotterdam", "destination_raw": "NLRTM"}],
}
NO_PLACE_LINE = "No item has a place on the chart today."
SHIPS_LATER_LINE = "Ship positions are not collected yet."


def prepared(**fields):
    return render.prepare_briefs([make_brief(**fields)])[0]


def stage(html):
    start = html.index('<section class="stage')
    return html[start : html.index("</section>", start)]


def stage_tag(html):
    start = html.index('<section class="stage')
    return html[start : html.index(">", start) + 1]


def legend(html):
    start = html.index('class="chart-legend"')
    return html[start : html.index("</div>", start)]


def css_rules(css):
    """(selector, body) for every rule, at any @media depth."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)]


# --- M1: when the chart is empty ------------------------------------------------------------


def test_chart_is_empty_with_no_items_and_no_ships():
    assert prepared()["chart_empty"] is True


def test_chart_is_empty_when_no_item_has_a_place_and_there_are_no_ships():
    assert prepared(items=[news("high"), news("low", "Other invented headline")])["chart_empty"] is True


def test_chart_is_not_empty_when_an_item_has_a_place():
    assert prepared(items=[news("medium", map=dict(PLACE))])["chart_empty"] is False


def test_chart_is_not_empty_when_there_are_ships():
    assert prepared(ships=SHIPS)["chart_empty"] is False


def test_an_item_with_a_place_beyond_the_five_shown_does_not_count():
    items = [news("high", f"Shown {n}") for n in range(5)] + [news("low", "Cut", map=dict(PLACE))]
    assert prepared(items=items)["chart_empty"] is True


def test_empty_day_page_marks_the_stage_and_says_why(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news("medium")]))
    assert "is-empty" in stage_tag(html)
    assert NO_PLACE_LINE in text_of(legend(html))


def test_archived_empty_day_says_on_this_day(tmp_path):
    pages = render_days(tmp_path, make_brief(day="2026-11-19"), make_brief(day="2026-11-20"))
    assert "No item has a place on the chart on this day." in text_of(legend(pages["2026-11-19"]))
    assert NO_PLACE_LINE in text_of(legend(pages["2026-11-20"]))


def test_day_with_pins_keeps_the_full_chart(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news("medium", map=dict(PLACE))]))
    assert "is-empty" not in stage_tag(html)
    assert "No item has a place" not in html


def test_day_with_ships_but_no_pins_keeps_the_full_chart(tmp_path):
    html = render_day(tmp_path, make_brief(ships=SHIPS))
    assert "is-empty" not in stage_tag(html)


def test_the_stylesheet_makes_the_empty_chart_a_strip():
    """The class is used: some .is-empty rule sets the chart's height (exact sizes: spec §7.4)."""
    assert any(".is-empty" in sel and ".chart-map" in sel and re.search(r"(^|;)\s*height\s*:", body)
               for sel, body in css_rules(CSS))


def test_the_empty_strip_is_not_an_overlay_on_wide_screens():
    """On a wide screen the panel of an empty day is in the page flow, not floating over the chart."""
    assert any(".is-empty" in sel and ".panel" in sel and re.search(r"position\s*:\s*(static|relative)", body)
               for sel, body in css_rules(CSS))


# --- M2: the brief comes before the chart ----------------------------------------------------


@pytest.mark.parametrize("items", [[news("medium")], [news("medium", map=dict(PLACE))]])
def test_panel_head_items_and_status_come_before_the_chart(tmp_path, items):
    html = stage(render_day(tmp_path, make_brief(items=items)))
    chart = html.index('class="chart"')
    for part in ('class="panel-head"', 'class="panel-items"', 'class="panel-status"'):
        assert html.index(part) < chart, part


def test_phones_no_longer_hide_the_panel_item_list():
    """Only an empty day on a wide screen hides it (the full brief follows right below the strip)."""
    for sel, body in css_rules(CSS):
        if ".panel-items" in sel and re.search(r"display\s*:\s*none", body):
            assert ".is-empty" in sel, sel


# --- S4: ships note in v1, failure note in v2 ------------------------------------------------


@pytest.mark.parametrize("items", [[], [news("medium", map=dict(PLACE))]])
def test_v1_has_no_note_box_over_the_chart(tmp_path, items):
    html = render_day(tmp_path, make_brief(items=items))
    assert "chart-note" not in html
    assert SHIPS_LATER_LINE in text_of(legend(html))


def test_v1_ships_line_is_grey_text_in_the_legend(tmp_path):
    html = legend(render_day(tmp_path, make_brief()))
    assert re.search(r'<span class="legend-note">\s*' + re.escape(SHIPS_LATER_LINE), html)


def test_v1_day_with_ships_has_no_ships_line(tmp_path):
    html = render_day(tmp_path, make_brief(ships=SHIPS))
    assert SHIPS_LATER_LINE not in text_of(legend(html))


def test_v2_failed_snapshot_shows_a_note_on_the_chart(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "AIS_SNAPSHOT_BUILT", True)
    html = render_day(tmp_path, make_brief(items=[news("medium", map=dict(PLACE))]))
    note = re.search(r'<p class="chart-note">(.*?)</p>', html)
    assert note and "The AIS snapshot failed" in note.group(1)
    assert SHIPS_LATER_LINE not in text_of(html)


def test_v2_with_ships_has_no_failure_note(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "AIS_SNAPSHOT_BUILT", True)
    assert "chart-note" not in render_day(tmp_path, make_brief(ships=SHIPS))


def test_v2_failure_note_sits_off_the_port():
    """Not centred over the chart (that is the Maasvlakte): pinned to a corner instead."""
    bodies = [body for sel, body in css_rules(CSS) if sel == ".chart-note"]
    assert bodies
    for body in bodies:
        assert "translate(-50%" not in body
        assert not re.search(r"top\s*:\s*45%", body) and not re.search(r"left\s*:\s*50%", body)
