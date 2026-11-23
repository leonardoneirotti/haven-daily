"""Weather status: KNMI's warnings for the Port of Rotterdam area, read via MeteoAlarm (spec §2.2, §4,
§5.11; issues #18 and #121).

One request a morning to MeteoAlarm's Netherlands feed (JSON, no key; robots.txt allows
bots). It republishes KNMI's own warnings. **Since November 2026** (found at launch, #26) it
holds a few regional warnings, one entry per warning *version*, each area as free text ("South
Holland and Utrecht and parts of: …") **plus a CAP polygon** ("lat,lon lat,lon …"), no geocode,
and **no entry at all for an area without a warning**. (Before, one entry per province, with
KNMI's daily green entries.)

The reading:
- **Which warnings count** (owner, 23 Nov 2026, #121): those whose **polygon contains any of the 41
  places** in config/places.toml (a small point-in-polygon check, no library), never by the
  free-text name. Places at sea count too, so coastal-water warnings over the anchorages count.
  Real messages only (`status` Actual), the newest version of each warning only (a version named
  in another message's `references` has been replaced by an Update or withdrawn by a Cancel), and
  only those **valid at some moment from when the feed was read until midnight** (Amsterdam
  date). A warning that already expired this morning, or starts tomorrow, doesn't count
  (owner's decision, 2 Nov 2026).
- **Nothing for the port area = No warnings**, but only when the feed loaded, parsed in the
  expected shape (every counted entry's area has a readable polygon) and is **fresh**: the
  server's `Date` within 15 minutes of when we read it, and no cache `Age` over 15 minutes.
  Otherwise No data. Never Normal on doubt (owner, 23 Nov 2026).
- **Level:** the highest one decides: green → Normal (`green`), yellow → Watch (`amber`),
  orange/red → Alert (`red`).
- **What is kept** for the display MeteoAlarm requires: "KNMI" as the source, the time of
  issue, KNMI's own level and hazard (e.g. Code yellow · Wind), onset/expiry, a link to
  www.meteoalarm.org and "not live". **Never the warning text** (headline, description).
  With no warnings there is no time of issue, only the read time (owner, 2 Nov 2026).

Any doubt is "No data", never a guess (spec §2.2): the feed down or blocked, not JSON, not
the warnings feed, not fresh, an entry without a readable polygon (we couldn't tell whether it
covers the port), or an unreadable level, hazard or time in a warning for the port area. Then
the reading has `value`/`level` `null` and one failure line goes to build.failures.

`python -m haven.weather` reads the live feed once and prints the reading; it writes nothing.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from email.utils import parsedate_to_datetime

from haven.clock import AMSTERDAM
from haven.config import Place, load_places
from haven.fetch import Fetcher, FetchError

FEED_URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands"
SITE_URL = "https://www.meteoalarm.org"
FAILURE_SOURCE = "Weather warnings (MeteoAlarm)"

AREA_NAME = "Port of Rotterdam area"  # any of the 41 places in config/places.toml (#121)
FRESH_WITHIN = timedelta(minutes=15)  # the server's answer must be this recent (#121)

COLOURS = ("green", "yellow", "orange", "red")  # lowest to highest
STATUS_LEVEL = {"green": "green", "yellow": "amber", "orange": "red", "red": "red"}
COUNTED_MESSAGES = ("Alert", "Update")  # a Cancel only withdraws what it references


class WeatherFeedError(Exception):
    """The feed can't be read safely. One line, naming the kind of problem only."""


@dataclass(frozen=True)
class _Warning:
    colour: str
    hazard: str | None  # None only for green entries without a readable type
    onset: datetime
    expires: datetime | None
    issued: datetime


@dataclass
class WeatherResult:
    reading: dict
    failures: list[dict] = field(default_factory=list)


# --- reading the feed -----------------------------------------------------------------


def reading_from_feed(data, read_at: datetime, places: tuple[Place, ...] | None = None) -> dict:
    """The status reading for the moment `read_at`. Raises WeatherFeedError on any doubt.

    Freshness is checked by read_weather, from the HTTP answer; this reads the feed's content.
    """
    read_at = _amsterdam(read_at)
    points = [(p.lat, p.lon) for p in (load_places() if places is None else places)]
    entries = _alerts(data)
    replaced = {ref for alert in entries if alert.get("status") == "Actual" for ref in _references(alert)}
    end_of_today = datetime.combine(read_at.date() + timedelta(days=1), time(0), AMSTERDAM)

    valid: list[_Warning] = []
    for alert in entries:
        if alert.get("status") != "Actual" or alert.get("msgType") not in COUNTED_MESSAGES:
            continue
        if alert.get("identifier") in replaced:
            continue
        info = _port_info(alert, points)
        if info is None:
            continue
        found = _warning(alert, info)
        if found.onset < end_of_today and (found.expires is None or found.expires > read_at):
            valid.append(found)

    # Nothing for the port area: No warnings (read_weather has checked the answer is fresh).
    top = max((COLOURS.index(w.colour) for w in valid), default=0)
    colour = COLOURS[top]
    raised = sorted((w for w in valid if w.colour != "green"), key=lambda w: (-COLOURS.index(w.colour), w.onset))
    at_top = [w for w in raised if w.colour == colour]

    if at_top:
        hazards = list(dict.fromkeys(w.hazard for w in sorted(at_top, key=lambda w: w.onset)))
        value = f"Code {colour} · {', '.join(hazards)}"
        issued = min(at_top, key=lambda w: w.onset).issued
    else:
        # No time of issue: KNMI's green entries are issued days ahead, so their time
        # would read as stale. The read time (observed_at, note) is shown instead.
        hazards = []
        value = "No warnings"
        issued = None

    reading = _base_reading(read_at)
    reading.update(
        value=value,
        level=STATUS_LEVEL[colour],
        knmi_level=colour,
        hazards=hazards,
        issued_at=_iso(issued) if issued else None,
        note=f"Warnings at {read_at:%H:%M} · not live",
        warnings=[
            {
                "level": w.colour,
                "hazard": w.hazard,
                "onset": _iso(w.onset),
                "expires": _iso(w.expires) if w.expires else None,
                "issued_at": _iso(w.issued),
            }
            for w in raised
        ],
    )
    return reading


def no_data_reading(read_at: datetime) -> dict:
    """The reading when the feed couldn't be used: No data (spec §2.2)."""
    return _base_reading(_amsterdam(read_at))


def read_weather(fetcher: Fetcher, read_at: datetime) -> WeatherResult:
    """Fetch the feed once and make the reading. Never raises for a feed problem (hard rule 9)."""
    read_at = _amsterdam(read_at)
    try:
        response = fetcher.fetch(FEED_URL)
        _check_fresh(response.headers, read_at)
        try:
            data = json.loads(response.text())
        except ValueError:
            raise WeatherFeedError("not JSON (a bot-check or error page?)") from None
        return WeatherResult(reading_from_feed(data, read_at))
    except FetchError as error:
        problem = str(error)
    except WeatherFeedError as error:
        problem = f"{FEED_URL}: {error}"
    except Exception as error:  # a bug of ours must not stop the morning run
        problem = f"{FEED_URL}: unexpected error ({type(error).__name__}: {error})"
    return WeatherResult(no_data_reading(read_at), [{"source": FAILURE_SOURCE, "error": problem}])


# --- helpers --------------------------------------------------------------------------


def _base_reading(read_at: datetime) -> dict:
    return {
        "key": "weather",
        "label": "Weather warnings",
        "icon": "wind",
        "value": None,
        "level": None,
        "place": AREA_NAME,
        "knmi_level": None,
        "hazards": [],
        "issued_at": None,
        "warnings": [],
        "observed_at": _iso(read_at),
        "source_name": "KNMI via MeteoAlarm",
        "source_url": SITE_URL,
        "note": None,
    }


def _amsterdam(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("The time the feed was read has no timezone; it must be timezone-aware.")
    return moment.astimezone(AMSTERDAM)


def _iso(moment: datetime) -> str:
    return moment.astimezone(AMSTERDAM).isoformat(timespec="seconds")


def _alerts(data) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("warnings"), list):
        raise WeatherFeedError("not a MeteoAlarm warnings feed (no 'warnings' list)")
    alerts = []
    for entry in data["warnings"]:
        alert = entry.get("alert") if isinstance(entry, dict) else None
        if not isinstance(alert, dict) or not isinstance(alert.get("info"), list):
            raise WeatherFeedError("not a MeteoAlarm warnings feed (an entry has no 'alert' with 'info')")
        alerts.append(alert)
    return alerts


def _references(alert: dict) -> set[str]:
    """CAP references: space-separated 'sender,identifier,sent' triples -> the identifiers."""
    refs = alert.get("references")
    if not isinstance(refs, str):
        return set()
    return {parts[1] for parts in (ref.split(",") for ref in refs.split()) if len(parts) >= 2}


def _check_fresh(headers: dict, read_at: datetime) -> None:
    """The answer must be the server's own and recent: its Date within FRESH_WITHIN of read_at, and
    no cache Age over FRESH_WITHIN (#121). The feed has no time of its own, and in calm weather no
    entries at all, so the HTTP answer is what can tell."""
    try:
        served = parsedate_to_datetime(headers["date"])
    except (KeyError, TypeError, ValueError):
        raise WeatherFeedError("no Date in the answer: can't tell whether the feed is fresh") from None
    if served.tzinfo is None:
        raise WeatherFeedError("no Date in the answer: can't tell whether the feed is fresh")
    if abs(served - read_at) > FRESH_WITHIN:
        raise WeatherFeedError(f"not fresh: the answer is dated {_iso(served)}, read at {_iso(read_at)}")
    age = headers.get("age")
    if age is not None and (not age.strip().isdigit() or int(age) > FRESH_WITHIN.total_seconds()):
        raise WeatherFeedError(f"not fresh: a cache's copy, {age} s old")


def _port_info(alert: dict, points: list[tuple[float, float]]) -> dict | None:
    """The info block (English first) whose area covers any of our places, or None.

    Every area of every info block must have a readable polygon: without one we couldn't tell
    whether the warning covers the port (WeatherFeedError, so No data)."""
    matches = [info for info in alert["info"] if isinstance(info, dict) and _covers(info, points)]
    if not matches:
        return None
    english = [info for info in matches if str(info.get("language", "")).startswith("en")]
    return (english or matches)[0]


def _covers(info: dict, points: list[tuple[float, float]]) -> bool:
    areas = info.get("area")
    if not isinstance(areas, list) or not areas or not all(isinstance(a, dict) for a in areas):
        raise WeatherFeedError("an entry's area is not a list of areas")
    covered = False
    for area in areas:
        polygons = area.get("polygon")
        if not isinstance(polygons, list) or not polygons:
            raise WeatherFeedError("an entry's area has no polygon (feed shape changed?)")
        for polygon in polygons:
            ring = parse_polygon(polygon)
            covered = covered or any(contains(ring, lat, lon) for lat, lon in points)
    return covered


def parse_polygon(text) -> list[tuple[float, float]]:
    """A CAP polygon, "lat,lon lat,lon …", as (lat, lon) points. WeatherFeedError if unreadable."""
    if not isinstance(text, str):
        raise WeatherFeedError("unreadable polygon (not text)")
    points = []
    for pair in text.split():
        parts = pair.split(",")
        try:
            lat, lon = (float(part) for part in parts) if len(parts) == 2 else (None, None)
        except ValueError:
            lat = lon = None
        if lat is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise WeatherFeedError("unreadable polygon (a point is not 'lat,lon')")
        points.append((lat, lon))
    if len(set(points)) < 3:
        raise WeatherFeedError("unreadable polygon (fewer than 3 points)")
    return points


def contains(ring: list[tuple[float, float]], lat: float, lon: float) -> bool:
    """Whether the point lies inside the polygon (ray casting; the ring may be open or closed)."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        (lat_i, lon_i), (lat_j, lon_j) = ring[i], ring[j]
        if (lat_i > lat) != (lat_j > lat):
            crossing = lon_i + (lat - lat_i) * (lon_j - lon_i) / (lat_j - lat_i)
            if lon < crossing:
                inside = not inside
        j = i
    return inside


def _warning(alert: dict, info: dict) -> _Warning:
    parameters = {
        p.get("valueName"): p.get("value") for p in info.get("parameter") or [] if isinstance(p, dict)
    }
    colour = _part(parameters.get("awareness_level"), 1)
    colour = colour.lower() if colour else None
    if colour not in COLOURS:
        raise WeatherFeedError("unreadable awareness level in a warning for the port area")
    hazard = _part(parameters.get("awareness_type"), 1)
    hazard = hazard[:1].upper() + hazard[1:] if hazard else None
    if hazard is None and colour != "green":
        raise WeatherFeedError("unreadable hazard in a warning for the port area")
    issued = _time(alert.get("sent"))
    onset = _time(info.get("onset") or info.get("effective") or alert.get("sent"))
    expires = _time(info["expires"]) if info.get("expires") is not None else None
    return _Warning(colour=colour, hazard=hazard, onset=onset, expires=expires, issued=issued)


def _part(value, index: int) -> str | None:
    """'2; yellow; Moderate' -> part 1 = 'yellow'."""
    if not isinstance(value, str):
        return None
    parts = [p.strip() for p in value.split(";")]
    return parts[index] if len(parts) > index and parts[index] else None


def _time(value) -> datetime:
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise WeatherFeedError("unreadable time in a warning for the port area") from None
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise WeatherFeedError("unreadable time in a warning for the port area (no timezone)")
    return moment


def main() -> int:
    from haven.clock import now

    sys.stdout.reconfigure(encoding="utf-8")
    result = read_weather(Fetcher(), now())
    print(json.dumps(result.reading, indent=2, ensure_ascii=False))
    for failure in result.failures:
        print(f"FAILURE {failure['source']}: {failure['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
