"""The social preview image, static/social-preview.png (spec §7.7, issue #95).

LinkedIn and other link previews show it (og:image, #28). It is made by a committed script,
tools/make_social_preview.py, so it can be remade: 1200 × 630, the site's dark colours,
"Haven Daily" large, the owner's one-liner below it and "Independent portfolio project" small
at the bottom, in the self-hosted IBM Plex fonts. Nothing from anyone else: no map data, no
photos, no third-party content (hard rule 13).
"""

import re
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from haven import render
from haven.config import load_site, preview_image_size
from tools import make_social_preview as card

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "static"
FONTS_DIR = STATIC_DIR / "fonts"
IMAGE = STATIC_DIR / load_site().social_image


def css_tokens() -> dict[str, str]:
    """The colour tokens at the top of style.css: name → value, read independently of the script."""
    css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
    root = css[css.index(":root {"):]
    root = root[:root.index("}")]
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b", root))


def rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


@pytest.fixture(scope="module")
def remade(tmp_path_factory):
    return card.make(tmp_path_factory.mktemp("card") / "social-preview.png")


# ---------- the file ----------

def test_the_image_is_in_static_and_is_1200_by_630():
    assert IMAGE.exists(), "run tools/make_social_preview.py"
    assert preview_image_size(IMAGE) == render.PREVIEW_SIZE == (1200, 630)


def test_the_committed_image_is_what_the_script_makes(remade):
    # Pillow is pinned in requirements-dev.txt, so the same script draws the same pixels.
    # Fails when the script, the texts, the colours or the fonts changed and the image wasn't remade.
    with Image.open(IMAGE) as committed, Image.open(remade) as fresh:
        assert committed.size == fresh.size
        assert ImageChops.difference(committed.convert("RGB"), fresh.convert("RGB")).getbbox() is None


def test_the_png_carries_no_text_or_metadata_chunks():
    # Only the picture itself: no tEXt/iTXt/zTXt comments, eXIf or tIME, nothing to strip later.
    data = IMAGE.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    kinds, at = [], 8
    while at < len(data):
        length = int.from_bytes(data[at:at + 4], "big")
        kinds.append(data[at + 4:at + 8].decode("ascii"))
        at += 12 + length
    assert set(kinds) <= {"IHDR", "PLTE", "IDAT", "IEND"}, kinds


# ---------- what it shows comes from the site ----------

def test_the_texts_are_the_sites_own():
    assert card.TITLE == render.SITE["name"] == "Haven Daily"
    assert card.TAGLINE == render.SITE["tagline"]  # the owner's one-liner, §7.8, used exactly
    assert card.FOOTER == "Independent portfolio project"


def test_the_colours_are_the_sites_tokens():
    tokens = css_tokens()
    assert card.COLOURS, "the script names the tokens it uses"
    for name, value in card.COLOURS.items():
        assert value == rgb(tokens[name]), name
    assert {"bg", "ink", "ink-2"} <= set(card.COLOURS)


def test_the_background_is_the_pages_background(remade):
    with Image.open(remade) as image:
        image = image.convert("RGB")
        bg = rgb(css_tokens()["bg"])
        for corner in ((0, 0), (1199, 0), (0, 629), (1199, 629)):
            assert image.getpixel(corner) == bg, corner


def test_every_colour_in_the_image_is_a_mix_of_the_tokens_it_names(remade):
    # Anti-aliased text blends a token into the background; nothing else (no photo, no map).
    with Image.open(remade) as image:
        colours = image.convert("RGB").getcolors(maxcolors=1_000_000)
    bg = rgb(css_tokens()["bg"])
    tokens = list(card.COLOURS.values())

    def on_a_blend(colour):
        for token in tokens:
            span = [t - b for t, b in zip(token, bg)]
            reach = max(range(3), key=lambda i: abs(span[i]))
            if span[reach] == 0:
                continue
            share = (colour[reach] - bg[reach]) / span[reach]
            if -0.01 <= share <= 1.01 and all(abs(bg[i] + share * span[i] - colour[i]) <= 3 for i in range(3)):
                return True
        return colour == bg

    strays = [colour for _, colour in colours if not on_a_blend(colour)]
    assert not strays, strays[:10]


def test_the_fonts_are_the_self_hosted_ibm_plex_files():
    css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
    assert card.FONTS, "the script names the fonts it uses"
    for role, path in card.FONTS.items():
        path = Path(path).resolve()
        assert path.parent == FONTS_DIR.resolve(), (role, path)
        assert path.name.startswith("ibm-plex-") and path.suffix == ".woff2", (role, path)
        assert path.exists() and f"fonts/{path.name}" in css, (role, path)  # a file the site serves


def test_the_script_reads_nothing_from_outside_the_repo():
    # Hard rule 13 (and 14's spirit): the card is drawn from our own texts, tokens and fonts only.
    source = Path(card.__file__).read_text(encoding="utf-8")
    for forbidden in ("http://", "https://", "urllib", "requests", "socket", "Image.open"):
        assert forbidden not in source, forbidden


# ---------- the description ----------

def test_the_alt_text_describes_what_the_image_shows():
    alt = load_site().social_image_alt
    for text in (card.TITLE, card.TAGLINE, card.FOOTER):
        assert text.lower() in alt.lower(), text
    for not_shown in ("chart", "map", "ship", "seaport at dusk", "photo"):
        assert not_shown not in alt.lower(), not_shown
