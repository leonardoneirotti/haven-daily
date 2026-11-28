"""A compact weather dial, and only the factual correction on the pages (issue #173, owner 28 Nov 2026).

1. MeteoAlarm's conditions (docs/permissions/2026-11-23-meteoalarm.md) and Terms §5 want their exact
   disclaimer with the displayed warnings; neither says it may be folded away. The owner's choice: one
   short visible line, "Morning snapshot, not live · Latest warnings on meteoalarm.org", the verbatim
   disclaimer still **visible** in small text, and the rest ("Haven Daily is not a MeteoAlarm or KNMI
   service.", the full snapshot sentence) under a small "Details" toggle: `<details>`, so it works
   without JavaScript. How it works keeps the full text (tests/test_meteoalarm_permission.py).
2. The #153 note ("Dutch titles are no longer shown", 23 and 25 Nov) is a site-wide change, not a
   correction of what a brief said: it stays in data/briefs/ and the spec, and no page shows it. The
   only correction shown is a short factual one on 23 Nov item 4. Which stored notes the pages leave
   out, and the short line, are in config/corrections.toml.
"""

import json
import re
import tomllib
from pathlib import Path

import pytest

from haven import render
from haven.render import METEOALARM_DISCLAIMER
from tests.test_render_real import dial, make_brief, render_day, text_of, weather

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://www.meteoalarm.org"
SPEC = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")

# --- 1. the weather dial ------------------------------------------------------------------------

READINGS = {
    "a warning": weather(),
    "no warnings": weather(value="No warnings", level="green", knmi_level="green", hazards=[], issued_at=None),
    "no data": weather(value=None, level=None, knmi_level=None, hazards=[], issued_at=None, note=None),
}


@pytest.fixture(params=list(READINGS))
def weather_dial(request, tmp_path):
    return dial(render_day(tmp_path, make_brief(status=[READINGS[request.param]])), "weather")


def visible(html):
    """The dial as it first shows: without what its Details toggle folds away."""
    return re.sub(r"<details\b.*?</details>", "", html, flags=re.S)


def folded(html):
    found = re.search(r'<details class="dial-details">(.*?)</details>', html, re.S)
    assert found, "no Details toggle on the weather dial"
    return found.group(1)


def test_one_short_visible_line_says_morning_snapshot_not_live_and_links_to_meteoalarm(weather_dial):
    line = re.search(r'<p class="dial-snapshot">(.*?)</p>', visible(weather_dial), re.S).group(1)
    assert text_of(line) == "Morning snapshot, not live · Latest warnings on meteoalarm.org"
    assert re.search(rf'<a href="{re.escape(SITE)}">Latest warnings on meteoalarm\.org', line)


def test_the_disclaimer_stays_visible_and_verbatim(weather_dial):
    assert METEOALARM_DISCLAIMER in text_of(visible(weather_dial))


def test_the_details_toggle_holds_the_rest_and_needs_no_javascript(weather_dial):
    inside = folded(weather_dial)
    assert re.search(r"<summary>Details</summary>", inside)
    assert "Haven Daily is not a MeteoAlarm or KNMI service." in text_of(inside)
    assert "Morning snapshot, not a live warning service." in text_of(inside)


def test_the_long_sentences_are_no_longer_in_the_visible_part(weather_dial):
    shown = text_of(visible(weather_dial))
    assert "Haven Daily is not a MeteoAlarm or KNMI service." not in shown
    assert "Morning snapshot, not a live warning service." not in shown


def test_the_spec_describes_the_compact_dial():
    assert "**A compact weather dial** *(#173" in SPEC


# --- 2. corrections on the pages ----------------------------------------------------------------

NOTE_153 = "Dutch titles are no longer shown (#153)"
SHORT = "Corrected 26 Nov: only the right lane was closed, not the whole road."
A16_URL = ("https://www.rijnmond.nl/nieuws/2286787/rioolslib-zorgt-voor-vertraging-op-a16-bij-moerdijkbrug-"
           "rechterrijstrook-dicht")


@pytest.fixture(scope="module")
def real_site(tmp_path_factory):
    site = tmp_path_factory.mktemp("site")
    render.render_site(ROOT / "data" / "briefs", site)
    return site


def page(site, name):
    return (site / name).read_text(encoding="utf-8")


def card(html, rank):
    start = html.index(f'id="item-{rank}"')
    return html[start:html.index("</li>\n", start)]


def test_no_page_shows_the_153_note(real_site):
    for path in real_site.rglob("*.html"):
        text = text_of(path.read_text(encoding="utf-8"))
        assert "Dutch titles are no longer shown" not in text and "(#153)" not in text, path.name


def test_23_nov_item_4_shows_the_short_factual_correction(real_site):
    html = page(real_site, "days/2026-11-23.html")
    item = card(html, 4)
    assert A16_URL in item and SHORT in text_of(item)
    assert text_of(html).count("Corrected 26 Nov: only the right lane") == 1


def test_23_nov_points_to_the_corrected_item_instead_of_a_list(real_site):
    html = page(real_site, "days/2026-11-23.html")
    assert 'id="corrections"' not in html  # no list: its only note is left out
    publication = re.search(r'<p class="publication">(.*?)</p>', html, re.S).group(1)
    assert "Corrected 26 Nov 06:04" in text_of(publication)
    assert '<a href="#item-4">See correction</a>' in publication


@pytest.mark.parametrize("name", ["days/2026-11-25.html", "index.html"])
def test_25_nov_and_today_show_no_correction(real_site, name):
    html = page(real_site, name)
    assert "Corrected" not in text_of(html) and "See correction" not in html


def test_the_stored_notes_are_unchanged():
    for day in ("2026-11-23", "2026-11-25"):
        brief = json.loads((ROOT / "data" / "briefs" / f"{day}.json").read_text(encoding="utf-8"))
        assert len(brief["corrections"]) == 1 and brief["corrections"][0]["note"].startswith(NOTE_153)


def test_the_display_rules_name_real_notes_and_a_real_item():
    # A typo here would silently show the note again, or show no short line: each entry must match.
    rules = tomllib.loads((ROOT / "config" / "corrections.toml").read_text(encoding="utf-8"))
    for rule in rules["hidden"] + rules["item"]:
        brief = json.loads((ROOT / "data" / "briefs" / f"{rule['date']}.json").read_text(encoding="utf-8"))
        assert any(fix["at"] == rule["at"] for fix in brief["corrections"]), rule
    for rule in rules["item"]:
        brief = json.loads((ROOT / "data" / "briefs" / f"{rule['date']}.json").read_text(encoding="utf-8"))
        assert any(i["url"] == rule["url"] for i in brief["items"]), rule


def test_the_spec_describes_what_the_pages_show():
    assert "**What the pages show of a correction** *(#173" in SPEC
