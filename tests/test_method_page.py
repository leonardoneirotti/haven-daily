"""Method page for the real pipeline (spec §2.2, §2.3 item 4, §3, §4, §12; issue #24).

The page must say how the site really works: automatic and unreviewed, corrected
afterwards. Thresholds cite their public source, the source list comes from
config/sources.toml (no hand-copied list to drift), the Rhine numbers come from
config/rhine.toml, the AI models from the code that calls them, MeteoAlarm's
disclaimer is verbatim and the footer is exact on every page.
"""

import html as html_lib
import re
import textwrap
from pathlib import Path

import pytest

from haven import filter as haven_filter
from haven import render, summarise
from haven.config import RhineThresholds, Source, load_rhine, load_sources

PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_BRIEFS = PROJECT_DIR / "data" / "sample" / "briefs"

FOOTER = (
    "Personal, unofficial project by Leonardo Neirotti. Not affiliated with the Port of Rotterdam "
    "Authority. AI-generated summaries — always check the original source."
)
METEOALARM_DISCLAIMER = (
    "Time delays between this website and the www.meteoalarm.org website are possible. For the most "
    "up-to-date awareness information as published by the participating National Meteorological and "
    "Hydrological Services, please refer to www.meteoalarm.org."
)
CONTARGO_LWS = "https://www.contargo.net/en/goodtoknow/lws"
MAERSK_LWS = "https://www.maersk.com/news/articles/2026/07/09/rhine-river-low-water-surcharge"


# --- helpers -------------------------------------------------------------------------------


def text_of(page: str) -> str:
    """The page as a reader sees it: no tags, entities decoded, whitespace collapsed."""
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def section(page: str, heading_id: str) -> str:
    """The HTML of one <section> of the Method page, found by its heading id."""
    match = re.search(rf'<section aria-labelledby="{heading_id}">(.*?)</section>', page, re.S)
    assert match, f"no section {heading_id!r}"
    return match.group(1)


def render_method(sources=None, rhine=None) -> str:
    env = render.make_environment()
    method = render.method_page(sources if sources is not None else load_sources(),
                                rhine if rhine is not None else load_rhine())
    return env.get_template("about.html").render(root="", active="method", sample=False, method=method)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    render.render_site(SAMPLE_BRIEFS, out)
    return out


@pytest.fixture(scope="module")
def about(site):
    return (site / "about.html").read_text(encoding="utf-8")


def source(id, verdict, **fields):
    defaults = {"urls": (f"https://example.org/{id}/feed",), "access": "rss", "language": "en",
                "home": f"https://example.org/{id}"}
    if verdict == "drop":
        defaults = {}
    return Source(id=id, name=fields.pop("name", id.title()), verdict=verdict, **{**defaults, **fields})


# --- footer and MeteoAlarm: exact text ---------------------------------------------------------


def test_footer_text_is_exact_on_every_page(site):
    pages = [site / "index.html", site / "archive.html", site / "about.html", *sorted((site / "days").glob("*.html"))]
    assert len(pages) == 3 + 4
    for page in pages:
        assert FOOTER in text_of(page.read_text(encoding="utf-8")), page.name


def test_meteoalarm_disclaimer_is_verbatim_with_knmi_and_a_link(about):
    weather = section(about, "weather")
    assert METEOALARM_DISCLAIMER in text_of(weather)
    assert 'href="https://www.meteoalarm.org"' in weather
    assert "KNMI" in text_of(weather)
    # The other MeteoAlarm requirements (spec §2.2) are explained too.
    assert "time of issue" in text_of(weather).lower()
    assert "not live" in text_of(weather)


# --- thresholds: from config, each with its public source -----------------------------------------


def test_rhine_thresholds_come_from_config(about):
    rhine = load_rhine()
    row = text_of(re.search(r'<tr id="threshold-rhine">.*?</tr>', about, re.S).group(0))
    assert f"{rhine.watch_at_or_below + 1}–{rhine.watch_above} cm" in row
    assert f"{rhine.watch_at_or_below} cm or below" in row
    assert f"above {rhine.watch_above} cm" in row
    assert f"{rhine.alert_at_or_below} cm or below" in row
    assert f"above {rhine.alert_above} cm" in row


def test_changing_the_config_changes_the_page():
    page = render_method(rhine=RhineThresholds(alert_at_or_below=70, watch_at_or_below=140,
                                               watch_above=470, alert_above=650))
    row = text_of(re.search(r'<tr id="threshold-rhine">.*?</tr>', page, re.S).group(0))
    assert "141–470 cm" in row and "140 cm or below" in row and "70 cm or below" in row
    assert "150 cm" not in row


def test_every_threshold_row_cites_its_source(about):
    rows = dict(re.findall(r'<tr id="threshold-(\w+)">(.*?)</tr>', about, re.S))
    assert set(rows) == {"weather", "rhine", "strike"}
    assert 'href="https://www.meteoalarm.org"' in rows["weather"]
    for url in (CONTARGO_LWS, MAERSK_LWS, render.PEGELONLINE_KAUB_URL):
        assert f'href="{url}"' in rows["rhine"]
    assert "kept items of the last 14 days" in text_of(rows["strike"]).lower()
    assert 'href="#strike"' in rows["strike"]  # how the strike flag works, further down the page


def test_no_draft_thresholds_are_left(about):
    text = text_of(about)
    assert "Draft" not in text
    assert "to be set" not in text
    assert "today's items" not in text.lower()  # the strike flag reads 14 days, not today's items (#21)


# --- sources: generated from config -----------------------------------------------------------------


def test_every_used_and_headline_only_source_from_config_is_listed(about):
    listed = section(about, "sources")
    for src in load_sources():
        if src.verdict != "drop":
            assert src.name in text_of(listed), src.id
            assert source_links(listed, src.name) == (src.home, src.urls[0]), src.id


def source_links(page: str, name: str) -> tuple[str, str]:
    """The link on a source's name and its "(feed)" link, from one line of the source list
    (owner, 2 Nov 2026, PR #76)."""
    line = re.search(rf'<li>\s*<strong><a href="([^"]+)">{re.escape(html_lib.escape(name))}</a></strong>(.*?)</li>',
                     page, re.S)
    assert line, f"no linked line for {name!r}"
    feed = re.search(r'\(<a href="([^"]+)">feed</a>\)', line.group(2))
    assert feed, f"no (feed) link for {name!r}"
    return line.group(1), feed.group(1)


def test_the_name_links_the_public_page_and_feed_links_what_the_job_reads():
    sources = (source("checked", "use", home="https://example.org/", urls=("https://example.org/rss.xml",)),
               source("head", "headline-only", why="Paywalled.", home="https://news.example/",
                      urls=("https://news.example/tag/port", "https://news.example/feed")))
    page = section(render_method(sources=sources), "sources")
    assert source_links(page, "Checked") == ("https://example.org/", "https://example.org/rss.xml")
    assert source_links(page, "Head") == ("https://news.example/", "https://news.example/tag/port")


def test_dropped_sources_have_no_links():
    page = section(render_method(sources=(source("c-drop", "drop", why="No public feed."),)), "sources")
    assert "<a " not in re.search(r'id="sources-drop">(.*?)</div>', page, re.S).group(1)


def test_sources_are_grouped_by_verdict():
    sources = (source("a-use", "use"), source("b-head", "headline-only", why="Blocks AI crawlers."),
               source("c-drop", "drop", why="robots.txt disallows the feed."))
    page = render_method(sources=sources)
    groups = dict(re.findall(r'<div class="source-group" id="sources-([\w-]+)">(.*?)</div>', page, re.S))
    assert "A-Use" in text_of(groups["use"])
    assert "B-Head" in text_of(groups["headline-only"])
    assert "C-Drop" in text_of(groups["drop"])
    assert "B-Head" not in text_of(groups["use"]) and "C-Drop" not in text_of(groups["use"])


def test_a_source_added_to_config_shows_up_without_touching_the_template():
    sources = (*load_sources(), source("invented-port-news", "use", name="Invented Port News"))
    assert "Invented Port News" in text_of(render_method(sources=sources))


def test_headline_only_and_dropped_sources_show_why():
    sources = (source("b-head", "headline-only", why="Its terms allow links only."),
               source("c-drop", "drop", why="No public feed."))
    text = text_of(render_method(sources=sources))
    assert "Its terms allow links only." in text
    assert "No public feed." in text


def test_sentences_in_the_source_list_are_separated_by_a_space(about):
    # Jinja's trim_blocks once glued "how" and "why" together: "...to an AI.Its robots.txt..."
    assert not re.search(r"[a-z)]\.[A-Z]", text_of(section(about, "sources")))


def test_how_each_source_is_used_follows_its_config():
    sources = (source("auto", "use", auto_keep=True), source("checked", "use"),
               source("head", "headline-only", why="Paywalled."))
    method = render.method_page(sources, load_rhine())
    how = {s["name"]: s["how"] for group in method["source_groups"] for s in group["sources"]}
    assert "skip" in how["Auto"].lower() and "AI relevance check" in how["Auto"]
    assert "AI relevance check" in how["Checked"] and "skip" not in how["Checked"].lower()
    assert "headline" in how["Head"].lower()


def test_notes_for_people_never_reach_the_page():
    # `note` is for people reading the config; only `why` is public.
    sources = (source("checked", "use", note="Internal: the old feed is stale."),)
    assert "Internal" not in text_of(render_method(sources=sources))


def test_the_ai_opt_out_rule_is_explained(about):
    text = text_of(section(about, "sources"))
    assert "article text never goes to an AI" in text


# --- the AI models: named from the code that calls them ---------------------------------------------


def test_the_ai_models_are_named_from_the_code(about):
    text = text_of(section(about, "models"))
    assert render.MODEL_NAMES[haven_filter.AI_MODEL] in text
    assert render.MODEL_NAMES[summarise.SUMMARY_MODEL] in text
    assert render.MODEL_NAMES[summarise.FALLBACK_MODEL] in text
    assert "20 minutes" in text


def test_an_unknown_model_id_stops_the_build(monkeypatch):
    monkeypatch.setattr(summarise, "SUMMARY_MODEL", "claude-invented-9")
    with pytest.raises(KeyError):
        render.method_page(load_sources(), load_rhine())


# --- nothing official, nothing reviewed ---------------------------------------------------------------


def test_nothing_suggests_the_page_is_official_or_reviewed(about):
    text = text_of(about)
    for word in ("official", "officially", "reviewed", "approved", "verified", "endorsed", "partner"):
        assert not re.search(rf"\b{word}\b", text, re.I), word
    assert "Nobody checks a brief before it goes online" in text
    assert "not affiliated with the port of rotterdam authority" in text.lower()
    assert "portofrotterdam.com/" not in re.sub(r'href="[^"]*"', "", about)  # no images or logos from them


# --- copyright, severity, chart, credits -------------------------------------------------------------------


def test_the_no_article_text_rule_is_stated(about):
    text = text_of(section(about, "copyright"))
    assert "No article text is stored" in text
    assert "Translated articles are never stored or republished" in text


def test_severity_rules_follow_the_spec(about):
    text = text_of(section(about, "severity"))
    assert "already over" in text  # Low, spec §2.1 (#67)
    assert "rated from headline only" in text  # spec §2.1
    assert "Not enough information" in text


def test_the_chart_says_lines_are_decoration_and_ships_are_not_collected_yet(about):
    text = text_of(section(about, "chart"))
    assert "decoration" in text and "not depth contours" in text
    assert "Ship positions are not collected yet" in text
    assert "ship positions" not in text_of(section(about, "steps")).lower()


def test_once_the_ais_snapshot_is_built_the_chart_explains_it(monkeypatch):
    monkeypatch.setattr(render, "AIS_SNAPSHOT_BUILT", True)
    text = text_of(section(render_method(), "chart"))
    assert "Ship positions are not collected yet" not in text
    assert "AIS snapshot" in text


CREDITS = ("KNMI", "MeteoAlarm", "WSV", "PEGELONLINE", "DL-DE→Zero-2.0", "Rijkswaterstaat", "CC0",
           "OpenStreetMap", "ODbL", "Leaflet", "BSD-2", "Lucide", "ISC", "IBM Plex", "SIL Open Font License",
           "Shapely", "Jinja2", "Beautiful Soup", "soupsieve", "Anthropic Python SDK")


def test_credits_follow_spec_section_12(about):
    text = text_of(section(about, "credits"))
    for credit in CREDITS:
        assert credit in text, credit


def test_who_makes_this(about):
    text = text_of(section(about, "maker"))
    assert "Leonardo Neirotti" in text
    assert "portfolio project" in text
