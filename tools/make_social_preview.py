"""Make the social preview image, static/social-preview.png (spec §7.7, issue #95).

LinkedIn and other link previews show it (the og:image tag, #28). Run it again whenever the
one-liner, the colours or the fonts change; tests/test_social_preview.py fails until you do.

    .venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt
    .venv\\Scripts\\python.exe tools/make_social_preview.py

What it draws, 1200 x 630 pixels: the page background, "Haven Daily" large, the owner's one-liner
below it, a thin rule and "Independent portfolio project" small at the bottom; since #117 the
logo's flags too, H over D on a halyard, on the right above the one-liner (patterns from
haven/flags.py, the flag colours used for nothing else). Everything comes
from the site itself: the texts from haven/render.py, the colours from the tokens at the top of
static/style.css (Harbour Light since #102), the letters from the self-hosted Manrope file in
static/fonts/. No map data, photos or anyone else's content (hard rule 13).
The short orange bar above the title is gone since #102: on the site the accent now marks only
what can be pressed or is selected, so on the card it would be decoration.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
from haven.flags import FLAGS, GRID  # noqa: E402
from haven.render import PREVIEW_SIZE, SITE  # noqa: E402  (after the path is set, so it runs as a script)

STATIC_DIR = PROJECT_DIR / "static"
FONTS_DIR = STATIC_DIR / "fonts"
OUT = STATIC_DIR / "social-preview.png"

TITLE = SITE["name"]
TAGLINE = SITE["tagline"]  # the owner's one-liner (§7.8), used exactly
FOOTER = "Independent portfolio project"


def css_tokens(css: Path = STATIC_DIR / "style.css") -> dict[str, tuple[int, int, int]]:
    """The #rrggbb colour tokens in style.css's first :root block, as RGB."""
    text = css.read_text(encoding="utf-8")
    root = text[text.index(":root {"):]
    root = root[:root.index("}")]
    return {name: tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
            for name, value in re.findall(r"--([\w-]+):\s*#([0-9a-fA-F]{6})\b", root)}


_TOKENS = css_tokens()
# The site's palette (§7.2, Harbour Light): fog-white page, navy and secondary ink, the rule line.
COLOURS = {name: _TOKENS[name] for name in ("bg", "ink", "ink-2", "rule",
                                           # the logo's flags (#117): inside the flags only
                                           "flag-white", "flag-red", "flag-yellow", "flag-blue")}

# The site's type roles (§7.3): Manrope for everything here, one variable file. Headlines 800,
# body text 400, labels 800 in capitals with letter-spacing.
MANROPE = FONTS_DIR / "manrope-variable-latin.woff2"
FONTS = {"title": MANROPE, "tagline": MANROPE, "footer": MANROPE}
WEIGHTS = {"title": 800, "tagline": 400, "footer": 800}

WIDTH, HEIGHT = PREVIEW_SIZE
MARGIN = 88          # LinkedIn shows the whole card; the margin keeps text clear of rounded corners
TITLE_SIZE = 148
TAGLINE_SIZE = 38
TAGLINE_WIDTH = 960  # wraps the one-liner onto two lines of about equal length
FOOTER_SIZE = 20
FOOTER_TRACKING = 3  # extra pixels between letters, like the site's labels (letter-spacing)
FLAG = 96            # each flag of the hoist, in px: 4 px per grid unit, so every part is on whole pixels
HOIST_TOP = 96       # top of flag H; flag D follows 8 px below, and the hoist ends above the one-liner


def draw_hoist(draw: ImageDraw.ImageDraw) -> None:
    """The logo's flags, H over D, on a halyard with a clip at each end (#117), right-aligned."""
    unit = FLAG // GRID
    left = WIDTH - MARGIN - FLAG
    halyard = left - 14
    tops = {"H": HOIST_TOP, "D": HOIST_TOP + FLAG + 8}
    bottom = tops["D"] + FLAG
    draw.rectangle((halyard - 1, HOIST_TOP - 12, halyard + 1, bottom + 12), fill=COLOURS["ink"])
    for y in (HOIST_TOP + 6, bottom - 6):  # the clips: a ring on the halyard and a short arm to the flag
        draw.ellipse((halyard - 5, y - 5, halyard + 5, y + 5), outline=COLOURS["ink"], width=2)
        draw.rectangle((halyard + 5, y - 1, left - 1, y + 1), fill=COLOURS["ink"])
    for letter, top in tops.items():
        for colour, x, y, w, h in FLAGS[letter].parts:
            draw.rectangle((left + x * unit, top + y * unit, left + (x + w) * unit - 1, top + (y + h) * unit - 1),
                           fill=COLOURS[f"flag-{colour}"])
        draw.rectangle((left, top, left + FLAG - 1, top + FLAG - 1), outline=COLOURS["ink"], width=2)


def wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Greedy word wrap: as many words per line as fit in `width` pixels."""
    lines: list[str] = []
    for word in text.split():
        if lines and font.getlength(f"{lines[-1]} {word}") <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def draw_tracked(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill, tracking: int) -> None:
    """Text with letter-spacing (Pillow has none): one letter at a time, `tracking` pixels apart."""
    x, y = xy
    for letter in text:
        draw.text((x, y), letter, font=font, fill=fill, anchor="ls")
        x += font.getlength(letter) + tracking


def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    # Pillow's basic text layout on every computer: its Linux build also has Raqm, which places
    # letters slightly differently, so the image remade in CI would not match the one made on Windows.
    loaded = ImageFont.truetype(str(FONTS[role]), size, layout_engine=ImageFont.Layout.BASIC)
    loaded.set_variation_by_axes([WEIGHTS[role]])  # Manrope is variable: its weight axis
    return loaded


def make(out: Path = OUT) -> Path:
    """Draw the card and save it as a PNG at `out`. Returns `out`."""
    title_font = font("title", TITLE_SIZE)
    tagline_font = font("tagline", TAGLINE_SIZE)
    footer_font = font("footer", FOOTER_SIZE)

    image = Image.new("RGB", (WIDTH, HEIGHT), COLOURS["bg"])
    draw = ImageDraw.Draw(image)

    # The title on its baseline ("ls" = left, baseline).
    title_baseline = 280
    # A few px left of the margin: the big H has blank space on its left; this lines its stem up
    # with the text below it.
    draw.text((MARGIN - 6, title_baseline), TITLE, font=title_font, fill=COLOURS["ink"], anchor="ls")

    # The one-liner, wrapped, in the secondary ink.
    line_height = round(TAGLINE_SIZE * 1.35)
    for n, line in enumerate(wrap(TAGLINE, tagline_font, TAGLINE_WIDTH)):
        draw.text((MARGIN, title_baseline + 102 + n * line_height), line,
                  font=tagline_font, fill=COLOURS["ink-2"], anchor="ls")

    draw_hoist(draw)

    # A thin rule and the small label at the bottom.
    footer_baseline = HEIGHT - 80
    draw.rectangle((MARGIN, footer_baseline - 46, WIDTH - MARGIN, footer_baseline - 45), fill=COLOURS["rule"])
    draw_tracked(draw, (MARGIN, footer_baseline), FOOTER.upper(), footer_font, COLOURS["ink-2"], FOOTER_TRACKING)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, format="PNG", optimize=True)  # Pillow adds no text or metadata chunks by default
    return out


if __name__ == "__main__":
    path = make()
    print(f"Wrote {path.relative_to(PROJECT_DIR)} ({WIDTH} x {HEIGHT})")
