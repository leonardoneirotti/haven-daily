"""Site speed, part 1 (issue #104; measurements in docs/site-speed.md).

The text, news and status come first and the chart after them: the 238 KB basemap is
loaded by map.js once the page has painted, so the page no longer waits for it.
The High marker's ping plays three times and stops. The pages show no character that
would pull in an extra font file, and the font files stay within a budget (preloading the
fonts was tried and made the first text later; see below). Moving the chart does less work on every move.

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
    """The map pages: Today and each day's page. A day's newspaper page (#101) has no map, so it falls
    under the pages that never fetch the basemap (test_other_pages_do_not_fetch_the_basemap)."""
    return [p for p in pages(site) if (p.name == "index.html" or p.parent.name == "days")
            and not p.name.endswith("-newspaper.html")]


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

def test_fonts_are_not_preloaded(site):
    # Tried and measured (speed run 44407583387, throttled phone): preloading the four
    # first-screen fonts (about 80 KB) made the first text later, 0.60 -> 0.94 s on Today and
    # 0.46 -> 0.73 s on the archive. On a slow connection they hold up the stylesheet, and the
    # page can't paint before it. With font-display: swap the text shows at once anyway.
    for page in pages(site):
        links = [link for link in soup_of(page).find_all("link") if "preload" in link.get("rel", [])]
        assert not [link for link in links if link.get("as") == "font"], page.relative_to(site)


def test_day_pages_fetch_the_basemap_ahead_of_the_fonts(site):
    # Owner, option 3 (19 Nov 2026): the map came 0.2-0.4 s after the 2.5 s target because the
    # basemap downloaded alongside the fonts. Asked for in <head> with high priority, it starts
    # before the fonts, which the browser finds only once the stylesheet is in. It still runs
    # after the first paint: map-loader.js adds the script, which takes the downloaded file.
    for page in day_pages(site):
        links = [link for link in soup_of(page).find_all("link") if "preload" in link.get("rel", [])]
        assert len(links) == 1, page.name
        link = links[0]
        assert link["href"].endswith("static/basemap.js") and link["as"] == "script"
        assert link.get("fetchpriority") == "high"
        assert not link.has_attr("crossorigin"), "must match the script tag map-loader.js adds, or it is fetched twice"
        assert (page.parent / link["href"]).resolve().is_file()


def test_other_pages_do_not_fetch_the_basemap(site):
    for page in pages(site):
        if page not in day_pages(site):
            assert "basemap.js" not in page.read_text(encoding="utf-8"), page.relative_to(site)


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
