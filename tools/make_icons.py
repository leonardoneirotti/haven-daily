"""Make the favicon and app icon: flag P, the "Blue Peter", on a light-blue tile (spec §7.6, #117).

    .venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt
    .venv\\Scripts\\python.exe tools/make_icons.py

Writes into static/: favicon.svg (browsers that take SVG), favicon-16.png and favicon-32.png
(sharp at their own size) and apple-touch-icon.png (180 px, a phone's home screen).
tests/test_signal_flags.py fails until the committed files are what this script makes.

Flag P ("In harbor: all persons should report on board as the vessel is about to proceed to
sea") stands for a fresh morning edition. Its pattern comes from haven/flags.py, the colours from
the tokens in static/style.css: the tile is the chart's water (--water), the flag --flag-blue and
--flag-white. Each size has its own layout on whole pixels, so no flag edge is blurred:

- 16 px: the flag 12 px (its white square 4 px), 2 px of tile around it, corners rounded 3 px;
- 32 px: the flag 24 px (square 8 px), 4 px of tile, corners 7 px;
- 180 px: the flag 132 px (square 44 px), 24 px of tile, square corners: iOS and Android round
  the corners of a home-screen icon themselves, and a transparent corner would show black there.

Corners are drawn at 4x and reduced, so only the rounded corners are smoothed.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
from haven.flags import FLAGS, GRID  # noqa: E402  (after the path is set, so it runs as a script)
from tools.make_social_preview import css_tokens  # noqa: E402

STATIC_DIR = PROJECT_DIR / "static"
_TOKENS = css_tokens()
TILE = _TOKENS["water"]
FLAG_COLOURS = {"blue": _TOKENS["flag-blue"], "white": _TOKENS["flag-white"]}

# size -> (flag size in px, corner radius in px); the flag sits in the middle of the tile
LAYOUTS = {16: (12, 3), 32: (24, 7), 180: (132, 0)}
FILES = {16: "favicon-16.png", 32: "favicon-32.png", 180: "apple-touch-icon.png"}
SUPERSAMPLE = 4


def hex_colour(colour: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{c:02x}" for c in colour)


def png(size: int) -> Image.Image:
    flag_px, radius = LAYOUTS[size]
    s = SUPERSAMPLE
    # Transparent pixels carry the tile's colour, so the smoothed corners don't darken.
    image = Image.new("RGBA", (size * s, size * s), (*TILE, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size * s - 1, size * s - 1), radius=radius * s, fill=(*TILE, 255))
    offset, unit = (size - flag_px) // 2, flag_px / GRID  # every part still lands on whole pixels
    for colour, x, y, w, h in FLAGS["P"].parts:
        left, top = offset + x * unit, offset + y * unit
        draw.rectangle((left * s, top * s, (left + w * unit) * s - 1, (top + h * unit) * s - 1),
                       fill=(*FLAG_COLOURS[colour], 255))
    return image.reduce(s)


def svg() -> str:
    """The same icon as the 32 px layout, as SVG."""
    flag_px, radius = LAYOUTS[32]
    offset, unit = (32 - flag_px) // 2, flag_px // GRID
    rects = "".join(
        f'<rect x="{offset + x * unit}" y="{offset + y * unit}" width="{w * unit}" height="{h * unit}" '
        f'fill="{hex_colour(FLAG_COLOURS[colour])}"/>'
        for colour, x, y, w, h in FLAGS["P"].parts)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
            '  <title>Signal flag P, the Blue Peter: about to sail (Haven Daily)</title>\n'
            f'  <rect width="32" height="32" rx="{radius}" fill="{hex_colour(TILE)}"/>\n'
            f'  {rects}\n'
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
