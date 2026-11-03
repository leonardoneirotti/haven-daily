"""Make the social preview image, static/social-preview.png (spec §7.7, issue #95).

LinkedIn and other link previews show it (the og:image tag, #28). Run it again whenever the
one-liner, the colours or the fonts change; tests/test_social_preview.py fails until you do.

    .venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt
    .venv\\Scripts\\python.exe tools/make_social_preview.py

What it draws, 1200 x 630 pixels: the page background, a short orange accent bar, "Haven Daily"
large, the owner's one-liner below it, a thin rule and "Independent portfolio project" small
at the bottom. Everything comes from the site itself: the texts from haven/render.py, the
colours from the tokens at the top of static/style.css, the letters from the self-hosted
IBM Plex files in static/fonts/. No map data, photos or anyone else's content (hard rule 13).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
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
# The site's dark palette (§7.2): page, ivory and secondary ink, the rule line, the one orange accent.
COLOURS = {name: _TOKENS[name] for name in ("bg", "ink", "ink-2", "rule", "accent")}

# The site's type roles (§7.3): headlines in Plex Sans Condensed, body text in Plex Sans,
# labels in Plex Mono, uppercase with letter-spacing.
FONTS = {
    "title": FONTS_DIR / "ibm-plex-sans-condensed-700-latin.woff2",
    "tagline": FONTS_DIR / "ibm-plex-sans-400-700-latin.woff2",  # variable 400-700, used at 400
    "footer": FONTS_DIR / "ibm-plex-mono-500-latin.woff2",
}

WIDTH, HEIGHT = PREVIEW_SIZE
MARGIN = 88          # LinkedIn shows the whole card; the margin keeps text clear of rounded corners
TITLE_SIZE = 148
TAGLINE_SIZE = 38
TAGLINE_WIDTH = 960  # wraps the one-liner onto two lines of about equal length
FOOTER_SIZE = 21
FOOTER_TRACKING = 3  # extra pixels between letters, like the site's mono labels (letter-spacing)


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


def make(out: Path = OUT) -> Path:
    """Draw the card and save it as a PNG at `out`. Returns `out`."""
    title_font = ImageFont.truetype(str(FONTS["title"]), TITLE_SIZE)
    tagline_font = ImageFont.truetype(str(FONTS["tagline"]), TAGLINE_SIZE)
    tagline_font.set_variation_by_axes([400])
    footer_font = ImageFont.truetype(str(FONTS["footer"]), FOOTER_SIZE)

    image = Image.new("RGB", (WIDTH, HEIGHT), COLOURS["bg"])
    draw = ImageDraw.Draw(image)

    # The orange accent bar, then the title on its baseline ("ls" = left, baseline).
    draw.rectangle((MARGIN, 120, MARGIN + 72, 127), fill=COLOURS["accent"])
    title_baseline = 290
    # 6 px left of the margin: the big H has blank space on its left; this lines its stem up with the bar.
    draw.text((MARGIN - 6, title_baseline), TITLE, font=title_font, fill=COLOURS["ink"], anchor="ls")

    # The one-liner, wrapped, in the secondary ink.
    line_height = round(TAGLINE_SIZE * 1.35)
    for n, line in enumerate(wrap(TAGLINE, tagline_font, TAGLINE_WIDTH)):
        draw.text((MARGIN, title_baseline + 102 + n * line_height), line,
                  font=tagline_font, fill=COLOURS["ink-2"], anchor="ls")

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
