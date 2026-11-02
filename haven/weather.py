"""Weather status: KNMI's warnings for Zuid-Holland, read via MeteoAlarm (spec §2.2, §4; issue #18).

One request a morning to MeteoAlarm's Netherlands feed (JSON, no key; robots.txt allows
bots). It republishes KNMI's own warnings: one entry per warning *version*, per province
and per hazard, including KNMI's daily "green" (no warning) entries.

The reading:
- **Which warnings count:** Zuid-Holland (EMMA_ID `NL009`), real messages only
  (`status` Actual), the newest version of each warning only (a version named in another
  message's `references` has been replaced by an Update or withdrawn by a Cancel), and only
  those **valid at some moment from when the feed was read until midnight** (Amsterdam
  date). A warning that already expired this morning, or starts tomorrow, doesn't count
  (owner's decision, 2 Nov 2026).
- **Level:** the highest one decides: green → Normal (`green`), yellow → Watch (`amber`),
  orange/red → Alert (`red`).
- **What is kept** for the display MeteoAlarm requires: "KNMI" as the source, the time of
  issue, KNMI's own level and hazard (e.g. Code yellow · Wind), onset/expiry, a link to
  www.meteoalarm.org and "not live". **Never the warning text** (headline, description).
  With no warnings there is no time of issue, only the read time (owner, 2 Nov 2026).

Any doubt is "No data", never a guess (spec §2.2): the feed down or blocked, not JSON, not
the warnings feed, no Zuid-Holland entry for today at all (an empty answer could hide a
renamed area), or an unreadable level, hazard or time in a Zuid-Holland warning. Then the
reading has `value`/`level` `null` and one failure line goes to build.failures.

`python -m haven.weather` reads the live feed once and prints the reading; it writes nothing.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from haven.clock import AMSTERDAM
from haven.fetch import Fetcher, FetchError

FEED_URL = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands"
SITE_URL = "https://www.meteoalarm.org"
FAILURE_SOURCE = "Weather warnings (MeteoAlarm)"

AREA_CODE = "NL009"  # EMMA_ID of the province; the area MeteoAlarm calls "Zuid-Holland"
AREA_NAME = "Zuid-Holland"

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


def reading_from_feed(data, read_at: datetime) -> dict:
    """The status reading for the moment `read_at`. Raises WeatherFeedError on any doubt."""
    read_at = _amsterdam(read_at)
    entries = _alerts(data)
    replaced = {ref for alert in entries if alert.get("status") == "Actual" for ref in _references(alert)}
    end_of_today = datetime.combine(read_at.date() + timedelta(days=1), time(0), AMSTERDAM)

    valid: list[_Warning] = []
    for alert in entries:
        if alert.get("status") != "Actual" or alert.get("msgType") not in COUNTED_MESSAGES:
            continue
        if alert.get("identifier") in replaced:
            continue
        info = _zuid_holland_info(alert)
        if info is None:
            continue
        found = _warning(alert, info)
        if found.onset < end_of_today and (found.expires is None or found.expires > read_at):
            valid.append(found)

    if not valid:
        raise WeatherFeedError(f"no {AREA_NAME} entry for today in the feed (area renamed or feed changed?)")

    top = max(COLOURS.index(w.colour) for w in valid)
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


def _zuid_holland_info(alert: dict) -> dict | None:
    """The info block (English first) whose area is Zuid-Holland, or None."""
    matches = [info for info in alert["info"] if isinstance(info, dict) and _is_zuid_holland(info)]
    if not matches:
        return None
    english = [info for info in matches if str(info.get("language", "")).startswith("en")]
    return (english or matches)[0]


def _is_zuid_holland(info: dict) -> bool:
    for area in info.get("area") or []:
        if not isinstance(area, dict):
            continue
        if area.get("areaDesc") == AREA_NAME:
            return True
        for code in area.get("geocode") or []:
            if isinstance(code, dict) and code.get("value") == AREA_CODE:
                return True
    return False


def _warning(alert: dict, info: dict) -> _Warning:
    parameters = {
        p.get("valueName"): p.get("value") for p in info.get("parameter") or [] if isinstance(p, dict)
    }
    colour = _part(parameters.get("awareness_level"), 1)
    colour = colour.lower() if colour else None
    if colour not in COLOURS:
        raise WeatherFeedError(f"unreadable awareness level in a {AREA_NAME} warning")
    hazard = _part(parameters.get("awareness_type"), 1)
    hazard = hazard[:1].upper() + hazard[1:] if hazard else None
    if hazard is None and colour != "green":
        raise WeatherFeedError(f"unreadable hazard in a {AREA_NAME} warning")
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
        raise WeatherFeedError(f"unreadable time in a {AREA_NAME} warning") from None
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise WeatherFeedError(f"unreadable time in a {AREA_NAME} warning (no timezone)")
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
