"""The newspaper view (issue #101; spec §7.9).

A second way to read the same day: a front page with the most severe item as the lead story, the
other items in columns below and the port status in a box at the side. The owner's decisions
(25 Nov 2026, #101):

- two real pages per day, `index.html` + `newspaper.html` (Today) and `days/<date>.html` +
  `days/<date>-newspaper.html`; a switch "Map | Newspaper" at the top of both, made of two links;
- nothing is remembered and nothing redirects (hard rule 14 unchanged);
- the newspaper page loads no map at all;
- RTV Rijnmond items are headline-only there and never the lead, until RTV Rijnmond agrees in
  writing (spec §11, condition 5): `newspaper = true` in its permission line switches it on;
- one original line drawing per tag (SVG files in static/illustrations/), labelled "Illustration";
- the weather box keeps every MeteoAlarm condition (the page has no other weather dial).

Headlines are invented.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest

from haven import render
from haven.config import ConfigError, load_sources, load_tag_list
from test_render_real import METEOALARM_DISCLAIMER, kaub, make_brief, news, render_days, strike, text_of, weather

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
ILLUSTRATIONS = ROOT / "static" / "illustrations"
DAY = "2026-11-20"
MAP_FILES = ("leaflet", "basemap.js", "map.js", "pins.js", "map-loader.js", "water.js", 'id="port-map"', 'id="map-data"')


def site_of(tmp_path, *briefs):
    render_days(tmp_path, *briefs)
    return tmp_path / "site"


def paper(tmp_path, brief):
    site = site_of(tmp_path, brief)
    return (site / "days" / f"{brief['date']}-newspaper.html").read_text(encoding="utf-8")


def part(html, start_marker, end_marker):
    start = html.index(start_marker)
    return html[start: html.index(end_marker, start)]


def lead(html):
    return part(html, '<article class="paper-lead', "</article>")


def columns(html):
    return part(html, '<ol class="paper-columns"', "</ol>")


def rijnmond(severity="high", headline="Invented Rijnmond strike story", **fields):
    return news(severity, headline, source="RTV Rijnmond", language="nl",
                permission={"max_sentences": 2, "impact": True}, **fields)


STATUS = [weather(), kaub(222, level="green"), strike("No active strike", "green")]


# --- pages and the switch -------------------------------------------------------------------------


def test_every_day_gets_a_newspaper_page_and_today_one_too(tmp_path):
    site = site_of(tmp_path, make_brief(day="2026-11-19"), make_brief(day=DAY))
    assert (site / "days" / "2026-11-19-newspaper.html").is_file()
    assert (site / "days" / f"{DAY}-newspaper.html").is_file()
    assert (site / "newspaper.html").is_file()


def switch(html):
    match = re.search(r'<nav class="view-switch" aria-label="View">(.*?)</nav>', html, re.S)
    assert match, "no switch"
    return dict((text_of(a), (href, "aria-current" in a)) for a, href in
                ((m.group(0), m.group(1)) for m in re.finditer(r'<a [^>]*href="([^"]+)"[^>]*>.*?</a>', match.group(1), re.S)))


@pytest.mark.parametrize("page, map_href, paper_href, current", [
    ("index.html", "index.html", "newspaper.html", "Map"),
    ("newspaper.html", "index.html", "newspaper.html", "Newspaper"),
    (f"days/{DAY}.html", f"../days/{DAY}.html", f"../days/{DAY}-newspaper.html", "Map"),
    (f"days/{DAY}-newspaper.html", f"../days/{DAY}.html", f"../days/{DAY}-newspaper.html", "Newspaper"),
])
def test_the_switch_is_two_links_and_marks_the_view_shown(tmp_path, page, map_href, paper_href, current):
    site = site_of(tmp_path, make_brief(day=DAY))
    links = switch((site / page).read_text(encoding="utf-8"))
    assert list(links) == ["Map", "Newspaper"]
    assert links["Map"][0] == map_href and links["Newspaper"][0] == paper_href
    assert [name for name, (_, on) in links.items() if on] == [current]


@pytest.mark.parametrize("page", ["archive.html", "about.html", "404.html"])
def test_pages_without_a_day_have_no_switch(tmp_path, page):
    site = site_of(tmp_path, make_brief(day=DAY))
    assert "view-switch" not in (site / page).read_text(encoding="utf-8")


def test_the_switch_sits_in_the_top_bar(tmp_path):
    html = paper(tmp_path, make_brief())
    bar = part(html, '<header class="topbar">', "</header>")
    assert 'class="view-switch"' in bar


def test_nothing_is_remembered_and_nothing_redirects():
    site_js = (ROOT / "static" / "site.js").read_text(encoding="utf-8")
    site_js = re.sub(r"/\*.*?\*/|//[^\n]*", "", site_js, flags=re.S)  # code only, not comments
    for word in ("localStorage", "sessionStorage", "location.replace", "location.href =", "cookie"):
        assert word not in site_js


def test_the_newspaper_page_loads_no_map(tmp_path):
    html = paper(tmp_path, make_brief(items=[news("medium", map={"lat": 51.95, "lon": 4.05, "label": "Maasvlakte",
                                                                   "side": "right"})], status=STATUS))
    for name in MAP_FILES:
        assert name not in html, name
    assert '<link rel="preload"' not in html
    assert re.findall(r'<script [^>]*src="([^"]+)"', html) == ["../static/site.js"]


def test_the_page_says_it_is_the_newspaper_view(tmp_path):
    html = paper(tmp_path, make_brief())
    assert re.search(r"<title>[^<]*Newspaper[^<]*</title>", html)
    assert f'<meta property="og:url" content="https://leonardoneirotti.github.io/haven-daily/days/{DAY}-newspaper.html">' in html


# --- the lead and the columns ---------------------------------------------------------------------


def test_the_lead_is_the_first_item_of_the_brief(tmp_path):
    items = [news("low", "Invented low story"), news("high", "Invented high story"), news("medium", "Invented medium story")]
    html = paper(tmp_path, make_brief(items=items, status=STATUS))
    assert "Invented high story" in text_of(lead(html))
    titles = re.findall(r'class="paper-title"[^>]*>(?:<a [^>]*>)?([^<]+)', columns(html))
    assert titles == ["Invented medium story", "Invented low story"]


def test_the_lead_has_a_big_headline_summary_impact_and_links(tmp_path):
    item = news("high", "Invented lead story", summary="Invented own-words summary.",
                impact="Invented impact; planners may want to plan around it.", affects=["Containers", "Labour"])
    html = lead(paper(tmp_path, make_brief(items=[item])))
    assert re.search(r'<h2 class="paper-title paper-headline"[^>]*>', html)
    assert "Invented own-words summary." in text_of(html)
    assert re.search(r'<p class="impact-text">\s*Invented impact', html)  # IBM Plex Serif, as on the cards
    assert "Impact for planners" in text_of(html) and "Affects Containers · Labour" in text_of(html)
    assert f'href="{item["url"]}"' in html and "Read original" in text_of(html)


def test_an_english_headline_is_shown_with_its_label_and_the_original(tmp_path):
    item = news("high", "Invented Nederlandse kop", language="nl", headline_en="Invented English headline")
    html = lead(paper(tmp_path, make_brief(items=[item])))
    assert "Invented English headline" in text_of(html)
    assert "Headline translated by AI · original (Dutch): Invented Nederlandse kop" in text_of(html)
    assert "Read in English" in text_of(html)


def test_a_headline_only_item_is_short(tmp_path):
    item = news("medium", "Invented headline-only story", source="The Loadstar", access="headline-only",
                summary=None, impact=None)
    html = columns(paper(tmp_path, make_brief(items=[news("high"), item])))
    story = part(html, "Invented headline-only story", "</li>")
    assert render.HEADLINE_NOTES["headline-only"] in text_of(story)
    assert "Impact for planners" not in story and "<img" not in story


def test_an_unrated_item_says_so_and_has_no_picture(tmp_path):
    html = columns(paper(tmp_path, make_brief(items=[news("high"), news(None, "Invented unrated story")])))
    story = part(html, "Invented unrated story", "</li>")
    assert "unrated" in text_of(story).lower() and "<img" not in story


def test_a_quiet_day_says_so_and_keeps_the_status_box(tmp_path):
    html = paper(tmp_path, make_brief(items=[], status=STATUS))
    assert "Nothing significant" in text_of(part(html, '<div class="paper-news"', '<aside'))
    assert 'class="paper-status"' in html and 'data-key="rhine"' in html


def test_the_numbers_are_the_same_as_on_the_map_page(tmp_path):
    items = [news("high", "Invented first"), news("medium", "Invented second")]
    html = paper(tmp_path, make_brief(items=items))
    assert 'id="item-1"' in lead(html) and 'id="item-2"' in columns(html)


# --- RTV Rijnmond: headline-only here until it agrees (spec §11, condition 5) ---------------------


def test_a_rijnmond_item_is_headline_only_and_never_the_lead(tmp_path):
    items = [rijnmond(summary="Invented Rijnmond summary.", impact="Invented Rijnmond impact; could delay pickups.",
                      affects=["Labour"]), news("medium", "Invented second story")]
    html = paper(tmp_path, make_brief(items=items))
    assert "Invented second story" in text_of(lead(html))
    story = part(columns(html), "Invented Rijnmond strike story", "</li>")
    text = text_of(story)
    for word in ("Invented Rijnmond summary.", "Invented Rijnmond impact", "permission", "Affects"):
        assert word not in text, word
    assert render.PAPER_HEADLINE_ONLY in text
    assert f'href="../days/{DAY}.html#item-1"' in story  # the summary is on the Map page
    assert "Read original (Dutch)" in text and "<img" not in story


def test_with_the_setting_on_a_rijnmond_item_is_shown_in_full(tmp_path, monkeypatch):
    sources = tuple(replace(s, permission=replace(s.permission, newspaper=True)) if s.permission else s
                    for s in load_sources())
    monkeypatch.setattr(render, "load_sources", lambda: sources)
    items = [rijnmond(summary="Invented Rijnmond summary."), news("medium", "Invented second story")]
    html = lead(paper(tmp_path, make_brief(items=items)))
    assert "Invented Rijnmond strike story" in text_of(html) and "Invented Rijnmond summary." in text_of(html)
    assert "AI summary, with RTV Rijnmond's permission." in text_of(html)


def test_a_day_with_only_rijnmond_items_has_no_lead(tmp_path):
    html = paper(tmp_path, make_brief(items=[rijnmond()]))
    assert "paper-lead" not in html
    assert "Invented Rijnmond strike story" in text_of(columns(html))


def test_the_rijnmond_setting_is_off_in_the_config():
    rtv = next(s for s in load_sources() if s.id == "rtv-rijnmond")
    assert rtv.permission is not None and rtv.permission.newspaper is False


def write_permission(tmp_path, extra):
    path = tmp_path / "sources.toml"
    path.write_text('[[source]]\nid = "x"\nname = "X"\nverdict = "headline-only"\nhome = "https://x.test/"\n'
                    'urls = ["https://x.test/feed"]\naccess = "rss"\nlanguage = "nl"\nwhy = "Invented."\n'
                    'permission = { file = "docs/permissions/2026-11-19-x.md", granted = 2026-11-19, '
                    f'max_sentences = 2, impact = true{extra} }}\n', encoding="utf-8")
    return path


def test_the_setting_is_optional_and_must_be_true_or_false(tmp_path):
    (source,) = load_sources(write_permission(tmp_path, ""))
    assert source.permission.newspaper is False
    (source,) = load_sources(write_permission(tmp_path, ", newspaper = true"))
    assert source.permission.newspaper is True
    with pytest.raises(ConfigError, match="newspaper must be true or false"):
        load_sources(write_permission(tmp_path, ', newspaper = "yes"'))


# --- the status box --------------------------------------------------------------------------------


def test_the_status_box_has_weather_rhine_and_strike_and_no_ships(tmp_path):
    html = part(paper(tmp_path, make_brief(status=STATUS)), '<aside class="paper-status"', "</aside>")
    keys = re.findall(r'data-key="(\w+)"', html)
    assert keys == ["weather", "rhine", "strike"]


def test_the_weather_box_keeps_every_meteoalarm_condition(tmp_path):
    box = part(paper(tmp_path, make_brief(status=STATUS)), '<aside class="paper-status"', "</aside>")
    text = text_of(box)
    assert METEOALARM_DISCLAIMER in text
    assert "KNMI via MeteoAlarm" in text and "Issued" in text and "not live" in text
    assert "not a MeteoAlarm or KNMI service" in text
    assert re.search(r'<a [^>]*href="https://www\.meteoalarm\.org"[^>]*>[^<]*[Ll]atest warnings', box)


# --- what both views share --------------------------------------------------------------------------


def test_corrections_failures_and_the_reduced_note_are_on_the_newspaper_page_too(tmp_path):
    brief = make_brief(items=[news(None, "Invented unrated story")],
                       corrections=[{"at": f"{DAY}T09:14:00+01:00", "note": "Invented correction note."}])
    brief["build"].update(failures=[{"source": "NL Times", "error": "HTTP 503"}], ai_unavailable=True)
    text = text_of(paper(tmp_path, brief))
    assert "Corrected 09:14" in text and "Invented correction note." in text
    assert "NL Times could not be reached today." in text
    assert "The AI step was unavailable" in text


def test_the_day_links_stay_in_the_newspaper_view(tmp_path):
    site = site_of(tmp_path, make_brief(day="2026-11-19"), make_brief(day=DAY))
    html = (site / "days" / f"{DAY}-newspaper.html").read_text(encoding="utf-8")
    nav = part(html, '<nav class="day-nav"', "</nav>")
    assert 'href="../days/2026-11-19-newspaper.html"' in nav and 'href="../archive.html"' in nav


def test_reading_order_is_lead_columns_status_then_notes(tmp_path):
    html = paper(tmp_path, make_brief(items=[news("high"), news("low", "Invented second")], status=STATUS))
    order = [html.index(marker) for marker in
             ('id="brief-title"', 'class="paper-lead', 'class="paper-columns"', 'class="paper-status"', 'id="build-title"')]
    assert order == sorted(order)


def test_headings_go_down_one_level_at_a_time(tmp_path):
    html = paper(tmp_path, make_brief(items=[news("high"), news("low", "Invented second")], status=STATUS))
    main = part(html, "<main", "</main>")
    levels = [int(n) for n in re.findall(r"<h([1-6])\b", main)]
    assert levels[0] == 1
    assert all(b <= a + 1 for a, b in zip(levels, levels[1:])), levels


def test_the_sample_note_is_on_sample_newspaper_pages(tmp_path):
    render.render_site(ROOT / "data" / "sample" / "briefs", tmp_path / "site")
    for page in [tmp_path / "site" / "newspaper.html", *(tmp_path / "site" / "days").glob("*-newspaper.html")]:
        assert "Sample data." in text_of(page.read_text(encoding="utf-8")), page.name


# --- the illustrations ------------------------------------------------------------------------------


ALLOWED_COLOURS = {"#0f2231", "#4b5e6d", "#0f6e8c", "#dbe7ed", "#ffffff", "#d6dee2", "#6f97ad", "#efebe3", "none"}
FLAG_COLOURS = {"#d7262e", "#f5c400", "#1c4fa0"}


def test_every_tag_has_an_illustration_and_there_is_a_general_one():
    tags = {tag.name for tag in load_tag_list()}
    assert set(render.ILLUSTRATIONS) == tags
    assert render.GENERAL_ILLUSTRATION
    files = {entry["file"] for entry in render.ILLUSTRATIONS.values()} | {render.GENERAL_ILLUSTRATION["file"]}
    assert len(files) == len(tags) + 1  # one drawing each, none shared
    assert {p.name for p in ILLUSTRATIONS.glob("*.svg")} == files


@pytest.mark.parametrize("svg", sorted(ILLUSTRATIONS.glob("*.svg")), ids=lambda p: p.name)
def test_each_illustration_is_a_small_safe_line_drawing_in_the_site_colours(svg):
    text = svg.read_text(encoding="utf-8")
    assert len(text.encode("utf-8")) <= 4096
    root = ET.fromstring(text)
    assert root.tag.endswith("svg") and root.get("viewBox") == "0 0 160 100"
    for bad in ("<script", "foreignObject", "href=", "url(", "@import", "<image", "<text"):
        assert bad not in text, bad
    colours = {c.lower() for c in re.findall(r'(?:fill|stroke)="([^"]+)"', text)}
    assert colours <= ALLOWED_COLOURS, colours - ALLOWED_COLOURS
    assert not colours & FLAG_COLOURS


def test_every_illustration_has_alt_text_that_says_it_is_an_illustration():
    for entry in [*render.ILLUSTRATIONS.values(), render.GENERAL_ILLUSTRATION]:
        assert entry["alt"].startswith("Illustration: ") and len(entry["alt"]) > 25


def test_an_item_gets_the_drawing_of_its_first_tag_that_has_one(tmp_path):
    item = news("high", "Invented lead story", affects=["Maasvlakte", "Rail", "Containers"])
    html = lead(paper(tmp_path, make_brief(items=[item])))
    img = re.search(r'<img [^>]*src="([^"]+)"[^>]*alt="([^"]+)"', html)
    assert img and img.group(1) == "../static/illustrations/" + render.ILLUSTRATIONS["Rail"]["file"]
    assert img.group(2) == render.ILLUSTRATIONS["Rail"]["alt"]
    assert re.search(r"<figcaption[^>]*>\s*Illustration\s*</figcaption>", html)


def test_an_item_without_a_tag_drawing_gets_the_general_one(tmp_path):
    html = lead(paper(tmp_path, make_brief(items=[news("high", affects=["Maasvlakte"])])))
    assert render.GENERAL_ILLUSTRATION["file"] in html


# --- the layout ---------------------------------------------------------------------------------------


def wide_block():
    blocks = re.findall(r"@media \(min-width: 64rem\) \{(.*?)\n\}", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S), re.S)
    return "\n".join(blocks)


def test_wide_screens_put_the_status_box_beside_the_news_and_the_items_in_columns():
    wide = wide_block()
    assert re.search(r"\.paper-grid \{[^}]*grid-template-columns:", wide)
    assert re.search(r"\.paper-columns \{[^}]*grid-template-columns:", wide)


def test_phones_get_one_column_in_page_order():
    outside = re.sub(r"@media [^{]+\{.*?\n\}", "", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S), flags=re.S)
    for selector in (".paper-grid", ".paper-columns"):
        for body in re.findall(re.escape(selector) + r" \{([^}]*)\}", outside):
            assert "grid-template-columns" not in body and "order:" not in body


def test_the_switch_is_part_of_the_button_set_and_shows_which_view_is_on():
    assert re.search(r'\.btn\[aria-pressed="true"\],\s*\.btn\[aria-current="page"\] \{', CSS)
    for sel, body in re.findall(r"([^{}]*\.view-switch[^{}]*)\{([^}]*)\}", CSS):
        for prop in ("border-radius", "min-height", "height", "font-size", "font-weight", "font-family", "border"):
            assert not re.search(rf"(^|[;\s]){prop}\s*:", body), f"{sel} sets {prop}"


def test_flag_colours_stay_out_of_the_newspaper_styles():
    for sel, body in re.findall(r"([^{}]*\.paper[^{}]*)\{([^}]*)\}", CSS):
        assert "--flag-" not in body, sel


# --- the speed run checks the newspaper page ------------------------------------------------------------


def test_the_speed_run_measures_the_newspaper_page():
    measure = (ROOT / "tools" / "measure_speed.mjs").read_text(encoding="utf-8")
    assert 'newspaper: "newspaper.html"' in measure
    assert ".paper-headline" in measure and ".paper-status" in measure  # "news and status visible"
    workflow = (ROOT / ".github" / "workflows" / "speed.yml").read_text(encoding="utf-8")
    assert re.search(r"PAGES: [\w,-]*\bnewspaper\b", workflow)
    compare = (ROOT / "tools" / "speed_compare.mjs").read_text(encoding="utf-8")
    assert "Map files requested" in compare


def test_the_committed_drawings_are_what_the_script_draws():
    import importlib.util
    spec = importlib.util.spec_from_file_location("draw_illustrations", ROOT / "tools" / "draw_illustrations.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert set(tool.DRAWINGS) == {p.name for p in ILLUSTRATIONS.glob("*.svg")}
    for name in tool.DRAWINGS:
        committed = (ILLUSTRATIONS / name).read_bytes().decode("utf-8").replace("\r\n", "\n")  # git may add CRs on Windows
        assert committed == tool.svg(name), name
