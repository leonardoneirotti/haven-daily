"""Item cards and the panel (issue #82; design review S5, S10, S11, M3; spec §7.4, §7.5, §7.8, §8.5).

- S5: a card with no summary (headline-only source, article not read, unrated) is short: the
  headline, one grey line saying why, the "affects" tags and the links. No impact block, and no
  "No single place on the chart" line anywhere (an item without a place has no button).
  "Not enough information" stays for a rated item that has a summary but no impact.
- S10: the brief's "Show on chart" sentence only when a shown item has a place; a visible
  marker on the ship list's header; the "whole port" button labelled on wide screens.
- S11: panel severity words, status labels and kicker at 13-14 px; no "affects" tag in the panel.
- M3: every panel entry opens in the panel (summary or the headline-only line) and is still a
  plain #item-N link without JavaScript. (The click itself is checked in headless Edge, §8.7.)

Headlines are invented.
"""

import re
from pathlib import Path

import pytest

from test_first_screen import PLACE, SHIPS, css_rules
from test_render_real import make_brief, news, news_card, render_day, text_of

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
MAP_JS = (ROOT / "static" / "map.js").read_text(encoding="utf-8")

HEADLINE_ONLY_LINE = ("Headline only (the source's terms don't allow a summary) · "
                      "severity rated from the headline")
UNREAD_LINE = "Headline only (the article couldn't be read) · severity rated from the headline"
UNRATED_LINE = "Headline only (the AI step failed for this item) · no summary, impact or severity"
INTRO_SENTENCE = '"Show on chart" moves the chart above the brief.'


def headline_only(severity="medium", **fields):
    return news(severity, "Invented headline-only story", source="NL Times", language="nl",
                access="headline-only", summary=None, impact=None, affects=["Containers", "Labour"], **fields)


def unread(**fields):
    """A `use` item whose article couldn't be read: rated from its headline (spec §5.5 point 2)."""
    return news("low", "Invented unreadable story", summary=None, impact=None, affects=["Barge"], **fields)


def unrated(**fields):
    return news(None, "Invented unrated story", **fields)


def card_of(tmp_path, item):
    return news_card(render_day(tmp_path, make_brief(items=[item])), 1)


def panel_items(html):
    start = html.index('class="panel-items"')
    return html[start : html.index("</ol>", start)]


def panel_entries(html):
    return re.findall(r'<a class="panel-item"[^>]*>.*?</a>', panel_items(html), flags=re.S)


# --- S5: the short card ------------------------------------------------------------------------


@pytest.mark.parametrize("make, line", [(headline_only, HEADLINE_ONLY_LINE), (unread, UNREAD_LINE),
                                        (unrated, UNRATED_LINE)])
def test_a_card_without_a_summary_has_one_line_and_no_impact_block(tmp_path, make, line):
    card = card_of(tmp_path, make())
    text = text_of(card)
    assert line in text
    assert "Impact for planners" not in text
    assert "Not enough information" not in text
    assert "item-impact" not in card


def test_the_short_line_is_grey(tmp_path):
    card = card_of(tmp_path, headline_only())
    assert re.search(r'<p class="item-summary is-empty">\s*' + re.escape(HEADLINE_ONLY_LINE.replace("'", "&#39;")),
                     card)


def test_the_headline_only_card_keeps_its_tags_and_links(tmp_path):
    text = text_of(card_of(tmp_path, headline_only()))
    assert "Affects Containers · Labour" in text
    assert "Read original (Dutch)" in text
    assert "Read in English" in text


def test_the_unread_card_keeps_its_tags(tmp_path):
    assert "Affects Barge" in text_of(card_of(tmp_path, unread()))


def test_the_severity_is_not_said_twice(tmp_path):
    """The line says the severity was rated from the headline; the old tag next to it is gone."""
    for n, item in enumerate((headline_only(), unread())):
        card = card_of(tmp_path / str(n), item)
        assert "rated from headline only" not in text_of(card)
        assert "sev-note" not in card


def test_the_unrated_card_still_says_unrated(tmp_path):
    card = card_of(tmp_path, unrated())
    assert "Severity: unrated" in text_of(card)
    assert "num-unrated" in card


def test_a_rated_item_with_a_summary_but_no_impact_keeps_not_enough_information(tmp_path):
    text = text_of(card_of(tmp_path, news("medium", impact=None)))
    assert "Own-words summary." in text
    assert "Impact for planners" in text
    assert "Not enough information in the source to judge the impact." in text
    assert "Headline only" not in text


def test_a_full_card_is_unchanged(tmp_path):
    text = text_of(card_of(tmp_path, news("high")))
    assert "Own-words summary." in text and "Something follows for planners." in text
    assert "Affects Containers" in text


@pytest.mark.parametrize("make", [headline_only, unread, unrated, lambda: news("high")])
def test_no_card_says_it_has_no_place_on_the_chart(tmp_path, make):
    card = card_of(tmp_path, make())
    assert "No single place on the chart" not in text_of(card)
    assert "Show on chart" not in text_of(card)  # no place, no button


def test_a_headline_only_item_with_a_place_keeps_its_button(tmp_path):
    card = card_of(tmp_path, headline_only(map=dict(PLACE)))
    assert 'data-action="show-item"' in card and "Show on chart" in text_of(card)


# --- S10: intro sentence, ship list marker, "Whole port" ---------------------------------------


def test_the_intro_sentence_shows_when_an_item_has_a_place(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news("high"), news("low", "Other", map=dict(PLACE))]))
    assert INTRO_SENTENCE in text_of(html)


@pytest.mark.parametrize("ships", [None, SHIPS])
def test_the_intro_sentence_is_left_out_when_no_item_has_a_place(tmp_path, ships):
    html = render_day(tmp_path, make_brief(items=[news("high"), headline_only()], ships=ships))
    assert "Show on chart" not in text_of(html)
    assert "2 items, most severe first." in text_of(html)


def test_a_place_on_an_item_cut_from_the_five_does_not_bring_the_sentence_back(tmp_path):
    items = [news("high", f"Shown {n}") for n in range(5)] + [news("low", "Cut", map=dict(PLACE))]
    assert "Show on chart" not in text_of(render_day(tmp_path, make_brief(items=items)))


def test_the_ship_list_header_shows_that_it_opens(tmp_path):
    html = render_day(tmp_path, make_brief(ships=SHIPS))
    summary = re.search(r"<summary>(.*?)</summary>", html, flags=re.S).group(1)
    assert 'class="summary-marker"' in summary
    # it turns when the list is open
    assert any("details[open]" in sel and ".summary-marker" in sel and "transform" in body
               for sel, body in css_rules(CSS))


def test_the_whole_port_button_has_a_visible_label_and_keeps_its_name():
    assert re.search(r'class="chart-home-label">Whole port<', MAP_JS)
    assert 'setAttribute("aria-label", "Show the whole port")' in MAP_JS


def test_the_whole_port_label_shows_on_wide_screens_only():
    hidden = [body for sel, body in css_rules(CSS) if sel == ".chart-home-label"]
    assert any(re.search(r"display\s*:\s*none", body) for body in hidden)
    wide = re.search(r"@media \(min-width: 64rem\) \{(?:[^{}]*\{[^{}]*\})*?[^{}]*\.chart-home-label\s*\{([^{}]*)\}",
                     CSS)
    assert wide and not re.search(r"display\s*:\s*none", wide.group(1))


# --- S11: panel text sizes, no tag in the panel ------------------------------------------------


def rem(value):
    return float(re.match(r"([\d.]+)rem", value.strip()).group(1))


@pytest.mark.parametrize("selector", [".panel-meta .sev", ".mini-label", ".panel .kicker"])
def test_panel_small_text_is_13_to_14_px(selector):
    sizes = [rem(m) for sel, body in css_rules(CSS) if sel == selector
             for m in re.findall(r"font-size\s*:\s*([^;]+)", body)]
    assert sizes, selector
    assert all(0.8125 <= size <= 0.875 for size in sizes), (selector, sizes)


def test_the_panel_shows_no_affects_tag(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news("medium", affects=["Shortsea", "Containers"])]))
    assert "Shortsea" not in text_of(panel_items(html))
    assert "Shortsea" in text_of(news_card(html, 1))  # the full card keeps every tag


# --- M3: one behaviour for every panel entry ---------------------------------------------------


def test_every_panel_entry_is_selectable_and_a_plain_link(tmp_path):
    items = [news("high", map=dict(PLACE)), headline_only(), unread(), unrated(), news("low", "Placeless")]
    entries = panel_entries(render_day(tmp_path, make_brief(items=items)))
    assert len(entries) == 5
    for rank, entry in enumerate(entries, start=1):
        assert f'href="#item-{rank}"' in entry
        assert 'data-action="show-item"' in entry
        assert f'data-rank="{rank}"' in entry


@pytest.mark.parametrize("make, line", [(lambda: news("medium"), "Own-words summary."),
                                        (headline_only, HEADLINE_ONLY_LINE), (unread, UNREAD_LINE),
                                        (unrated, UNRATED_LINE)])
def test_every_panel_entry_has_something_to_open(tmp_path, make, line):
    entry = panel_entries(render_day(tmp_path, make_brief(items=[make()])))[0]
    opened = re.search(r'<span class="panel-summary[^"]*">(.*?)</span>', entry, flags=re.S)
    assert opened and text_of(opened.group(1)) == line


def test_selecting_an_item_without_a_place_clears_the_chart_focus():
    """map.js: an item with no place opens in the panel, hides the old focus box and says so."""
    branch = re.search(r"if \(!callout\) \{(.*?)\n    \}", MAP_JS, flags=re.S)
    assert branch, "selectItem needs its own branch for an item without a place"
    assert "hideFocus()" in branch.group(1)
    assert "setHash(" in branch.group(1)
