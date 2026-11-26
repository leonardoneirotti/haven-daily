"""A busy invented day for the speed run (#156): the sample site with 250 invented ships on one day.

The real ship count per morning is unknown until a ship source gives permission (spec §5.9 plans for
100-250). This writes a copy of the sample briefs into OUT, the quiet day 2026-10-28 with 250 ships
(the sample day's own 34, then invented ones spread around their places), for
`python -m haven.render --briefs OUT --preview-ships`. It reads "data/sample/briefs" (read only)
and never writes into data/. Every ship is invented ("Busy Invented 001", ...).

    python tools/make_busy_ships.py "$RUNNER_TEMP/busy-briefs"
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample" / "briefs"
DAY = "2026-10-28"
COUNT = 250


def busy(brief: dict, count: int = COUNT) -> dict:
    """The brief with `count` ships: the first ones as they are, then copies moved a little."""
    ships = brief["ships"]
    vessels = list(ships["vessels"])
    shuffle = random.Random(156)  # the same busy day on every run
    n = 0
    while len(vessels) < count:
        model = vessels[n % len(ships["vessels"])]
        n += 1
        copy = dict(model, name=f"Busy Invented {n:03d}", news_item=None,
                    lat=round(model["lat"] + shuffle.uniform(-0.006, 0.006), 5),
                    lon=round(model["lon"] + shuffle.uniform(-0.01, 0.01), 5),
                    heading=shuffle.randrange(0, 360))
        vessels.append(copy)
    return dict(brief, ships=dict(ships, vessels=vessels))


def main() -> None:
    out = Path(sys.argv[1])
    if out.resolve().is_relative_to((ROOT / "data").resolve()):
        raise SystemExit("make_busy_ships.py writes outside data/ only")
    out.mkdir(parents=True, exist_ok=True)
    for path in sorted(SAMPLE.glob("*.json")):
        brief = json.loads(path.read_text(encoding="utf-8"))
        if brief["date"] == DAY:
            brief = busy(brief)
        (out / path.name).write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote the sample briefs to {out}, {DAY} with {COUNT} invented ships")


if __name__ == "__main__":
    main()
