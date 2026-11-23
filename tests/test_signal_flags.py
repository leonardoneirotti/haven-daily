"""The signal-flag logo and the flags around it (issue #117, closes #29; spec §7.6).

- The logo: flags H over D (Haven Daily) on a thin halyard with small clips, with "Haven Daily" in
  Manrope next to it; on hover and focus "H·D in maritime signal flags".
- Favicon and app icon: flag P, the "Blue Peter", in a light-blue rounded tile (16, 32, 180 px).
- A 404 page with flag D and a link back to Today.
- A flag key on How it works: H, D and P with their letters and their meanings in the
  International Code of Signals.

Every flag comes from one place, haven/flags.py: its letter, name, meaning (quoted from the Code)
and pattern. The real flag colours are used only inside flags, never as UI colours, so they
can't be confused with the severity colours.
"""

import re
import struct
from pathlib import Path
from urllib.parse import urlparse

import pytest
from bs4 import BeautifulSoup
from PIL import Image, ImageChops

from haven import flags, render
from haven.config import load_site

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "static"
CSS = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
SAMPLE_BRIEFS = PROJECT_DIR / "data" / "sample" / "briefs"
BASE_PATH = urlparse(load_site().base_url).path  # "/haven-daily/" on GitHub Pages
HINT = "H·D in maritime signal flags"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    render.render_site(SAMPLE_BRIEFS, out)
    return out


def soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def text_of(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ")).strip()


def css_tokens() -> dict[str, str]:
    root = CSS[CSS.index(":root {"):]
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b", root[:root.index("}")]))


def rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def rules():
    """(selector, body) for every CSS rule, media queries opened up."""
    flat = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", flat)]


# --- the flags themselves: one source, checked against the Code ----------------------------------


def test_the_source_is_named():
    assert flags.SOURCE["title"] == "International Code of Signals"
    assert flags.SOURCE["publication"] == "Pub. 102"
    assert flags.SOURCE["edition"] == "United States Edition, 1969 (Revised 2003)"
    assert "page 22" in flags.SOURCE["where"]


def test_the_meanings_are_quoted_from_the_code():
    assert flags.FLAGS["H"].name == "Hotel"
    assert flags.FLAGS["H"].meanings == ((None, "I have a pilot on board."),)
    assert flags.FLAGS["D"].name == "Delta"
    assert flags.FLAGS["D"].meanings == ((None, "Keep clear of me; I am maneuvering with difficulty."),)
    assert flags.FLAGS["P"].name == "Papa"
    assert flags.FLAGS["P"].meanings == (
        ("In harbor", "All persons should report on board as the vessel is about to proceed to sea."),
        ("At sea", "It may be used by fishing vessels to mean: ‘My nets have come fast upon an obstruction’."),
    )


def area(parts):
    return sum(w * h for _, _, _, w, h in parts)


@pytest.mark.parametrize("letter", ["H", "D", "P"])
def test_each_pattern_fills_the_flag_with_code_colours_only(letter):
    parts = flags.FLAGS[letter].parts
    g = flags.GRID
    assert all(0 <= x and 0 <= y and x + w <= g and y + h <= g for _, x, y, w, h in parts)
    assert {colour for colour, *_ in parts} <= flags.CODE_COLOURS  # red, blue, yellow, black, white
    # The first part is the whole field or the parts tile it: either way nothing is left empty.
    whole = parts[0][1:] == (0, 0, g, g)
    assert whole or area(parts) == g * g


def test_h_is_white_at_the_hoist_and_red_at_the_fly_in_vertical_halves():
    g = flags.GRID
    assert flags.FLAGS["H"].parts == (("white", 0, 0, g // 2, g), ("red", g // 2, 0, g // 2, g))


def test_d_is_yellow_blue_yellow_in_horizontal_bands_one_two_one():
    g = flags.GRID
    q = g // 4
    assert flags.FLAGS["D"].parts == (("yellow", 0, 0, g, q), ("blue", 0, q, g, 2 * q), ("yellow", 0, 3 * q, g, q))


def test_p_is_blue_with_a_white_square_in_the_centre():
    g = flags.GRID
    t = g // 3
    assert flags.FLAGS["P"].parts == (("blue", 0, 0, g, g), ("white", t, t, t, t))


# --- flag colours stay inside flags ---------------------------------------------------------------


def test_flag_colours_are_used_only_by_flag_parts():
    for selector, body in rules():
        if "var(--flag-" in body and not selector.startswith(":root"):
            assert all(s.strip().startswith(".flag-") for s in selector.split(",")), selector


def test_flag_colour_values_appear_nowhere_else_in_the_stylesheet():
    tokens = css_tokens()
    root_end = CSS.index("}", CSS.index(":root {"))
    rest = CSS[root_end:].lower()
    for name in ("flag-red", "flag-yellow", "flag-blue"):
        assert tokens[name].lower() not in rest, name


def test_flag_parts_are_drawn_only_inside_a_flag(site):
    for page in ("index.html", "about.html", "404.html"):
        for part in soup(site / page).select("[class*='flag-']"):
            assert part.find_parent("svg", class_=re.compile(r"\b(signal-flag|hoist)\b")), (page, part)


# --- the logo in the header -----------------------------------------------------------------------


@pytest.mark.parametrize("page", ["index.html", "archive.html", "about.html", "404.html"])
def test_every_header_has_the_hoist_and_the_name(site, page):
    brand = soup(site / page).select_one("header .brand")
    hoist = brand.select_one("svg.hoist")
    assert hoist is not None and hoist.get("aria-hidden") == "true"
    assert text_of(brand.select_one(".brand-name")) == "Haven Daily"


def test_the_hoist_is_h_over_d_on_a_halyard_with_clips(site):
    hoist = soup(site / "index.html").select_one("header svg.hoist")
    assert hoist.select_one(".halyard") is not None
    assert len(hoist.select(".clip")) == 2
    h, d = hoist.select("g.flag-h"), hoist.select("g.flag-d")
    assert len(h) == 1 and len(d) == 1
    y = lambda g: float(re.search(r"translate\(\s*[\d.]+[ ,]+([\d.]+)", g["transform"]).group(1))  # noqa: E731
    assert y(h[0]) < y(d[0])  # H on top


def test_the_hint_shows_on_hover_and_focus(site):
    brand = soup(site / "index.html").select_one("header .brand")
    hint = brand.select_one(".brand-hint")
    assert text_of(hint) == HINT
    assert brand.get("aria-describedby") == hint.get("id")
    selectors = " ".join(sel for sel, body in rules() if "brand-hint" in sel and re.search(r"opacity:\s*1|visibility:\s*visible", body))
    assert ".brand:hover" in selectors and ".brand:focus-visible" in selectors


def css_rem(selector: str, prop: str) -> list[float]:
    return [float(v) for sel, body in rules() if selector in [s.strip() for s in sel.split(",")]
            for v in re.findall(rf"(?<![\w-]){prop}:\s*([\d.]+)rem", body)]


def test_the_hoist_stays_big_enough_to_read_on_a_phone():
    heights = css_rem(".hoist", "height")
    assert heights and min(heights) >= 2.25  # each flag about 16 CSS px or more


def test_the_name_is_manrope_not_spaced_capitals():
    body = " ".join(b for s, b in rules() if s == ".brand-name")
    assert "--font-mono" not in body and "uppercase" not in body and "letter-spacing: 0." not in body


# --- favicon and app icon: flag P --------------------------------------------------------------------

ICONS = {"favicon-16.png": 16, "favicon-32.png": 32, "apple-touch-icon.png": 180}


def png_size(path: Path) -> tuple[int, int]:
    return struct.unpack(">II", path.read_bytes()[16:24])


@pytest.mark.parametrize("name, size", ICONS.items())
def test_the_icon_files_have_their_sizes(name, size):
    assert png_size(STATIC_DIR / name) == (size, size)


def test_every_page_links_the_icons(site):
    head = soup(site / "index.html").head
    links = {(l.get("rel")[0], l.get("sizes"), l["href"]) for l in head.select("link[rel~=icon], link[rel=apple-touch-icon]")}
    assert ("icon", None, "static/favicon.svg") in links
    assert ("icon", "32x32", "static/favicon-32.png") in links
    assert ("icon", "16x16", "static/favicon-16.png") in links
    assert ("apple-touch-icon", "180x180", "static/apple-touch-icon.png") in links


@pytest.fixture(scope="module")
def remade_icons(tmp_path_factory):
    from tools import make_icons
    out = tmp_path_factory.mktemp("icons")
    make_icons.make(out)
    return out


@pytest.mark.parametrize("name", list(ICONS) + ["favicon.svg"])
def test_the_committed_icons_are_what_the_script_makes(remade_icons, name):
    if name.endswith(".svg"):
        assert (remade_icons / name).read_text(encoding="utf-8") == (STATIC_DIR / name).read_text(encoding="utf-8")
        return
    with Image.open(remade_icons / name) as new, Image.open(STATIC_DIR / name) as old:
        assert ImageChops.difference(new.convert("RGBA"), old.convert("RGBA")).getbbox() is None


@pytest.mark.parametrize("name, size", ICONS.items())
def test_the_icon_is_flag_p_on_the_light_blue_tile(name, size):
    tokens = css_tokens()
    tile, blue, white = rgb(tokens["water"]), rgb(tokens["flag-blue"]), rgb(tokens["flag-white"])
    with Image.open(STATIC_DIR / name) as image:
        px = image.convert("RGBA")
        c = size // 2
        assert px.getpixel((c, c))[:3] == white                    # the white square in the centre
        assert px.getpixel((c, size * 7 // 32))[:3] == blue        # the blue field above it
        assert px.getpixel((c, 0))[:3] == tile                     # the tile's edge, top middle
        corner = px.getpixel((0, 0))
        assert corner[3] == 255 if size == 180 else corner[3] < 128  # rounded tile; iOS rounds the 180 itself


@pytest.mark.parametrize("name, size", [("favicon-16.png", 16), ("favicon-32.png", 32)])
def test_small_icons_are_sharp(name, size):
    """Inside the rounded corners every pixel is exactly a token colour: no blurred flag edges."""
    tokens = css_tokens()
    allowed = {rgb(tokens[t]) for t in ("water", "flag-blue", "flag-white")}
    r = size // 4
    with Image.open(STATIC_DIR / name) as image:
        px = image.convert("RGBA")
        for x in range(size):
            for y in range(size):
                in_corner = (x < r or x >= size - r) and (y < r or y >= size - r)
                if not in_corner:
                    assert px.getpixel((x, y))[:3] in allowed and px.getpixel((x, y))[3] == 255, (x, y)


def test_the_svg_icon_draws_the_same_flag_on_the_tile():
    svg = (STATIC_DIR / "favicon.svg").read_text(encoding="utf-8")
    tokens = css_tokens()
    assert re.search(rf'<rect[^>]*rx="\d+"[^>]*fill="{tokens["water"]}"', svg)
    assert tokens["flag-blue"] in svg and tokens["flag-white"] in svg
    assert "Signal flag P" in svg


# --- the 404 page: flag D ----------------------------------------------------------------------------


def test_the_404_page_is_built(site):
    assert (site / "404.html").is_file()


def test_the_404_page_shows_flag_d_a_friendly_line_and_a_way_back(site):
    page = soup(site / "404.html")
    main = page.select_one("main")
    assert main.select_one("svg.signal-flag g.flag-d") is not None
    assert page.title.get_text().startswith("Page not found")
    text = text_of(main)
    assert "Keep clear of me; I am maneuvering with difficulty." in text
    back = [a for a in main.select("a") if "Today" in text_of(a)]
    assert back and back[0]["href"] == f"{BASE_PATH}index.html"


def test_the_404_page_works_at_any_address(site):
    """GitHub Pages serves 404.html at the missing address, so its links can't be relative."""
    page = soup(site / "404.html")
    for tag, attribute in (("link", "href"), ("script", "src"), ("a", "href")):
        for node in page.select(f"{tag}[{attribute}]"):
            value = node[attribute]
            if value.startswith(("http://", "https://", "#", "mailto:")):
                continue
            assert value.startswith(BASE_PATH), (tag, value)


def test_the_404_page_keeps_the_footer(site):
    text = text_of(soup(site / "404.html").select_one("footer"))
    assert "Personal, unofficial project by Leonardo Neirotti." in text
    assert "Privacy: no cookies" in text


# --- the flag key on How it works ----------------------------------------------------------------------


def test_how_it_works_has_a_key_to_the_three_flags(site):
    section = soup(site / "about.html").select_one("section[aria-labelledby=flags]")
    assert section is not None
    rows = section.select(".signal-key li")
    assert [text_of(r.select_one(".signal-letter")) for r in rows] == ["H", "D", "P"]
    for row, letter in zip(rows, "HDP"):
        flag = flags.FLAGS[letter]
        assert row.select_one(f"svg.signal-flag g.flag-{letter.lower()}") is not None
        text = text_of(row)
        assert flag.name in text
        for _, meaning in flag.meanings:
            assert meaning in text


def test_the_key_names_its_source(site):
    text = text_of(soup(site / "about.html").select_one("section[aria-labelledby=flags]"))
    assert "International Code of Signals" in text and "Pub. 102" in text


# --- the social card ------------------------------------------------------------------------------------


def test_the_social_card_shows_the_hoist():
    from tools import make_social_preview as card
    tokens = css_tokens()
    assert {"flag-red", "flag-yellow", "flag-blue", "flag-white"} <= set(card.COLOURS)
    with Image.open(STATIC_DIR / "social-preview.png") as image:
        colours = {c for _, c in image.convert("RGB").getcolors(maxcolors=1_000_000)}
    for name in ("flag-red", "flag-yellow", "flag-blue"):
        assert rgb(tokens[name]) in colours, name


def test_the_alt_text_mentions_the_flags():
    alt = load_site().social_image_alt
    assert "signal flags H over D" in alt


# --- the spec ----------------------------------------------------------------------------------------------


def test_the_spec_names_the_source():
    spec = (PROJECT_DIR / "docs" / "SPEC.md").read_text(encoding="utf-8")
    logo = spec[spec.index("### 7.6 Logo"):spec.index("### 7.7")]
    assert "Pub. 102" in logo and "Revised 2003" in logo
