"""The maritime signal flags on the site (issue #117, spec §7.6): one source for all of them.

The logo is H over D (Haven Daily), the favicon and app icon are P (the "Blue Peter": the vessel
is about to proceed to sea, a fresh morning edition), and the 404 page shows D. The header
(templates/_macros.html), the icons (tools/make_icons.py), the social card
(tools/make_social_preview.py), the 404 page and the flag key on How it works all draw from here.

Checked against the International Code of Signals (SOURCE):
- **Meanings** are quoted from its single-letter signals (Chapter 1, Section 10, page 22); its
  spelling is American ("harbor", "maneuvering").
- **Patterns** follow the Code's flags: H white at the hoist and red at the fly, in vertical
  halves; D yellow, blue, yellow in horizontal bands; P blue with a white square in the centre.
  The Code's text gives no exact shades or proportions: the flags are shown in its colour plate,
  in five colours only (red, blue, yellow, black, white). Our proportions (D's bands 1 : 2 : 1, P's
  square a third of the flag, square flags) are the usual drawing of these flags, to be checked
  against the plate (spec §7.6).
- **Colours** are the five Code colours, as the tokens --flag-white, --flag-red, --flag-yellow and
  --flag-blue in static/style.css. They are used only inside flags, never as UI colours, so they
  can't be confused with the severity colours (spec §7.2).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CODE_COLOURS", "FLAGS", "GRID", "SOURCE", "Flag"]

SOURCE = {
    "title": "International Code of Signals",
    "publication": "Pub. 102",
    "edition": "United States Edition, 1969 (Revised 2003)",
    "publisher": "National Imagery and Mapping Agency",
    "where": "Chapter 1, Section 10, single-letter signals, page 22",
    "read": "https://archive.org/details/pub-102",  # the copy read on 23 Nov 2026
}

CODE_COLOURS = frozenset({"red", "blue", "yellow", "black", "white"})
GRID = 24  # a flag is GRID x GRID units; every part sits on whole units, so small sizes stay sharp


@dataclass(frozen=True)
class Flag:
    letter: str
    name: str  # the phonetic name in the Code's spelling table
    meanings: tuple[tuple[str | None, str], ...]  # (context or None, meaning), quoted from the Code
    parts: tuple[tuple[str, int, int, int, int], ...]  # (Code colour, x, y, width, height), drawn in order


_HALF, _QUARTER, _THIRD = GRID // 2, GRID // 4, GRID // 3

FLAGS = {
    "H": Flag("H", "Hotel", ((None, "I have a pilot on board."),),
              (("white", 0, 0, _HALF, GRID), ("red", _HALF, 0, _HALF, GRID))),
    "D": Flag("D", "Delta", ((None, "Keep clear of me; I am maneuvering with difficulty."),),
              (("yellow", 0, 0, GRID, _QUARTER), ("blue", 0, _QUARTER, GRID, 2 * _QUARTER),
               ("yellow", 0, 3 * _QUARTER, GRID, _QUARTER))),
    "P": Flag("P", "Papa",
              (("In harbor", "All persons should report on board as the vessel is about to proceed to sea."),
               ("At sea", "It may be used by fishing vessels to mean: ‘My nets have come fast upon an "
                          "obstruction’.")),
              (("blue", 0, 0, GRID, GRID), ("white", _THIRD, _THIRD, _THIRD, _THIRD))),
}
