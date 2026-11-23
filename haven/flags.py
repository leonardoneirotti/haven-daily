"""The maritime signal flags on the site (issue #117, spec §7.6): one source for all of them.

The site uses two flags only (owner, PR #120): H over D (Haven Daily) is the logo, the favicon
and the app icon, and the 404 page shows D. The header (templates/_macros.html), the icons (tools/make_icons.py), the social card
(tools/make_social_preview.py), the 404 page and the flag key on How it works all draw from here.

Checked against the International Code of Signals (SOURCE):
- **Meanings** are quoted from its single-letter signals (Chapter 1, Section 10, page 22); its
  spelling is American ("maneuvering").
- **Patterns, colours and proportions** follow Flags of the World (FOTW_SOURCE, checked by the
  owner 23 Nov 2026), since the Code's text gives no shades or proportions (it shows the flags only
  in a colour plate, in five colours: red, blue, yellow, black, white): all signal code flags are
  square; H vertically divided, white at the hoist and red at the fly; D horizontally divided
  yellow-blue-yellow, 1 : 2 : 1.
- **Colours** are the five Code colours, as the tokens --flag-white, --flag-red, --flag-yellow and
  --flag-blue in static/style.css. They are used only inside flags, never as UI colours, so they
  can't be confused with the severity colours (spec §7.2).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CODE_COLOURS", "FLAGS", "FOTW_SOURCE", "GRID", "SOURCE", "Flag"]

SOURCE = {
    "title": "International Code of Signals",
    "publication": "Pub. 102",
    "edition": "United States Edition, 1969 (Revised 2003)",
    "publisher": "National Imagery and Mapping Agency",
    "where": "Chapter 1, Section 10, single-letter signals, page 22",
    "read": "https://archive.org/details/pub-102",  # the copy read on 23 Nov 2026
}

# Colours and proportions, which the Code's text doesn't give (owner, 23 Nov 2026).
FOTW_SOURCE = "https://crwflags.com/fotw/flags/xf-ics.html"  # Flags of the World, "International Code of Signals"

CODE_COLOURS = frozenset({"red", "blue", "yellow", "black", "white"})
GRID = 24  # a flag is GRID x GRID units; every part sits on whole units, so small sizes stay sharp


@dataclass(frozen=True)
class Flag:
    letter: str
    name: str  # the phonetic name in the Code's spelling table
    meanings: tuple[tuple[str | None, str], ...]  # (context or None, meaning), quoted from the Code
    parts: tuple[tuple[str, int, int, int, int], ...]  # (Code colour, x, y, width, height), drawn in order


_HALF, _QUARTER = GRID // 2, GRID // 4

FLAGS = {
    "H": Flag("H", "Hotel", ((None, "I have a pilot on board."),),
              (("white", 0, 0, _HALF, GRID), ("red", _HALF, 0, _HALF, GRID))),
    "D": Flag("D", "Delta", ((None, "Keep clear of me; I am maneuvering with difficulty."),),
              (("yellow", 0, 0, GRID, _QUARTER), ("blue", 0, _QUARTER, GRID, 2 * _QUARTER),
               ("yellow", 0, 3 * _QUARTER, GRID, _QUARTER))),
}
