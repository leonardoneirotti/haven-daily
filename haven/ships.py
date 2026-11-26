"""The morning ship snapshot: one format for any ship source (issue #156, spec §6 `ships`).

One snapshot per morning, not live tracking. Each source gets an adapter that returns this format
(the Port of Rotterdam's arrivals and berths, or a few minutes of aisstream.io; both are built once
the source gives written permission, spec §11). The brief, the page and the chart only ever see this:

    {
      "source_id": "aisstream",              who it came from (config), and its name for the credit line
      "source_name": "aisstream.io",
      "kind": "positions",                   "berths" (where a ship is moored) or "positions" (where it was seen)
      "snapshot_start": "...", "snapshot_end": "...",   the listening window, or the data's own time
      "vessels": [ {name, type, status, place, lat, lon, heading, speed_kn, length_m, flag, area,
                    destination_raw, destination, news_item} ],
      "expected": [ {name, type, eta, place, length_m} ] or null    ships due in the next 24 h (berth data only)
    }

- `type`: container / tanker / bulk, or cargo (AIS can't tell container from bulk; owner, #156).
- `status`: moored / anchored / underway.
- `place`: a place id from config/places.toml (terminal, anchorage or area) or null, set by the
  adapter: "ships at the terminal in the news" is then a lookup, never a guess (spec §5.10).
- No MMSI or IMO number: the page never shows one, so it is never kept.

Pure checks and grouping, no network.
"""

from __future__ import annotations

from typing import Iterable

KINDS = ("berths", "positions")
TYPES = ("container", "tanker", "bulk", "cargo")
STATUSES = ("moored", "anchored", "underway")

_REQUIRED = ("source_id", "source_name", "kind", "snapshot_start", "snapshot_end", "vessels")
_VESSEL_REQUIRED = ("name", "type", "status", "place", "lat", "lon")
_EXPECTED_REQUIRED = ("name", "type", "eta", "place")


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_snapshot(data, place_ids: set[str]) -> list[str]:
    """Every way `data` breaks the format, as short lines; [] when it is fine."""
    if not isinstance(data, dict):
        return ["the snapshot is not an object"]
    problems = [f"missing {name}" for name in _REQUIRED if name not in data]
    if problems:
        return problems
    for name in ("source_id", "source_name", "snapshot_start", "snapshot_end"):
        if not _text(data[name]):
            problems.append(f"{name} must be text")
    if data["kind"] not in KINDS:
        problems.append(f"kind must be one of {', '.join(KINDS)}")
    if not isinstance(data["vessels"], list):
        return problems + ["vessels must be a list"]
    for n, ship in enumerate(data["vessels"], start=1):
        problems += [f"vessel {n}: {p}" for p in _check_vessel(ship, place_ids)]
    expected = data.get("expected")
    if expected is not None:
        if not isinstance(expected, list):
            problems.append("expected must be a list or null")
        else:
            for n, ship in enumerate(expected, start=1):
                problems += [f"expected {n}: {p}" for p in _check_expected(ship, place_ids)]
    return problems


def _check_place(ship: dict, place_ids: set[str]) -> list[str]:
    place = ship["place"]
    return [] if place is None or place in place_ids else [f"place {place!r} is not in config/places.toml"]


def _check_vessel(ship, place_ids: set[str]) -> list[str]:
    if not isinstance(ship, dict):
        return ["not an object"]
    problems = [f"missing {name}" for name in _VESSEL_REQUIRED if name not in ship]
    if problems:
        return problems
    if not _text(ship["name"]):
        problems.append("name must be text")
    if ship["type"] not in TYPES:
        problems.append(f"type must be one of {', '.join(TYPES)}")
    if ship["status"] not in STATUSES:
        problems.append(f"status must be one of {', '.join(STATUSES)}")
    for name in ("lat", "lon"):
        if not _number(ship[name]):
            problems.append(f"{name} must be a number")
    for name in ("heading", "speed_kn", "length_m"):
        if ship.get(name) is not None and not _number(ship[name]):
            problems.append(f"{name} must be a number or null")
    return problems + _check_place(ship, place_ids)


def _check_expected(ship, place_ids: set[str]) -> list[str]:
    if not isinstance(ship, dict):
        return ["not an object"]
    problems = [f"missing {name}" for name in _EXPECTED_REQUIRED if name not in ship]
    if problems:
        return problems
    if not _text(ship["name"]):
        problems.append("name must be text")
    if ship["type"] not in TYPES:
        problems.append(f"type must be one of {', '.join(TYPES)}")
    if not _text(ship["eta"]):
        problems.append("eta must be a time")
    return problems + _check_place(ship, place_ids)


def by_place(vessels: Iterable[dict], places) -> list[dict]:
    """The ships counted per place (for the Ships dial's counts per terminal, PR 2 of #156; the map
    shows every ship instead, owner's change on PR #157): one entry per place with ships, at the
    centre of its ships, most ships first. Ships without a place (most under way) are counted in none.
    `news_item`: the most severe (lowest) item rank linked to a ship there, or None."""
    labels = {place.id: place.label for place in places}
    groups: dict[str, list[dict]] = {}
    for ship in vessels:
        if ship.get("place"):
            groups.setdefault(ship["place"], []).append(ship)
    counts = []
    for place, group in groups.items():
        linked = [ship["news_item"] for ship in group if ship.get("news_item")]
        by_type: dict[str, int] = {}
        for ship in group:
            by_type[ship["type"]] = by_type.get(ship["type"], 0) + 1
        counts.append({
            "place": place,
            "label": labels.get(place, place),
            "lat": round(sum(ship["lat"] for ship in group) / len(group), 5),
            "lon": round(sum(ship["lon"] for ship in group) / len(group), 5),
            "count": len(group),
            "by_type": by_type,
            "news_item": min(linked) if linked else None,
        })
    order = list(groups)  # ties keep the order the places first appear in
    return sorted(counts, key=lambda entry: (-entry["count"], order.index(entry["place"])))
