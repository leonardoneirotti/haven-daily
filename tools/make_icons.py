"""Make the favicon and app icon: flags H over D on a light-blue tile (spec §7.6; owner's pick, PR #120).

    .venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt
    .venv\\Scripts\\python.exe tools/make_icons.py

Writes into static/: favicon.svg (browsers that take SVG), favicon-16.png and favicon-32.png
(drawn pixel by pixel at their own size) and apple-touch-icon.png (180 px, a phone's home screen).
tests/test_signal_flags.py fails until the committed files are what this script makes.

The logo's two flags, H over D (Haven Daily), on the chart's water colour (--water). Patterns from
haven/flags.py, colours from the tokens in static/style.css. Each size has its own layout on whole
pixels, with the flags as large as the tile allows, so no edge is blurred:

- 16 px: two 8 px flags filling the height. H has a 1 px navy outline (its white would vanish on
  the pale tile; inside it: white 3 | red 3); D has none, so its bands stay exact (2 / 4 / 2).
- 32 px: two 14 px flags, 1 px outlines, 2 px apart (white 6 | red 6; bands 3 / 6 / 3).
- 180 px: two 70 px flags, 3 px outlines, 8 px apart (white 32 | red 32; bands 16 / 32 / 16), on
  a square tile: iOS and Android round a home-screen icon's corners themselves, and a transparent
  corner would show black there.

Only the tile's rounded corners are smoothed (drawn at 4x and reduced).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
from haven.flags import FLAGS, GRID  # noqa: E402  (after the path is set, so it runs as a script)
from tools.make_social_preview import css_tokens  # noqa: E402

STATIC_DIR = PROJECT_DIR / "static"
_TOKENS = css_tokens()
TILE = _TOKENS["water"]
EDGE = _TOKENS["flag-edge"]  # navy, = --ink
FLAG_COLOURS = {name: _TOKENS[f"flag-{name}"] for name in ("white", "red", "yellow", "blue")}


@dataclass(frozen=True)
class Layout:
    radius: int      # the tile's corner radius (0 = square)
    flag: int        # each flag's side, outline included: square
    line: int        # outline width
    left: int        # the flags' left edge
    top: int         # flag H's top edge; D follows `gap` px below H
    gap: int
    outline_d: bool  # False at 16 px, where an outline would leave D's bands uneven


LAYOUTS = {
    16: Layout(radius=3, flag=8, line=1, left=4, top=0, gap=0, outline_d=False),
    32: Layout(radius=7, flag=14, line=1, left=9, top=1, gap=2, outline_d=True),
    180: Layout(radius=0, flag=70, line=3, left=55, top=16, gap=8, outline_d=True),
}
FILES = {16: "favicon-16.png", 32: "favicon-32.png", 180: "apple-touch-icon.png"}
SUPERSAMPLE = 4  # for the rounded corners only


def hex_colour(colour: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{c:02x}" for c in colour)


def flag_rects(letter: str, x: int, y: int, size: int, line: int) -> list[tuple[tuple[int, int, int], int, int, int, int]]:
    """(colour, left, top, width, height) in whole pixels: the outline (if any), then the parts."""
    rects = [(EDGE, x, y, size, size)] if line else []
    inner = size - 2 * line
    scale = inner / GRID
    for colour, px, py, w, h in FLAGS[letter].parts:
        left, top = x + line + round(px * scale), y + line + round(py * scale)
        right, bottom = x + line + round((px + w) * scale), y + line + round((py + h) * scale)
        rects.append((FLAG_COLOURS[colour], left, top, right - left, bottom - top))
    return rects


def layout_rects(lay: Layout) -> list:
    d_top = lay.top + lay.flag + lay.gap
    return (flag_rects("H", lay.left, lay.top, lay.flag, lay.line)
            + flag_rects("D", lay.left, d_top, lay.flag, lay.line if lay.outline_d else 0))


def png(size: int) -> Image.Image:
    lay = LAYOUTS[size]
    s = SUPERSAMPLE
    # The tile, its corners smoothed. Transparent pixels carry the tile's colour, so they don't darken.
    big = Image.new("RGBA", (size * s, size * s), (*TILE, 0))
    ImageDraw.Draw(big).rounded_rectangle((0, 0, size * s - 1, size * s - 1), radius=lay.radius * s,
                                          fill=(*TILE, 255))
    image = big.reduce(s)
    draw = ImageDraw.Draw(image)
    for colour, x, y, w, h in layout_rects(lay):  # the flags: whole pixels, no smoothing
        draw.rectangle((x, y, x + w - 1, y + h - 1), fill=(*colour, 255))
    return image


def svg() -> str:
    """The 32 px layout as SVG, edges kept crisp."""
    lay = LAYOUTS[32]
    rects = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{hex_colour(c)}"/>'
                    for c, x, y, w, h in layout_rects(lay))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
            '  <title>Haven Daily: signal flags H over D</title>\n'
            f'  <rect width="32" height="32" rx="{lay.radius}" fill="{hex_colour(TILE)}"/>\n'
            f'  <g shape-rendering="crispEdges">{rects}</g>\n'
            '</svg>\n')


def make(out_dir: Path = STATIC_DIR) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for size, name in FILES.items():
        image = png(size)
        if size == 180:  # opaque: the home screen rounds it
            image = image.convert("RGB")
        image.save(out_dir / name, format="PNG", optimize=True)
    (out_dir / "favicon.svg").write_text(svg(), encoding="utf-8", newline="\n")
    return out_dir


if __name__ == "__main__":
    make()
    print("Wrote static/favicon.svg, " + ", ".join(f"static/{n}" for n in FILES.values()))
