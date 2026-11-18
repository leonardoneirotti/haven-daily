"""Site speed, part 1 (issue #104; measurements in docs/site-speed.md).

The text, news and status come first and the chart after them: the 238 KB basemap is
loaded by map.js once the page has painted, so the page no longer waits for it.
The High marker's ping plays three times and stops. The first-screen fonts are loaded
early, the pages show no character that would pull in an extra font file, and the font
files stay within a budget. Moving the chart does less work on every move.

map.js can't run here (it needs Leaflet and a browser), so its parts are checked by
reading it; tools/measure_speed.mjs measures the result in a real browser (speed.yml).
"""

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from haven import render
from test_fonts import font_faces

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
SAMPLE_BRIEFS = ROOT / "data" / "sample" / "briefs"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
MAP_JS = (STATIC / "map.js").read_text(encoding="utf-8")
LOADER_JS = (STATIC / "map-loader.js").read_text(encoding="utf-8")

# The first-screen fonts (measured on Today, the archive and How it works, phone and laptop):
# Plex Sans (one variable file), Condensed 700 for the titles and Mono 600, which the
# labels set at weight 700 use (the nearest file). Day pages add Mono 500 (the dates).
PRELOAD_EVERY_PAGE = ["ibm-plex-sans-400-700-latin.woff2", "ibm-plex-sans-condensed-700-latin.woff2",
                      "ibm-plex-mono-600-latin.woff2"]
PRELOAD_DAY_PAGES = PRELOAD_EVERY_PAGE + ["ibm-plex-mono-500-latin.woff2"]

# The font budget (owner, 18 Nov 2026): every font file a page can load, in the main
# (latin) set, at most this much together. The style pass (#102) must stay within it.
FONT_BUDGET_BYTES = 240 * 1024
FONT_BUDGET_FILES = 11


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    render.render_site(SAMPLE_BRIEFS, out)
    return out


def pages(site):
    return sorted(site.rglob("*.html"))


def day_pages(site):
    return [p for p in pages(site) if p.name == "index.html" or p.parent.name == "days"]


def soup_of(path):
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


# ---------- 1. Text first, the chart after ----------

def test_day_pages_do_not_load_the_basemap_or_the_chart_with_a_script_tag(site):
    # A <script src="basemap.js"> held up the page until 238 KB had arrived and run.
    for page in day_pages(site):
        sources = [s.get("src", "") for s in soup_of(page).find_all("script")]
        assert not any(src.endswith(("basemap.js", "/map.js")) for src in sources), page.name


def test_the_chart_scripts_wait_until_the_page_is_read_and_keep_their_order(site):
    # Deferred scripts run in the order they appear: Leaflet, pins.js, then the loader.
    for page in day_pages(site):
        sources = [s["src"] for s in soup_of(page).find_all("script", src=True) if s.has_attr("defer")]
        names = [src.rsplit("/", 1)[-1] for src in sources]
        assert names == ["leaflet.js", "pins.js", "map-loader.js"], page.name


def test_the_loader_adds_the_basemap_then_the_chart_after_the_page_has_painted():
    # After the next frame, from the folder the loader itself came from (no other site, rule 14).
    assert "requestAnimationFrame" in LOADER_JS
    assert "document.currentScript" in LOADER_JS
    assert LOADER_JS.index('"basemap.js"') < LOADER_JS.index('"map.js"')
    # Added scripts normally run in whatever order they arrive; async = false keeps basemap first.
    assert "async = false" in LOADER_JS
    assert not re.search(r"https?://", LOADER_JS)


def test_a_quiet_loading_note_stands_in_for_the_chart(site):
    for page in day_pages(site):
        note = soup_of(page).find(id="chart-loading")
        assert note is not None, page.name
        assert note.get_text(strip=True) == "Loading chart…"
        # Shown only while the chart is on its way: with JavaScript and before the chart is drawn.
        assert "needs-map" in note["class"]
        assert note.has_attr("aria-hidden"), "the chart's own label already describes it to screen readers"
    assert re.search(r"\.chart-loading\s*\{", CSS)
    assert "chart-loading" in LOADER_JS


def test_if_the_chart_fails_to_load_the_page_falls_back_to_the_text():
    # No basemap or no map.js: the chart's controls and the note go, the plain-text stand-ins show.
    assert "onerror" in LOADER_JS
    assert re.search(r'classList\.remove\("has-map"\)', LOADER_JS)


# ---------- 4. The ping plays three times, then stops ----------

def test_the_high_marker_ping_is_not_endless():
    rule = re.search(r"\.callout-item\.sev-high \.num::after\s*\{([^}]*)\}", CSS).group(1)
    animation = re.search(r"animation:\s*([^;]+);", rule).group(1)
    assert "infinite" not in animation
    assert re.search(r"\bping\b", animation) and re.search(r"\b3\b", animation), animation


def test_the_ping_does_not_start_again_when_markers_are_rebuilt():
    # Markers are rebuilt after a move; once the three pings are over, they stay still.
    assert re.search(r"\.ping-done \.callout-item\.sev-high \.num::after\s*\{[^}]*animation:\s*none", CSS)
    assert "ping-done" in MAP_JS


def test_no_ping_with_reduced_motion():
    motion = CSS[CSS.index("@media (prefers-reduced-motion: reduce)"):]
    assert re.search(r"\*::after\s*\{[^}]*animation:\s*none !important", motion)


# ---------- 5. Fonts ----------

def preloads(page):
    return [link for link in soup_of(page).find_all("link") if "preload" in link.get("rel", [])]


def test_first_screen_fonts_are_preloaded(site):
    for page in pages(site):
        wanted = PRELOAD_DAY_PAGES if page in day_pages(site) else PRELOAD_EVERY_PAGE
        links = preloads(page)
        names = [link["href"].rsplit("/", 1)[-1] for link in links]
        assert names == wanted, page.relative_to(site)
        for link in links:
            # Without crossorigin the browser fetches the font twice.
            assert link["as"] == "font" and link["type"] == "font/woff2" and link.has_attr("crossorigin")
            assert (page.parent / link["href"]).resolve().is_file(), link["href"]


def test_preloads_come_before_the_stylesheet(site):
    for page in pages(site):
        html = page.read_text(encoding="utf-8")
        assert html.index('rel="preload"') < html.index("style.css"), page.name


def test_preloaded_fonts_are_the_ones_style_css_uses():
    used = {url.rsplit("/", 1)[-1] for face in font_faces(CSS) for url in face["urls"]}
    assert set(PRELOAD_DAY_PAGES) <= used


def test_pages_show_no_character_that_pulls_in_an_extra_font_file(site):
    # The latin-ext files are loaded only for letters such as ł, ő or ș. Our own text never
    # needs them (a headline from a source may, and then the browser loads the file).
    extra = [r for face in font_faces(CSS) if any(u.endswith("-latin-ext.woff2") for u in face["urls"])
             for r in face["ranges"]]
    main = [r for face in font_faces(CSS) if any(u.endswith("-latin.woff2") for u in face["urls"])
            for r in face["ranges"]]
    for page in pages(site):
        soup = soup_of(page)
        for tag in soup(["script", "style"]):
            tag.decompose()
        for char in set(soup.get_text()):
            code = ord(char)
            if any(a <= code <= b for a, b in main):
                continue
            assert not any(a <= code <= b for a, b in extra), \
                f"{page.relative_to(site)}: {char!r} (U+{code:04X}) loads a latin-ext font file"


def test_the_font_files_stay_within_the_budget():
    files = {url for face in font_faces(CSS) for url in face["urls"] if url.endswith("-latin.woff2")}
    size = sum((STATIC / url).stat().st_size for url in files)
    assert len(files) <= FONT_BUDGET_FILES, f"{len(files)} font files, budget {FONT_BUDGET_FILES}"
    assert size <= FONT_BUDGET_BYTES, f"{size / 1024:.0f} KB of fonts, budget {FONT_BUDGET_BYTES / 1024:.0f} KB"


# ---------- 6. Less work on every move ----------

def test_the_scale_bar_updates_only_when_a_move_ends():
    scale = re.search(r"L\.control\.scale\(\{([^}]*)\}\)", MAP_JS).group(1)
    assert re.search(r"updateWhenIdle:\s*true", scale)


def test_colours_are_read_once_not_on_every_repaint():
    paint = MAP_JS[MAP_JS.index("function paint(ctx)"):]
    paint = paint[:paint.index("\n  }\n")]
    assert "token(" not in paint and "getComputedStyle" not in paint


def test_callouts_are_measured_again_only_once_the_fonts_are_ready():
    # "loadingdone" fires for every font that arrives; each made the chart measure all markers.
    assert "loadingdone" not in MAP_JS
    assert "document.fonts.ready" in MAP_JS
