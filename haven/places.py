"""The AI picks from fixed lists; the code fills in the facts (spec §5.10).

The summariser answers with one place id (or "none") and up to 5 "affects" tags.
`pick()` turns that answer into what goes on the item:

- `map`: lat, lon, label and side copied from config/places.toml, or None (no pin);
- `affects`: only tags from config/tags.toml or place labels, at most 5, in the
  list's spelling;
- `unlisted`: every place or tag the AI named that is on neither list, so the owner
  can see what to add (stored on the item's line in data/items/).

Nothing the AI writes reaches the brief unless it is on a list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from haven.config import SHEET_BBOX, Place, load_places, load_tags

__all__ = ["MAX_TAGS", "SHEET_BBOX", "Pick", "pick"]

MAX_TAGS = 5
NO_PLACE = "none"


@dataclass(frozen=True)
class Pick:
    """The checked place and tags for one item."""

    map: dict | None  # {"lat", "lon", "label", "side"}, or None = not on the chart
    affects: list[str]
    unlisted: dict | None  # {"places": [...], "tags": [...]}, or None when everything was listed

    def record(self) -> dict:
        """The item fields: `map` and `affects` always, `unlisted` only when something was discarded."""
        record = {"map": self.map, "affects": list(self.affects)}
        if self.unlisted is not None:
            record["unlisted"] = self.unlisted
        return record


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else str(value).strip()


def pick(place, tags: Iterable | None, places: tuple[Place, ...] | None = None,
         tags_list: tuple[str, ...] | None = None) -> Pick:
    """Check the AI's place id and tags against the lists (read from config/ unless given)."""
    places = load_places() if places is None else places
    tags_list = load_tags() if tags_list is None else tags_list
    unlisted_places: list[str] = []
    unlisted_tags: list[str] = []

    # Place: an id from the list (case and spaces ignored), or "none"/empty = no pin.
    chosen: Place | None = None
    answer = "" if place is None else _text(place)
    if answer and answer.casefold() != NO_PLACE:
        chosen = next((p for p in places if p.id == answer.casefold()), None)
        if chosen is None:
            unlisted_places.append(answer)

    # Tags: the list's tags and every place label; the list's spelling wins.
    allowed = {t.casefold(): t for t in tags_list}
    for p in places:
        allowed.setdefault(p.label.casefold(), p.label)
    affects: list[str] = []
    for raw in tags or ():
        tag = _text(raw)
        if not tag:
            continue
        listed = allowed.get(tag.casefold())
        if listed is None:
            if tag not in unlisted_tags:
                unlisted_tags.append(tag)
        elif listed not in affects and len(affects) < MAX_TAGS:
            affects.append(listed)

    # The pinned place is also a location tag, if there is still room for it.
    if chosen is not None and chosen.label not in affects and len(affects) < MAX_TAGS:
        affects.append(chosen.label)

    map_ = None
    if chosen is not None:
        map_ = {"lat": chosen.lat, "lon": chosen.lon, "label": chosen.label, "side": chosen.side}
    unlisted = None
    if unlisted_places or unlisted_tags:
        unlisted = {"places": unlisted_places, "tags": unlisted_tags}
    return Pick(map=map_, affects=affects, unlisted=unlisted)
