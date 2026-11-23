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


def test_every_flag_is_drawn_square(site):
    """All signal code flags are square (Flags of the World, read by the owner 23 Nov 2026)."""
    page = soup(site / "about.html")
    for svg in page.select("svg.signal-flag"):  # the flag key: one flag per svg
        _, _, w, h = svg["viewbox"].split()  # html.parser lowercases attribute names
        assert w == h, svg["viewbox"]
    for edge in soup(site / "index.html").select("header svg.hoist .flag-edge"):  # the logo
        assert edge["width"] == edge["height"], edge
    from tools import make_icons, make_social_preview as card
    assert all(isinstance(lay.flag, int) and lay.flag > 0 for lay in make_icons.LAYOUTS.values())  # one size, both sides
    with Image.open(STATIC_DIR / "social-preview.png") as image:  # the card: outline FLAG x FLAG
        px = image.convert("RGB")
        ink = card.COLOURS["ink"]
        left = card.WIDTH - card.MARGIN - card.FLAG
        for top in (card.HOIST_TOP, card.HOIST_TOP + card.FLAG + 8):
            corners = [(left, top), (left + card.FLAG - 1, top), (left, top + card.FLAG - 1),
                       (left + card.FLAG - 1, top + card.FLAG - 1)]
            assert all(px.getpixel(c) == ink for c in corners), top


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


def test_every_header_names_the_flags_with_their_letters(site):
    """Owner's pick (a), PR #120: the letters next to the flags, on every page, phone included."""
    for page in ("index.html", "archive.html", "about.html", "404.html"):
        brand = soup(site / page).select_one("header .brand")
        letters = brand.select_one(".hoist-letters")
        assert letters is not None and letters.get("aria-hidden") == "true", page
        assert [text_of(s) for s in letters.find_all("span")] == ["H", "D"], page
        assert letters.find_previous_sibling("svg", class_="hoist") is not None, page


def test_the_letters_stay_beside_the_flags_on_every_screen():
    assert sorted(css_rem(".hoist-letters", "height")) == sorted(css_rem(".hoist", "height"))
    for selector, body in rules():
        if ".hoist-letters" in selector:
            assert "display: none" not in body and "display:none" not in body, selector


def test_today_says_what_the_logo_spells_and_links_to_the_flag_key(site):
    """Owner's pick (b), PR #120: one sentence in "About this project" on Today."""
    about = soup(site / "index.html").select_one("section.about")
    line = about.select_one("p.about-flags")
    assert re.sub(r"\s+", " ", line.get_text()).strip() == "Our logo spells H·D, Haven Daily, in maritime signal flags."
    assert [a["href"] for a in line.select("a")] == ["about.html#flags"]
    assert soup(site / "about.html").select_one("#flags") is not None  # the key it links to


def test_the_key_tells_where_each_flag_is_used(site):
    section = soup(site / "about.html").select_one("section[aria-labelledby=flags]")
    intro = text_of(section.select_one("p"))
    assert "H over D" in intro and "browser tab" in intro and "flag P" not in intro
    p_row = [r for r in section.select(".signal-key li") if text_of(r.select_one(".signal-letter")) == "P"][0]
    assert "browser tab" not in text_of(p_row) and "home screen" not in text_of(p_row)


# --- favicon and app icon: H over D on the light-blue tile (owner's pick, PR #120) ----------------

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


# The flags as large as the tile allows: together they fill at least this share of the height.
FILL = {16: 1.0, 32: 30 / 32, 180: 148 / 180}


@pytest.mark.parametrize("name, size", ICONS.items())
def test_the_icon_is_h_over_d_on_the_light_blue_tile(name, size):
    from tools import make_icons
    tokens = css_tokens()
    colour = {k: rgb(tokens[k]) for k in ("water", "flag-white", "flag-red", "flag-yellow", "flag-blue")}
    lay = make_icons.LAYOUTS[size]
    assert 2 * lay.flag + lay.gap >= FILL[size] * size  # as large as possible
    with Image.open(STATIC_DIR / name) as image:
        px = image.convert("RGBA")
        at = lambda x, y: px.getpixel((x, y))[:3]  # noqa: E731
        # H: white at the hoist (left), red at the fly (right), inside its outline
        inner, edge = lay.flag - 2 * lay.line, lay.line
        hx, hy = lay.left + edge, lay.top + edge
        assert at(hx + inner // 4, hy + inner // 2) == colour["flag-white"]
        assert at(hx + 3 * inner // 4, hy + inner // 2) == colour["flag-red"]
        # D: yellow, blue, yellow, 1 : 2 : 1
        d_edge = lay.line if lay.outline_d else 0
        d_inner = lay.flag - 2 * d_edge
        dx, dy = lay.left + d_edge, lay.top + lay.flag + lay.gap + d_edge
        assert at(dx + d_inner // 2, dy + d_inner // 8) == colour["flag-yellow"]
        assert at(dx + d_inner // 2, dy + d_inner // 2) == colour["flag-blue"]
        assert at(dx + d_inner // 2, dy + d_inner - 1 - d_inner // 8) == colour["flag-yellow"]
        assert at(1, size // 2) == colour["water"]  # the tile beside the flags
        corner = px.getpixel((0, 0))
        assert corner[3] == 255 if size == 180 else corner[3] < 128  # rounded tile; phones round the 180 themselves


@pytest.mark.parametrize("name, size", [("favicon-16.png", 16), ("favicon-32.png", 32)])
def test_small_icons_are_sharp(name, size):
    """Drawn pixel by pixel: outside the rounded corners every pixel is exactly a token colour."""
    tokens = css_tokens()
    allowed = {rgb(tokens[t]) for t in ("water", "ink", "flag-white", "flag-red", "flag-yellow", "flag-blue")}
    r = size // 4
    with Image.open(STATIC_DIR / name) as image:
        px = image.convert("RGBA")
        for x in range(size):
            for y in range(size):
                in_corner = (x < r or x >= size - r) and (y < r or y >= size - r)
                if not in_corner:
                    assert px.getpixel((x, y))[:3] in allowed and px.getpixel((x, y))[3] == 255, (x, y)


def test_the_svg_icon_draws_h_over_d_on_the_tile():
    svg = (STATIC_DIR / "favicon.svg").read_text(encoding="utf-8")
    tokens = css_tokens()
    assert re.search(rf'<rect[^>]*rx="\d+"[^>]*fill="{tokens["water"]}"', svg)
    for name in ("flag-white", "flag-red", "flag-yellow", "flag-blue", "ink"):
        assert tokens[name] in svg, name
    assert "H over D" in svg and "Blue Peter" not in svg


def test_the_blue_peter_is_only_in_the_flag_key(site):
    assert 'FLAGS["P"]' not in (PROJECT_DIR / "tools" / "make_icons.py").read_text(encoding="utf-8")
    for page in ("index.html", "archive.html", "about.html", "404.html"):
        for p_flag in soup(site / page).select("g.flag-p"):
            assert page == "about.html" and p_flag.find_parent(class_="signal-key"), page


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
    assert "crwflags.com/fotw/flags/xf-ics.html" in logo  # colours and proportions (owner, 23 Nov 2026)
    assert "Still to check" not in logo and "to be checked" not in logo


def test_no_open_note_on_the_flags_remains():
    assert "to be checked" not in Path(flags.__file__).read_text(encoding="utf-8")


def test_the_reference_picture_is_small():
    assert (PROJECT_DIR / "design" / "logo" / "references" / "hoist.png").stat().st_size < 200_000
