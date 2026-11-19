"""Before and after side by side, one picture per place, plus contact sheets (issue #104).

    python tools/basemap_sheet.py <shots dir> <out dir>

Reads the <place id>-before.png / -after.png pairs and places.json written by
tools/basemap_shots.mjs. Writes <out dir>/<place id>.jpg (before left, after right,
with the place's name) and <out dir>/sheet-1.jpg, sheet-2.jpg... (smaller, 8 places each).
Needs Pillow (not a dependency of the site: pip install pillow).
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

shots, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
places = json.loads((shots / "places.json").read_text(encoding="utf-8"))
GAP, BAR = 8, 30

pairs = []
for place in places:
    before = Image.open(shots / f"{place['id']}-before.png").convert("RGB")
    after = Image.open(shots / f"{place['id']}-after.png").convert("RGB")
    w, h = before.size
    pair = Image.new("RGB", (2 * w + GAP, h + BAR), "white")
    pair.paste(before, (0, BAR))
    pair.paste(after, (w + GAP, BAR))
    draw = ImageDraw.Draw(pair)
    draw.text((8, 9), f"{place['label']}: before", fill="black")
    draw.text((w + GAP + 8, 9), "after", fill="black")
    # The place itself, at the centre of each half.
    for x0 in (0, w + GAP):
        cx, cy = x0 + w // 2, BAR + h // 2
        draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), outline=(255, 0, 160), width=2)
    pair.save(out / f"{place['id']}.jpg", quality=82)
    pairs.append(pair)

PER_SHEET = 8
for n, start in enumerate(range(0, len(pairs), PER_SHEET), 1):
    group = [p.resize((p.width // 2, p.height // 2)) for p in pairs[start:start + PER_SHEET]]
    sheet = Image.new("RGB", (group[0].width, sum(p.height + GAP for p in group)), "white")
    y = 0
    for p in group:
        sheet.paste(p, (0, y))
        y += p.height + GAP
    sheet.save(out / f"sheet-{n}.jpg", quality=80)
print(f"{len(pairs)} places, {(len(pairs) + PER_SHEET - 1) // PER_SHEET} sheets in {out}")
