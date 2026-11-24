"""Map upgrades (issue #134, part 2; spec §7.4, §7.5, §8.5).

- Laptop: the chart taller and less wide: at most 80rem wide, centred in a rounded frame, as tall as
  the window minus the top bar (40-64rem). Owner's choice, 24 Nov 2026. Phones unchanged.
- A full-screen button on the chart. Where the browser has no full screen for a page element
  (iPhone Safari), an "expanded" chart that fills the window, with a close button. Escape closes it.
- Clicking or tapping a pin opens a small card: number, severity, English headline (or the
  original), summary, links. Close button, Escape or a click outside closes it; keyboard accessible.
- Speed targets and the Content-Security-Policy kept; the speed checks run in GitHub Actions.

map.js needs Leaflet and a browser, so it is checked here by reading it; the card's HTML is a pure
function in pins.js and runs in Node; tools/check_map_input.mjs clicks, taps and presses keys in
headless Chrome in the speed run (speed.yml), before and after.
"""

import json
import re
from pathlib import Path

import pytest

from haven import render
from test_map_input import CHECK_TOOL, CSS, MAP_JS, block
from test_pins_geometry import NODE, js
from test_render_real import make_brief, news

ROOT = Path(__file__).resolve().parent.parent
SPEC = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")
CHECKS = CHECK_TOOL.read_text(encoding="utf-8")
PLACE = {"lat": 51.95, "lon": 4.05, "label": "ECT Delta", "side": "right"}

needs_node = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def wide_rules(selector: str) -> str:
    """The body of `selector`'s rule inside the first wide-screen block that has it."""
    for block_match in re.finditer(r"@media \(min-width: 64rem\) \{(.*?)\n\}", CSS, flags=re.S):
        rule = re.search(r"(?m)^  " + re.escape(selector) + r" \{(.*?)^  \}", block_match.group(1), flags=re.S)
        if rule:
            return rule.group(1)
    raise AssertionError(f"no wide-screen rule for {selector}")


# --- the laptop chart: taller and less wide --------------------------------------------------


def test_the_laptop_stage_is_at_most_80rem_wide_centred_and_as_tall_as_the_window_minus_the_top_bar():
    stage = wide_rules(".stage")
    assert "height: clamp(40rem, calc(100vh - var(--topbar-h)), 64rem);" in stage
    assert "width: min(80rem, calc(100% - 2 * var(--gutter)));" in stage
    assert "margin-inline: auto;" in stage
    assert "border-radius: var(--radius);" in stage
    assert "clamp(36rem, calc(100vh - 5.5rem), 62rem)" not in CSS  # the old laptop height


def test_the_phone_chart_is_unchanged():
    base = re.search(r"(?m)^\.chart-map \{(.*?)^\}", CSS, flags=re.S).group(1)
    assert "height: 62vh;" in base and "min-height: 340px;" in base and "max-height: 560px;" in base


# --- the full-screen button and the expanded chart --------------------------------------------


def test_a_full_screen_button_uses_the_browser_full_screen_where_there_is_one():
    full = block("Full screen")
    assert "requestFullscreen" in full and "webkitRequestFullscreen" in full
    assert "fullscreenEnabled" in full and "webkitFullscreenEnabled" in full
    assert "fullscreenchange" in full
    assert "invalidateSize" in full  # the chart takes its new size
    assert 'L.DomUtil.create("button", "btn chart-fullscreen")' in full
    assert "aria-pressed" in full


def test_without_it_the_chart_is_expanded_with_a_close_button_and_escape_closes_it():
    full = block("Full screen")
    assert '"is-expanded"' in full
    assert "chart-close" in full and 'aria-label", "Close the full-screen chart"' in full
    assert '"Escape"' in full
    assert "chart-expanded" in full  # the page behind doesn't scroll
    expanded = re.search(r"(?m)^\.chart-frame\.is-expanded \{(.*?)^\}", CSS, flags=re.S).group(1)
    assert "position: fixed;" in expanded and "inset: 0;" in expanded
    assert re.search(r"(?m)^html\.chart-expanded \{\s*overflow: hidden;", CSS)
    assert ".chart-frame:fullscreen" in CSS


def test_keyboard_focus_stays_in_the_expanded_chart_and_comes_back_to_the_button():
    full = block("Full screen")
    assert '"Tab"' in full          # Tab wraps inside the expanded chart
    assert "button.focus()" in full  # back on the button when it closes


def test_the_panel_covers_nothing_while_the_chart_is_full_screen():
    cover = MAP_JS[MAP_JS.index("function panelCover()"):MAP_JS.index("function boundsOf(")]
    assert "isFull()" in cover


# --- the pin card -------------------------------------------------------------------------------


def payload(*items):
    brief = make_brief(items=list(items))
    render.prepare_briefs([brief])
    return brief["map"]["callouts"]


def test_the_map_data_carries_what_the_card_shows():
    [one, two] = payload(
        news("high", "Invented: Botlekbrug weer in bedrijf", language="nl", headline_en="Invented: Botlek bridge back",
             map=PLACE),
        news("medium", "Invented headline-only story", source="NL Times", access="headline-only", summary=None,
             impact=None, map=dict(PLACE, label="Euromax")),
    )
    assert one["title"] == "Invented: Botlek bridge back" and one["original"] == "Invented: Botlekbrug weer in bedrijf"
    assert one["summary"] == "Own-words summary." and one["url"].startswith("https://news.test/")
    assert one["translate_url"] and one["note"] is None
    assert two["original"] is None and two["summary"] is None
    assert two["note"].startswith("Headline only")  # the short card's line instead of a summary


def card(callout: dict, rank: int = 1) -> str:
    return js(f"P.cardHtml({json.dumps(callout)}, {rank})")


CALLOUT = {"rank": 1, "severity": "high", "title": "Invented: Botlek bridge back", "original": "Invented: Botlekbrug",
           "summary": "Own-words summary.", "note": None, "url": "https://news.test/1",
           "translate_url": "https://translate.test/1", "label": "Botlekbrug"}


@needs_node
def test_the_card_has_number_severity_headline_summary_and_links():
    html = card(CALLOUT)
    assert 'role="dialog"' in html and 'aria-labelledby="chart-card-title"' in html
    assert '<span class="num num-high">1</span>' in html and ">high<" in html
    assert 'id="chart-card-title"' in html and "Invented: Botlek bridge back" in html
    assert "Headline translated by AI" in html and "Invented: Botlekbrug" in html
    assert "Own-words summary." in html
    assert 'href="https://news.test/1"' in html and "Read original" in html
    assert 'href="https://translate.test/1"' in html and "Read in English" in html
    assert 'href="#item-1"' in html                                    # the full item below
    assert 'data-action="close-card"' in html and 'aria-label="Close"' in html


@needs_node
def test_a_card_without_a_summary_shows_the_short_line_and_no_missing_links():
    html = card(dict(CALLOUT, original=None, summary=None, note="Headline only (paywalled)", url=None,
                     translate_url=None))
    assert "Headline only (paywalled)" in html
    assert "translated by AI" not in html
    assert "Read original" not in html and "Read in English" not in html
    assert 'href="#item-1"' in html


@needs_node
def test_the_card_escapes_what_it_shows():
    html = card(dict(CALLOUT, title='<img src=x onerror="alert(1)">', summary="<b>x</b>"))
    assert "<img" not in html and "&lt;img" in html and "<b>" not in html


def test_a_pin_click_opens_the_card_and_escape_or_a_click_outside_closes_it():
    pick = block("Pin card")
    assert "L.popup(" in pick and "closeButton: false" in pick and '"chart-popup chart-card"' in pick
    assert "pinGeometry.cardHtml(" in pick
    assert '"Escape"' in pick
    assert pick.count(".focus(") >= 2  # into the card when it opens, back to the number when it closes
    wiring = block("Wiring")
    assert "closeCardOutside(event)" in wiring  # a click outside the card closes it
    assert "openCard(" in MAP_JS[MAP_JS.index("function selectItem("):MAP_JS.index("function showShips(")]


def test_the_card_keeps_clear_of_the_bars_on_top_and_the_buttons_on_the_right():
    # On a phone the card opened under the ship filter and the item line: its number, severity,
    # close button and the start of its headline were hidden (screenshot on PR #136, 24 Nov 2026).
    pick = block("Pin card")
    room = pick[pick.index("function cardRoom()"):pick.index("function openCard(")]
    assert ".chart-filter" in room and ".chart-focus" in room  # the bars on top of the chart
    assert ".leaflet-control-zoom" in room                     # the buttons on the right
    assert "maxHeight: room.height" in pick                    # never taller than the room left
    assert "autoPanPaddingTopLeft: [room.left, room.top]" in pick
    assert "autoPanPaddingBottomRight: [room.right, room.bottom]" in pick


def test_on_a_phone_the_card_summary_is_cut_to_three_lines():
    narrow = re.findall(r"@media \(max-width: 40rem\) \{(.*?)\n\}", CSS, flags=re.S)
    rule = next((re.search(r"\.chart-card-summary \{(.*?)\}", b, flags=re.S) for b in narrow
                 if ".chart-card-summary {" in b), None)
    assert rule, "no phone rule for the card summary"
    assert "-webkit-line-clamp: 3;" in rule.group(1) and "line-clamp: 3;" in rule.group(1)


def test_a_phone_tap_on_a_pin_no_longer_scrolls_the_page_to_the_full_card():
    select = MAP_JS[MAP_JS.index("function selectItem("):MAP_JS.index("function showShips(")]
    assert 'item.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" })' not in select


def test_the_card_has_its_own_styles_and_no_inline_script():
    assert ".chart-card " in CSS or ".chart-card{" in CSS or ".chart-card ." in CSS
    assert "onclick" not in MAP_JS and "javascript:" not in MAP_JS


# --- checked in a real browser, in the speed run -------------------------------------------------


@pytest.mark.parametrize("name", [
    "Laptop: chart size",
    "Phone: chart size",
    "Laptop: click on item 1's number opens its card",
    "Laptop: Escape closes the card",
    "Laptop: a click outside closes the card",
    "Laptop: keyboard Enter on item 1's number",
    "Laptop: full-screen button",
    "Laptop: no browser full screen (expanded chart)",
    "Phone: tap on item 1's number",
    "Phone: the card clear of the bars on top and inside the chart",
    "Phone: full-screen button (expanded, as on an iPhone)",
])
def test_the_browser_check_has_a_row_for(name):
    assert f'["{name}"' in CHECKS


def test_the_spec_describes_the_upgrades():
    assert "80rem" in SPEC and "Full screen" in SPEC and "pin card" in SPEC.lower()
