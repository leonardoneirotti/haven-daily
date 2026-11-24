"""Launch fixes from the owner's site review (issue #138; spec §2.1, §2.2, §4, §5.10.1, §7.4, §7.5, §7.8).

1. The Ships dial (full dial and the panel's mini cell) is hidden until ship positions are collected
   (v2, `render.AIS_SNAPSHOT_BUILT`). The ship filter is part of the same feature: it only exists
   on a day with ships, so v1 never shows it.
2. Roads on the chart: the 23 Nov A15/A20 road works got no pin because the place list had no
   roads, so "none" was the right answer. The A15 and A20 are on the list now (kind "road").
3. Failure notes in plain words for readers ("NL Times could not be reached today"); the stored
   brief keeps the technical line for the owner.
4. NL Times and Nieuwsblad Transport are paused for launch (`enabled = false`; their config kept).
5. One identity sentence everywhere (`render.IDENTITY`).
6. The short card's grey line is shorter (owner's option A).
7. The publisher's permission note is on the card only, not in the panel's list.
8. "How it works" is shorter and no longer says the AI keeps an item when unsure (#124).

Headlines are invented.
"""

import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from haven import collect, render
from haven.config import PLACE_KINDS, ConfigError, load_places, load_sources, load_tag_list
from haven.places import pick
from haven.summarise import system_prompt
from test_render_real import make_brief, news, news_card, render_day, text_of

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_BRIEFS = ROOT / "data" / "sample" / "briefs"

IDENTITY = ("Second-year International Business student (Supply Chain Management) "
            "at Rotterdam University of Applied Sciences.")


def panel(html):
    start = html.index('class="panel-items"')
    return html[start : html.index("</ol>", start)]


def panel_status(html):
    start = html.index('class="panel-status"')
    return html[start : html.index("</ul>", start)]


@pytest.fixture(scope="module")
def sample_site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    render.render_site(SAMPLE_BRIEFS, out)
    return out


# --- 1. Ships hidden until v2 ------------------------------------------------------------------


def test_v1_day_has_no_ships_dial_and_no_ships_cell_in_the_panel(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news()]))
    assert 'data-key="ships"' not in html
    assert "Ships in the port area" not in text_of(html)
    assert "Ships in the port area" not in panel_status(html)


def test_v1_day_has_no_ship_filter(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news()]))
    assert "chart-filter" not in html and "data-ship-filter" not in html


def test_from_v2_a_failed_snapshot_still_shows_the_ships_dial(tmp_path, monkeypatch):
    """Hard rule 9: once ships are collected, a missing snapshot is a failure and is shown."""
    monkeypatch.setattr(render, "AIS_SNAPSHOT_BUILT", True)
    html = render_day(tmp_path, make_brief(items=[news()]))
    assert 'data-key="ships"' in html
    assert "Ships in the port area" in panel_status(html)
    assert "The AIS snapshot failed" in text_of(html)


def test_sample_day_with_ships_keeps_the_dial_and_the_filter(sample_site):
    """The sample briefs preview v2 with ships: the ship feature stays complete there."""
    with_ships = [p for p in (sample_site / "days").glob("*.html") if "data-ship-filter" in p.read_text(encoding="utf-8")]
    assert with_ships
    html = with_ships[0].read_text(encoding="utf-8")
    assert 'data-key="ships"' in html and "Ships in the port area" in panel_status(html)


# --- 2. Roads on the chart ---------------------------------------------------------------------


def test_road_is_a_place_kind():
    assert "road" in PLACE_KINDS


# On each road's stretch inside the port (owner's option A, PR #139 review): the A15 at exit 15 near
# the Botlek, the A20 at exit 7 Maassluis. The junctions with the A4 (Benelux, Kethelplein) were further
# east and hid 4 more pin pairs at the opening view.
@pytest.mark.parametrize("place_id, label, osm, lat, lon", [("a15", "A15", "node/44155110", 51.8686, 4.2714),
                                                            ("a20", "A20", "node/322088946", 51.9253, 4.2672)])
def test_the_a15_and_a20_are_on_the_place_list(place_id, label, osm, lat, lon):
    place = next(p for p in load_places() if p.id == place_id)
    assert (place.label, place.kind, place.osm, place.lat, place.lon) == (label, "road", osm, lat, lon)


def test_the_summariser_is_offered_the_roads():
    prompt = system_prompt(load_places(), load_tag_list())
    assert "- a15: A15 (road)" in prompt
    assert "- a20: A20 (road)" in prompt


def test_road_works_on_the_a15_now_get_a_pin():
    """The 23 Nov item (A15, A20 and N59 closures): the AI could only answer "none" then."""
    places = load_places()
    picked = pick("a15", ["Truck pickups", "Hinterland"], places=places)
    a15 = next(p for p in places if p.id == "a15")
    assert picked.map == {"lat": a15.lat, "lon": a15.lon, "label": "A15", "side": a15.side}
    assert picked.affects[:2] == ["Truck pickups", "Hinterland"]
    assert picked.unlisted is None


# --- 3. Failure notes in plain words -----------------------------------------------------------


@pytest.mark.parametrize("source, error, line", [
    ("NL Times", "https://nltimes.nl/tags/port-rotterdam: HTTP 403", "NL Times could not be reached today."),
    ("Contargo business news", "https://www.contargo.net/en/business/business-news: timed out after 20 s (tried twice)",
     "Contargo business news could not be reached today."),
    ("ECT news", "https://www.ect.nl/en/news-feed: HTTP 503 (tried twice)", "ECT news could not be reached today."),
    ("ECT news", "https://www.ect.nl/en/news-feed: robots.txt disallows /en/news-feed for HavenDaily; not fetched",
     "ECT news was not read today: its website asks automated readers not to visit."),
    ("ECT news", "https://www.ect.nl/en/news-feed: no news items found on the page (layout changed?)",
     "ECT news could not be read today: its page has changed."),
    ("ECT news", "https://www.ect.nl/en/news-feed: unexpected error (KeyError: 'x')",
     "ECT news could not be read today because of a fault in Haven Daily."),
    ("ECT news", "https://www.ect.nl/en/news/some-article: HTTP 404",
     "One ECT news article could not be opened, so that item has no summary."),
    ("Weather warnings (MeteoAlarm)", "https://feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands: HTTP 500 (tried twice)",
     "Weather warnings (MeteoAlarm) could not be reached today."),
    ("Weather warnings (MeteoAlarm)",
     "https://feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands: no Zuid-Holland entry for today in the feed "
     "(area renamed or feed changed?)",
     "Weather warnings (MeteoAlarm) could not be read today: its feed has changed."),
])
def test_a_failure_reads_as_a_plain_sentence(source, error, line):
    assert render.plain_failure({"source": source, "error": error}) == line


def test_a_line_that_is_already_plain_keeps_its_words_without_an_address():
    gap = ("couldn't check whether any notices were missed since the last run: "
           "there is no earlier run in the last 14 days")
    assert render.plain_failure({"source": "PIN notices to shipping", "error": gap}) == \
        f"PIN notices to shipping: {gap}."


def test_two_failed_feeds_of_one_source_are_one_line():
    failures = [{"source": "Nieuwsblad Transport", "error": "https://www.nt.nl/havens/feed/: HTTP 403"},
                {"source": "Nieuwsblad Transport", "error": "https://www.nt.nl/tag/rotterdam/feed/: HTTP 403"}]
    assert render.failure_lines(failures) == ["Nieuwsblad Transport could not be reached today."]


def test_the_day_page_shows_no_status_codes_or_addresses_in_its_failures(tmp_path):
    failures = [{"source": "NL Times", "error": "https://nltimes.nl/tags/port-rotterdam: HTTP 403"},
                {"source": "Nieuwsblad Transport", "error": "https://www.nt.nl/havens/feed/: HTTP 403"}]
    brief = make_brief(items=[news()])
    brief["build"]["failures"] = failures
    html = render_day(tmp_path, brief)
    start = html.index('<ul class="failures">')
    block = text_of(html[start : html.index("</ul>", start)])
    assert "NL Times could not be reached today." in block
    assert "Nieuwsblad Transport could not be reached today." in block
    assert "HTTP" not in block and "http" not in block and "403" not in block


# --- 4. NL Times and Nieuwsblad Transport paused for launch -------------------------------------


@pytest.mark.parametrize("source_id", ["nl-times", "nieuwsblad-transport"])
def test_the_403_sources_are_paused_but_keep_their_config(source_id):
    source = next(s for s in load_sources() if s.id == source_id)
    assert source.enabled is False
    assert source.fetched is False
    assert source.verdict == "headline-only" and source.urls and source.home


def test_every_other_fetched_source_stays_enabled():
    assert {s.id for s in load_sources() if not s.enabled} == {"nl-times", "nieuwsblad-transport"}


def test_the_config_says_why_they_are_paused():
    text = (ROOT / "config" / "sources.toml").read_text(encoding="utf-8")
    for source_id in ("nl-times", "nieuwsblad-transport"):
        entry = text[text.index(f'id = "{source_id}"') : text.index("[[source]]", text.index(f'id = "{source_id}"'))]
        assert "enabled = false" in entry
        comment = "\n".join(line for line in entry.splitlines() if line.lstrip().startswith("#"))
        assert "403" in comment and "GitHub" in comment


def write_sources(tmp_path, extra):
    path = tmp_path / "sources.toml"
    path.write_text('[[source]]\nid = "x"\nname = "X"\nverdict = "use"\nhome = "https://x.test/"\n'
                    'urls = ["https://x.test/feed"]\naccess = "rss"\nlanguage = "en"\n' + extra, encoding="utf-8")
    return path


def test_enabled_must_be_true_or_false(tmp_path):
    with pytest.raises(ConfigError, match="'enabled' must be true or false"):
        load_sources(write_sources(tmp_path, 'enabled = "no"\n'))


def test_a_source_is_enabled_unless_the_config_says_otherwise(tmp_path):
    (source,) = load_sources(write_sources(tmp_path, ""))
    assert source.enabled is True and source.fetched is True


def test_the_collector_never_reads_a_paused_source(tmp_path):
    (source,) = load_sources(write_sources(tmp_path, "enabled = false\n"))
    called = []

    def collector(src, fetcher, previous_run):
        called.append(src.id)
        raise AssertionError("a paused source must not be read")

    result = collect.run_collect((source,), fetcher=None, today=date(2026, 11, 25), data_dir=tmp_path,
                                 now=lambda: datetime(2026, 11, 25, 5, 45, tzinfo=timezone.utc), collector=collector)
    assert called == [] and result.failures == []


def test_how_it_works_lists_the_paused_sources_as_paused(sample_site):
    text = text_of((sample_site / "about.html").read_text(encoding="utf-8"))
    for name in ("NL Times", "Nieuwsblad Transport"):
        assert re.search(rf"{name} .{{0,160}}Paused for now", text), name


def test_sources_md_says_they_are_paused():
    text = (ROOT / "SOURCES.md").read_text(encoding="utf-8")
    for name in ("NL Times", "Nieuwsblad Transport"):
        row = next(line for line in text.splitlines() if line.startswith(f"| {name}") or f"| {name} |" in line)
        assert "paused" in row.lower(), name


# --- 5. One identity sentence ------------------------------------------------------------------


def test_the_identity_sentence_is_one_constant():
    assert render.IDENTITY == IDENTITY


def test_the_identity_is_in_the_footer_of_every_page(sample_site):
    pages = [sample_site / "index.html", sample_site / "archive.html", sample_site / "about.html",
             *sorted((sample_site / "days").glob("*.html"))]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        footer = html[html.index('<footer class="site-footer">') :]
        assert IDENTITY in text_of(footer), page.name


def test_the_identity_is_in_the_about_block_and_how_it_works(sample_site):
    today = text_of((sample_site / "index.html").read_text(encoding="utf-8").split('<footer')[0])
    how = (sample_site / "about.html").read_text(encoding="utf-8")
    maker = text_of(how[how.index('id="maker"') : how.index("</section>", how.index('id="maker"'))])
    assert IDENTITY in today
    assert IDENTITY in maker


def test_the_identity_is_in_the_readme():
    assert IDENTITY in (ROOT / "README.md").read_text(encoding="utf-8")


def test_no_page_or_readme_uses_another_description_of_the_owner(sample_site):
    texts = [(ROOT / "README.md").read_text(encoding="utf-8")]
    texts += [p.read_text(encoding="utf-8") for p in sample_site.rglob("*.html")]
    for text in texts:
        plain = text_of(text)
        assert "BBA" not in plain
        assert "an International Business student" not in plain


# --- 6. The shorter headline-only line (owner's option A) --------------------------------------


def test_the_headline_only_lines_are_short():
    assert render.HEADLINE_NOTES == {
        "headline-only": "Headline only · severity from the headline",
        "unread": "Headline only · article couldn't be read · severity from the headline",
        "unrated": "Headline only · AI step failed · no summary or severity",
    }


# --- 7. The permission note: on the card, not in the panel's list --------------------------------


def rijnmond(**fields):
    return news("medium", "Invented Rijnmond story", source="RTV Rijnmond", language="nl",
                permission={"max_sentences": 2, "impact": True}, **fields)


def test_the_permission_note_is_not_in_the_panel(tmp_path):
    html = render_day(tmp_path, make_brief(items=[rijnmond()]))
    assert "panel-permission" not in html
    assert "permission" not in text_of(panel(html)).lower()


def test_the_permission_note_stays_on_the_card(tmp_path):
    html = render_day(tmp_path, make_brief(items=[rijnmond()]))
    assert "AI summary, with RTV Rijnmond's permission." in text_of(news_card(html, 1))


# --- 8. How it works: shorter, and the filter rule of #124 ---------------------------------------


BEFORE_WORDS = 3071  # main text of How it works on main, 24 Nov 2026 (#138)


def words_of_main(html):
    main = html[html.index("<main") : html.index("</main>")]
    return len(text_of(main).split())


def test_how_it_works_is_at_least_a_third_shorter(sample_site):
    words = words_of_main((sample_site / "about.html").read_text(encoding="utf-8"))
    assert words <= BEFORE_WORDS * 2 // 3, words


def test_how_it_works_no_longer_says_the_ai_keeps_an_item_when_unsure(sample_site):
    text = text_of((sample_site / "about.html").read_text(encoding="utf-8")).lower()
    assert "unsure whether it matters" not in text
    assert "it keeps the item" not in text
    assert "clear link" in text


# === PR #139 review (owner, 24 Nov 2026) ========================================================

# --- 1. No ship line in v1 ------------------------------------------------------------------------


def test_v1_says_nothing_about_ships_on_the_day_page_or_how_it_works(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news()]))
    assert "Ship positions are not collected yet" not in text_of(html)
    how = (tmp_path / "site" / "about.html").read_text(encoding="utf-8")
    assert "Ship positions are not collected yet" not in text_of(how)


def test_from_v2_a_failed_snapshot_is_still_said_under_the_chart(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "AIS_SNAPSHOT_BUILT", True)
    html = render_day(tmp_path, make_brief(items=[news()]))
    assert "The AIS snapshot failed." in text_of(html)


# --- 2. A road pin only when the item names nothing more specific ----------------------------------


from haven import places as haven_places  # noqa: E402
from test_summarise import full, item as summary_item, run  # noqa: E402


@pytest.mark.parametrize("answer, text, chosen", [
    ("a15", "Invented: A15 closed near the Maasvlakte tonight", "maasvlakte"),
    ("a15", "Invented: works on the A15 at Maasvlakte 2", "maasvlakte-2"),          # "2" for "II"
    ("a15", "Invented: A15 closed near Maasvlakte II", "maasvlakte-2"),             # the longer label wins
    ("a20", "Invented: A20 lane closed. Trucks for Europoort and Botlek divert.", "europoort"),  # first named
    ("a15", "Invented: closures on the A15, A20 and N59 this week", "a15"),          # nothing more specific
    ("a15", "Invented: A15 works near Botlekbrug", "botlekbrug"),                     # whole words only
    ("botlek", "Invented: Europoort and Botlek", "botlek"),                           # not a road: unchanged
    ("none", "Invented: Botlek news", "none"),                                       # no pin stays no pin
])
def test_a_road_gives_way_to_a_more_specific_place_the_item_names(answer, text, chosen):
    assert haven_places.prefer_specific(answer, text, load_places()) == chosen


def test_the_prompt_tells_the_ai_to_prefer_the_more_specific_place():
    prompt = system_prompt(load_places(), load_tag_list())
    assert "a road only when the item names no more specific place" in prompt.lower()


def test_the_summariser_applies_it_to_the_ai_answer():
    headline = "Invented: A15 closed near Botlek tonight"
    result, _ = run([summary_item(headline=headline)], full(place="a15", strike=None))
    [done] = result.items
    assert done.ai["map"]["label"] == "Botlek"


def test_the_summariser_keeps_the_road_when_nothing_more_specific_is_named():
    headline = "Invented: closures on the A15, A20 and N59 this week"
    result, _ = run([summary_item(headline=headline)],
                    full(place="a15", strike=None, summary="Invented: road works close two motorways."))
    [done] = result.items
    assert done.ai["map"]["label"] == "A15"


def test_the_23_nov_brief_is_unchanged():
    brief = (ROOT / "data" / "briefs" / "2026-11-23.json").read_text(encoding="utf-8")
    road = [line for line in brief.splitlines() if "wegen gaan deze week dicht" in line]
    assert road  # the item is still there, and the file has no correction about it
    assert '"corrections": []' in brief


# --- 9. The one-liner is not on the page; the description for link previews stays ------------------


ONE_LINER = ("What affects the Port of Rotterdam today, and what it means for logistics planners. "
             "Updated every morning.")


def test_the_one_liner_is_on_no_page(sample_site, tmp_path):
    real = render_day(tmp_path, make_brief(items=[news()]))
    for page in [real, *(p.read_text(encoding="utf-8") for p in sample_site.rglob("*.html"))]:
        assert ONE_LINER not in text_of(re.sub(r"<head>.*?</head>", "", page, flags=re.S))
        assert 'class="tagline"' not in page


def test_link_previews_and_search_keep_the_description(sample_site):
    html = (sample_site / "index.html").read_text(encoding="utf-8")
    first = "What affects the Port of Rotterdam today, and what it means for logistics planners."
    assert re.search(r'<meta name="description" content="' + re.escape(first), html)
    assert re.search(r'<meta property="og:description" content="' + re.escape(first), html)


def test_a_real_page_has_no_strip_under_the_header_and_a_sample_page_keeps_its_note(sample_site, tmp_path):
    real = render_day(tmp_path, make_brief(items=[news()]))
    assert 'class="masthead"' not in real
    sample = (sample_site / "index.html").read_text(encoding="utf-8")
    assert 'class="masthead"' in sample and "Sample data." in text_of(sample)


# --- 10. The laptop chart: full width, the window's full height -------------------------------------


CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_the_laptop_chart_keeps_mains_height():
    """Owner, option A of the PR #139 review: main's height (812 px at 1440 x 900). A taller chart has a
    higher minimum zoom (the map sheet's north-south extent is fixed), so more pin pairs were hidden
    at the opening view. With the one-liner gone the whole chart is on screen when the page opens
    (chart 57..869 px at 1440 x 900, measured in headless Edge, PR #139)."""
    from test_map_upgrades import wide_rules
    stage = wide_rules(".stage")
    assert "height: clamp(36rem, calc(100vh - 5.5rem), 62rem);" in stage
    assert "width:" not in stage and "margin-inline" not in stage  # still full width


def test_the_phone_chart_is_still_unchanged():
    base = re.search(r"(?m)^\.chart-map \{(.*?)^\}", CSS, flags=re.S).group(1)
    assert "height: 62vh;" in base and "min-height: 340px;" in base and "max-height: 560px;" in base


# --- One map size on every day (owner, before merging PR #139) --------------------------------------
# Wide screens: an empty day (nothing to pin, no ships) gets the same big map and floating panel as a
# day with pins, with the "No item has a place on the chart" line visible. Phones keep their strip.


def media_blocks(css: str, query: str) -> list[str]:
    """The bodies of every `@media <query> { … }` block (top-level, closed by a line with only "}")."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return re.findall(r"@media " + re.escape(query) + r" \{(.*?)\n\}", css, flags=re.S)


def test_wide_screens_have_no_empty_day_layout():
    for block in media_blocks(CSS, "(min-width: 64rem)"):
        assert ".stage-empty" not in block


def test_the_strip_is_for_phones_only():
    outside = re.sub(r"@media [^{]+\{.*?\n\}", "", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S), flags=re.S)
    assert ".stage-empty" not in outside  # no rule for every width
    phone = "".join(media_blocks(CSS, "(max-width: 63.99rem)"))
    assert re.search(r"\.stage-empty \.chart-map \{[^}]*height: 30vh;[^}]*min-height: 15rem;[^}]*max-height: 20rem;",
                     phone)


def test_an_empty_day_keeps_its_panel_list_and_says_why_on_the_map(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news("medium")]))
    assert 'class="panel-items"' in html
    legend = html[html.index('class="chart-legend'):]
    assert "No item has a place on the chart today." in text_of(legend[: legend.index("</div>")])
