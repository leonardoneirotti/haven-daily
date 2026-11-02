"""Self-hosted IBM Plex fonts (#27, spec §7.3).

The pages used to load IBM Plex from Google Fonts, which sends every visitor's IP
address to Google. The font files now live in static/fonts/ and style.css points at
them with @font-face rules, so a page never asks Google for anything.
"""

import re
from pathlib import Path

import pytest

from haven import render

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "static"
FONTS_DIR = STATIC_DIR / "fonts"
STYLE_CSS = STATIC_DIR / "style.css"
SAMPLE_BRIEFS = PROJECT_DIR / "data" / "sample" / "briefs"

GOOGLE_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")

# What the design uses (spec §7.3) = what the old Google Fonts link loaded.
NEEDED = [
    ("IBM Plex Sans", "normal", 400), ("IBM Plex Sans", "normal", 500),
    ("IBM Plex Sans", "normal", 600), ("IBM Plex Sans", "normal", 700),
    ("IBM Plex Sans", "italic", 400),
    ("IBM Plex Sans Condensed", "normal", 500), ("IBM Plex Sans Condensed", "normal", 600),
    ("IBM Plex Sans Condensed", "normal", 700),
    ("IBM Plex Mono", "normal", 400), ("IBM Plex Mono", "normal", 500),
    ("IBM Plex Mono", "normal", 600),
    ("IBM Plex Serif", "normal", 400), ("IBM Plex Serif", "normal", 600),
    ("IBM Plex Serif", "italic", 400),
]

# Letters the pages show: English, Dutch, German and other European place and
# company names, plus the punctuation the design uses (· — € ↓).
CHARACTERS = "Aaz09éëïöüßÅøæçñłőşčž·—–€↓’“”"


def font_faces(css: str) -> list[dict]:
    """Each @font-face rule in the stylesheet as {family, style, weights, urls, ranges, display}."""
    faces = []
    for body in re.findall(r"@font-face\s*\{([^}]*)\}", css):
        family = re.search(r"font-family:\s*[\"']([^\"']+)[\"']", body).group(1)
        style = re.search(r"font-style:\s*(\w+)", body).group(1)
        weight = [int(w) for w in re.search(r"font-weight:\s*([\d ]+);", body).group(1).split()]
        display = re.search(r"font-display:\s*(\w+)", body)
        ranges = []
        unicode_range = re.search(r"unicode-range:\s*([^;]+);", body)
        if unicode_range:
            for part in unicode_range.group(1).split(","):
                start, _, end = part.strip()[2:].partition("-")
                ranges.append((int(start, 16), int(end or start, 16)))
        faces.append({
            "family": family, "style": style,
            "weights": range(weight[0], weight[-1] + 1),
            "urls": re.findall(r"url\([\"']?([^\"')]+)[\"']?\)", body),
            "ranges": ranges or [(0, 0x10FFFF)],
            "display": display.group(1) if display else None,
        })
    return faces


@pytest.fixture(scope="module")
def faces():
    return font_faces(STYLE_CSS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    render.render_site(SAMPLE_BRIEFS, out)
    return out


# --- no request to Google ---------------------------------------------------------


def test_no_rendered_page_or_asset_mentions_google_font_hosts(site):
    for path in site.rglob("*"):
        if path.suffix in {".html", ".css", ".js"}:
            text = path.read_text(encoding="utf-8")
            for host in GOOGLE_HOSTS:
                assert host not in text, f"{path.relative_to(site)} mentions {host}"


def test_no_template_or_static_file_mentions_google_font_hosts():
    # Also catches a template the sample site doesn't render.
    for folder in (PROJECT_DIR / "templates", STATIC_DIR):
        for path in folder.rglob("*"):
            if path.suffix in {".html", ".css", ".js"}:
                text = path.read_text(encoding="utf-8")
                for host in GOOGLE_HOSTS:
                    assert host not in text, f"{path.relative_to(PROJECT_DIR)} mentions {host}"


# --- the @font-face rules -----------------------------------------------------------


def test_every_font_face_loads_a_local_woff2_file(faces):
    assert faces, "style.css has no @font-face rules"
    for face in faces:
        assert face["urls"], face
        for url in face["urls"]:
            assert not re.match(r"^[a-z]+:|^//", url), f"{url} is not a local file"
            assert url.startswith("fonts/") and url.endswith(".woff2"), url
            path = STATIC_DIR / url  # relative to style.css, which sits in static/
            assert path.is_file(), f"{url} is missing"
            assert path.read_bytes()[:4] == b"wOF2", f"{url} is not a woff2 file"


@pytest.mark.parametrize("family, style, weight", NEEDED)
def test_each_family_weight_and_style_the_design_uses_has_a_font_face(faces, family, style, weight):
    matching = [f for f in faces if f["family"] == family and f["style"] == style
                and weight in f["weights"]]
    assert matching, f"no @font-face for {family} {style} {weight}"
    for char in CHARACTERS:
        assert any(start <= ord(char) <= end for f in matching for start, end in f["ranges"]), \
            f"{family} {style} {weight} has no file for {char!r}"


def test_no_extra_families_weights_or_styles(faces):
    # Only what the design uses: no fonts the browser would never need.
    for face in faces:
        covered = [(face["family"], face["style"], w) for w in face["weights"]
                   if (face["family"], face["style"], w) in NEEDED]
        assert covered, f"unused @font-face: {face['family']} {face['style']}"
        assert face["weights"][0] in [w for _, _, w in covered] and \
            face["weights"][-1] in [w for _, _, w in covered], face


def test_text_stays_visible_while_fonts_load(faces):
    # Same as the old link's &display=swap: show the fallback font at once, swap when loaded.
    assert all(face["display"] == "swap" for face in faces)


def test_every_font_file_in_static_fonts_is_used(faces):
    used = {url for face in faces for url in face["urls"]}
    for path in FONTS_DIR.glob("*.woff2"):
        assert f"fonts/{path.name}" in used, f"{path.name} is not used by style.css"


# --- licence and credits ------------------------------------------------------------


def test_ofl_licence_ships_with_the_fonts():
    licence = (FONTS_DIR / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence
    assert 'Copyright © 2017 IBM Corp. with Reserved Font Name "Plex"' in licence


def test_fonts_and_licence_are_published_with_the_site(site, faces):
    for url in {url for face in faces for url in face["urls"]}:
        assert (site / "static" / url).is_file(), url
    assert (site / "static" / "fonts" / "OFL.txt").is_file()


def test_method_page_credits_the_fonts_and_links_the_licence(site):
    about = (site / "about.html").read_text(encoding="utf-8")
    credit = re.search(r"Fonts: IBM Plex Sans, Sans Condensed, Mono and Serif \((.*?)\)", about)
    assert credit, "font credit missing on the Method page"
    assert 'href="static/fonts/OFL.txt"' in credit.group(1)
    assert "SIL Open Font License" in credit.group(1)
