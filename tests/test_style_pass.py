"""The visual style pass (#102): direction A, "Harbour Light", picked by the owner on 20 Nov 2026.

Only the look changes (spec §7): colours, fonts, spacing, cards, buttons and how the chart is
drawn. The pages, chart, panel and dials stay as they are, so every other test still holds.
What is checked here:

- the Harbour Light colours, and every text colour readable on its background (WCAG AA);
- colour carries meaning only: the blue accent marks what you can press or have selected, and
  nothing else; the "Whole port" button is no longer orange;
- one button set: every button and button-like link shares one rule (size, corners, border, type);
- type: Manrope for text and headlines, Plex Mono only for data, Plex Serif only for the impact
  (and water names on the chart): no more spaced monospace capitals for six jobs;
- the header: visible on load, slides away when scrolling down, comes back when scrolling up,
  with the cursor at the top of the screen or with keyboard focus; no browser storage;
- the critique's "crowded" and "inconsistent" points (design/style-pass/README.md).

map.js and site.js can't run here, so their parts are checked by reading them; the header was
also checked in headless Edge on a phone and a laptop screen (PR for #102).
"""

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from haven import render
from test_first_screen import css_rules
from test_fonts import font_faces

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
RULES = css_rules(CSS)
MAP_JS = (STATIC / "map.js").read_text(encoding="utf-8")
SITE_JS = (STATIC / "site.js").read_text(encoding="utf-8")
SAMPLE_BRIEFS = ROOT / "data" / "sample" / "briefs"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    render.render_site(SAMPLE_BRIEFS, out)
    return out


def pages(site):
    return sorted(site.rglob("*.html"))


def soup_of(path):
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def tokens():
    """The #rrggbb tokens of the first :root block."""
    root = CSS[CSS.index(":root {"):]
    root = root[:root.index("}")]
    return {name: value.lower() for name, value in re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b", root)}


def bodies(selector):
    """Bodies of every rule whose selector list includes `selector` exactly."""
    return [body for sel, body in RULES if selector in [s.strip() for s in sel.split(",")]]


def luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ---------- The palette ----------

HARBOUR_LIGHT = {
    "bg": "#f3f5f4", "surface": "#ffffff", "ink": "#0f2231", "ink-2": "#4b5e6d",
    "water": "#dbe7ed", "land": "#efebe3", "ship": "#0f8a7c", "accent": "#0f6e8c",
    "high": "#c8321e", "medium": "#eaa419", "low": "#5d7186", "overprint": "#8a3a6c",
}


def test_the_tokens_are_harbour_light():
    found = tokens()
    for name, value in HARBOUR_LIGHT.items():
        assert found.get(name) == value, f"--{name} is {found.get(name)}, Harbour Light has {value}"
    assert re.search(r"color-scheme:\s*light", CSS[CSS.index(":root {"):])


# Text colour on background: every pair the pages use, at least 4.5:1 (WCAG AA, normal text).
TEXT_PAIRS = [
    (fg, bg) for fg in ("ink", "ink-2", "high-ink", "medium-ink", "low-ink", "ok-ink", "nodata-ink",
                        "overprint", "accent")
    for bg in ("bg", "surface", "surface-2")
] + [
    ("on-high", "high"), ("on-medium", "medium"), ("on-low", "low"), ("on-accent", "accent"),
    ("water-label", "water"), ("land-label", "land"), ("ink", "water"), ("ink", "land"),
]


@pytest.mark.parametrize("fg, bg", TEXT_PAIRS)
def test_text_is_readable_on_its_background(fg, bg):
    found = tokens()
    ratio = contrast(found[fg], found[bg])
    assert ratio >= 4.5, f"--{fg} on --{bg}: {ratio:.2f}:1, needs 4.5:1"


@pytest.mark.parametrize("bg", ["surface", "bg", "water", "land"])
def test_a_button_edge_stands_out_from_what_is_around_it(bg):
    # WCAG 1.4.11: the edge that shows where a control is, at least 3:1 (white buttons on the chart).
    found = tokens()
    assert contrast(found["edge"], found[bg]) >= 3, f"--edge on --{bg}"


# ---------- Colour carries meaning only ----------

def test_no_orange_and_no_peach_left():
    found = tokens()
    assert "cta" not in found and "on-cta" not in found, "the peach popup button is gone"
    assert "--cta" not in CSS and "#ff801d" not in CSS.lower()


SELECTED = ('[aria-pressed="true"]', '[aria-current="page"]', ".is-active", ":focus-visible", ":focus")


def test_the_accent_only_marks_what_is_selected_or_can_be_pressed():
    # The accent fills or underlines a control only in its selected/pressed state (and colours
    # links and focus rings); it is never a decoration and never stands next to a severity.
    for sel, body in RULES:
        if re.search(r"(background|box-shadow|border(-\w+)?)\s*:[^;]*var\(--accent\)", body):
            for part in sel.split(","):
                assert any(state in part for state in SELECTED), f"{part.strip()} uses the accent"


def test_the_whole_port_button_is_a_normal_button():
    # It was the only filled orange button, beside amber "Medium" squares, and read like a severity.
    for sel, body in RULES:
        if ".chart-home" in sel:
            assert not re.search(r"var\(--(accent|high|medium|low)\b", body), sel
    assert 'L.DomUtil.create("button", "btn chart-home")' in MAP_JS


# ---------- One button set ----------

BUTTON_LIKE = [".chart-button", ".chart-home", ".chart-filter button", ".chart-focus button", ".pop-news",
               ".item-actions a", ".leaflet-container .leaflet-bar a"]
SHAPE = ("border-radius", "min-height", "height", "font-size", "font-weight", "font-family", "border")


def test_one_rule_shapes_every_button():
    shared = [sel for sel, body in RULES if ".btn" in [s.strip() for s in sel.split(",")]
              and re.search(r"border-radius", body) and re.search(r"min-height", body)]
    assert shared, "no shared .btn rule"
    assert ".leaflet-container .leaflet-bar a" in [s.strip() for s in shared[0].split(",")], \
        "Leaflet's zoom buttons are made by Leaflet, so the shared rule names them too"


@pytest.mark.parametrize("selector", BUTTON_LIKE)
def test_no_button_has_its_own_shape(selector):
    # Size, corners, border and type come from the shared rule only; a button's own rules may set
    # its layout and its pressed/selected colours, nothing that makes it look like another set.
    for sel, body in RULES:
        if selector in [s.strip() for s in sel.split(",")] and ".btn" not in sel:
            for prop in SHAPE:
                assert not re.search(rf"(^|[;\s]){prop}\s*:", body), f"{sel} sets its own {prop}"


def test_every_button_and_action_link_on_the_pages_is_in_the_set(site):
    for page in pages(site):
        soup = soup_of(page)
        for button in soup.find_all("button"):
            classes = button.get("class", [])
            if "link-button" in classes:  # a name or count in running text: styled as a link
                continue
            assert "btn" in classes, f"{page.name}: {button}"
        for link in soup.select(".item-actions a"):
            assert "btn" in link.get("class", []), f"{page.name}: {link}"


def test_the_buttons_made_by_the_chart_are_in_the_set():
    assert 'class="btn pop-news' in MAP_JS


def test_text_buttons_look_like_links():
    # "12 at anchor" and the ship names: buttons in running text, styled exactly as a link.
    body = " ".join(bodies(".link-button"))
    assert re.search(r"text-decoration:\s*underline", body)
    assert not re.search(r"border-radius|min-height", body)


# ---------- Type ----------

def test_mono_is_for_data_only():
    # Spaced monospace capitals did six jobs (brand, kickers, severity words, the date, land
    # names, table headers) and made the site feel like an early-2020s dashboard (critique 2).
    for selector in (".brand-name", ".kicker", ".sev", ".panel-head h1", ".chart-label-land span",
                     "thead th", ".impact-label", ".source-group h3", ".chart-loading"):
        for body in bodies(selector):
            assert "--font-mono" not in body, selector


def test_the_brand_is_a_name_not_a_code():
    body = " ".join(bodies(".brand-name"))
    assert "uppercase" not in body
    assert re.search(r"font-weight:\s*800", body)


def test_serif_is_for_interpretation_and_water_names_only():
    allowed = {".impact-text", ".impact-label em", ".chart-label-water span"}
    for sel, body in RULES:
        if "--font-serif" in body and not sel.startswith(":root"):
            assert {s.strip() for s in sel.split(",")} <= allowed, sel


def test_the_fonts_are_halved_to_bring_the_map_in_sooner():
    # Up to 192 KB of fonts in 9 files shared the slow phone connection with the basemap
    # (docs/site-speed.md, part 2). Harbour Light needs four Latin files: Manrope (one variable
    # file), Plex Mono 400, Plex Serif 400 and its italic.
    files = {url for face in font_faces(CSS) for url in face["urls"] if url.endswith("-latin.woff2")}
    size = sum((STATIC / url).stat().st_size for url in files)
    assert len(files) <= 4, sorted(files)
    assert size <= 100 * 1024, f"{size / 1024:.0f} KB"


# ---------- The header ----------

def test_the_header_holds_the_brand_and_the_navigation_only(site):
    for page in pages(site):
        header = soup_of(page).find("header", class_="topbar")
        assert header.find(class_="brand") and header.find("nav", class_="site-nav"), page.name
        assert not header.find(class_="tagline") and not header.find(class_="sample-note"), page.name


def test_the_one_liner_and_the_sample_note_follow_right_under_it(site):
    for page in pages(site):
        header = soup_of(page).find("header", class_="topbar")
        masthead = header.find_next_sibling()
        assert "masthead" in masthead.get("class", []), page.name
        assert masthead.find("p", class_="tagline").get_text(strip=True) == render.SITE["tagline"]
        assert masthead.find("p", class_="sample-note"), f"{page.name}: sample site, so marked (rule 10)"


def test_with_javascript_the_header_stays_at_the_top_without_it_it_scrolls_away():
    sticky = [sel for sel, body in RULES if re.search(r"position:\s*sticky", body) and "topbar" in sel]
    assert sticky and all(sel.startswith("html.js") or ".js " in sel for sel in sticky), sticky


def test_the_header_slides_away_and_comes_back():
    hidden = " ".join(bodies(".topbar.is-hidden"))
    assert re.search(r"transform:\s*translateY\(-100%\)", hidden)
    # Keyboard focus inside it always brings it back, also before the script reacts.
    assert re.search(r"transform:\s*none", " ".join(bodies(".topbar:focus-within")))
    assert re.search(r"transition:[^;]*transform", " ".join(bodies("html.js .topbar")))


def test_the_script_hides_it_going_down_and_shows_it_going_up_near_the_top_or_on_focus():
    # passive: the listener never holds up scrolling on a phone
    assert re.search(r'addEventListener\("scroll", function.*?\}, \{ passive: true \}\);', SITE_JS, re.S)
    assert re.search(r'addEventListener\("mousemove"', SITE_JS)  # the cursor at the top of the screen
    assert re.search(r'addEventListener\("focusin"', SITE_JS)
    assert "is-hidden" in SITE_JS
    for storage in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
        assert storage not in SITE_JS


def test_the_chart_and_the_items_are_not_hidden_under_the_header_when_scrolled_to():
    # map.js scrolls up to the chart (and the header comes back), and to an item.
    for selector in (".chart", ".item"):
        assert any(re.search(r"scroll-margin-top:[^;]*--topbar-h", body) for body in bodies(selector)), selector


# ---------- Crowded (critique 6, 7, 8, 9) ----------

def rem(value):
    found = re.match(r"\s*([\d.]+)rem", value)
    return float(found.group(1)) if found else None


def font_sizes(selector):
    return [rem(m) for body in bodies(selector) for m in re.findall(r"font-size:\s*([^;]+)", body) if rem(m)]


@pytest.mark.parametrize("selector, smallest", [
    (".dial-place", 0.8125), (".dial-note", 0.8125), (".dial-meta", 0.8125),
    (".dial-disclaimer", 0.75), (".gauge-tick", 0.6875), (".dial-mapping", 0.8125),
])
def test_port_status_text_is_bigger(selector, smallest):
    sizes = font_sizes(selector)
    assert sizes and min(sizes) >= smallest, (selector, sizes)


def test_the_port_status_column_is_wider():
    wide = re.search(r"\.brief-layout\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*([\d.]+)rem", CSS)
    assert wide and float(wide.group(1)) >= 26


def test_the_panel_list_shows_that_it_scrolls():
    # Item 4 was cut mid-line with no hint (critique 7): a shadow at the edge that has more.
    body = " ".join(bodies(".panel-items"))
    assert "local" in body and "linear-gradient" in body


def test_labels_on_the_chart_stand_off_what_is_under_them():
    # "Terminal strike" sat over "MAASVLAKTE 2" (critique 8): the item label gets its own card.
    body = " ".join(bodies(".callout-label"))
    assert re.search(r"background:\s*var\(--surface\)", body)
    assert re.search(r"border-radius", body)


def test_the_phone_header_is_one_bar():
    # A quarter of a phone's first screen went to the header (critique 9). The bar: brand and nav
    # on one row when they fit; the one-liner and sample note scroll away with the page.
    assert not re.search(r"\.topbar-tools\s*\{[^}]*width:\s*100%", CSS), "the nav no longer gets its own row"
    assert re.search(r"\.topbar-inner\s*\{[^}]*min-height:\s*3", CSS)


# ---------- Inconsistent (critique 10-13) ----------

def test_an_empty_archive_slot_does_not_look_like_an_unrated_item():
    # Both were outlined squares (critique 12). Unrated keeps its outline; an empty slot is a dash.
    empty = " ".join(bodies(".slot-empty"))
    assert not re.search(r"(border|outline):\s*\d", empty)
    assert re.search(r"outline:\s*2px solid var\(--nodata-ink\)", " ".join(bodies(".num-unrated")))
    assert bodies(".slot-empty::before")


def test_the_land_is_drawn_flat_without_random_grain():
    # Random speckle over the land looked noisy, like a photo rather than a drawing (critique 13).
    assert "createPattern" not in MAP_JS and "Math.random" not in MAP_JS


# ---------- Plain (critique 3, 4, 5) ----------

def test_cards_below_the_first_screen():
    for selector in (".item", ".dial"):
        body = " ".join(bodies(selector))
        assert re.search(r"background:\s*var\(--surface\)", body), selector
        assert re.search(r"border-radius:\s*var\(--radius\)", body), selector


def test_page_titles_are_no_longer_poster_size():
    sizes = re.findall(r"clamp\(([^)]*)\)", " ".join(bodies(".page-title")))
    assert sizes and rem(sizes[0].split(",")[-1]) <= 3.5


def test_how_it_works_uses_the_width_with_its_contents_beside_the_text(site):
    main = soup_of(site / "about.html").find("main")
    assert "page-method" in main["class"]
    assert any(re.search(r"grid-template-columns", body) for body in bodies(".page-method"))
    assert any(re.search(r"position:\s*sticky", body) for body in bodies(".page-method .contents"))


def test_the_footer_has_columns_on_wide_screens():
    assert any(re.search(r"grid-template-columns", body) for body in bodies(".footer-inner"))
