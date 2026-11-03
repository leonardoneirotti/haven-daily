"""Strike flag: the status line's strike indicator, from stored items (spec §5.7, §2.2; issue #21).

No network and no AI: the summariser (#15) already put strike details on every item it
rated (`strike`: state, location, affects_rotterdam, start, end, match, strike_id). This
module only reads them back and applies the rules.

1. **Which items:** kept items (`filter.kept`) with strike details, collected **today or in the
   14 days before**, plus any strike whose `start` or `end` is today or later, **up to 60 days
   back** (so a strike announced 18 days ahead is still seen on its day). Once a strike counts,
   all its items of the 60 days count, so an older cancellation still cancels it.
2. **Same strike, several items:** grouped by `strike_id`; the **newest item wins** (latest
   collection day, then latest `published`, then later in the file).
3. **Level from the newest item** (§5.7 table), only for `affects_rotterdam: true`.
4. **Safety rule:** only a confident match (`new` / `same`) can lower a level. An `unsure` item
   that would lower it (or keep it) leaves the strike as it was and is shown next to it; one that
   would **raise** it counts as a strike of its own, shown next to the strike it might be.
5. **The flag** = worst level, Normal if none; AI unavailable → No data (§5.6).
6. **What is linked:** the deciding item of the worst strike (the newest one if several share
   the level), plus its unsure partner; on Normal, the newest confident cancellation, if any.

`flag_from_items(...)` is the pure logic; `read_strike_flag(...)` reads the stored days through
`haven.storage` and never raises (hard rule 9); `reading(...)` gives the §6 `status[]` entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from haven import storage
from haven.clock import AMSTERDAM
from haven.filter import age_start
from haven.summarise import published_day

FAILURE_SOURCE = "Strike flag"
WINDOW_DAYS = 14  # today + the 14 days before (the summariser's known strikes are those 14 days)
REACH_DAYS = 60  # strikes dated today or later are looked for this far back
FRESH_DAYS = 2  # "ongoing, no end date": Alert while the newest item is at most this old
STATES = ("announced", "ongoing", "cancelled")
MATCHES = ("new", "same", "unsure")
NO_AI_NOTE = "Can't be judged without the AI step."
# The public words of the reading (issue #84, design review S8): where the flag comes from.
PLACE = f"From the news of the last {WINDOW_DAYS} days"
NOTHING_LINKED = "Haven Daily's news sources"  # the source when no item is linked
UNREADABLE_DETAILS = "strike details unreadable (what kind of report, which strike, or whether it affects Rotterdam); item skipped"
_RANK = {None: 0, "amber": 1, "red": 2}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class _Report:
    """One kept item's strike details."""

    record: dict
    day: date  # the day it was collected
    order: tuple  # newest = largest
    state: str
    location: str | None
    rotterdam: bool
    start: date | None
    end: date | None
    match: str
    strike_id: str | None
    as_of: date  # its published day, else the day it was collected


@dataclass(frozen=True)
class _Judged:
    level: str | None  # "red" / "amber" / None (ignored)
    value: str | None  # the text shown for it
    deciding: _Report
    partner: _Report | None = None  # the other item of an unsure pair
    partner_role: str = "unsure"


@dataclass
class StrikeFlag:
    level: str | None  # "green" / "amber" / "red", None = No data
    value: str | None
    items: list[dict] = field(default_factory=list)  # deciding item(s), see _shown
    failures: list[dict] = field(default_factory=list)
    ai_unavailable: bool = False


@dataclass
class StrikeResult:
    reading: dict
    failures: list[dict] = field(default_factory=list)


# --- the flag --------------------------------------------------------------------------


def flag_from_items(days: list[tuple[date, list]], today: date, sources=(),
                    ai_unavailable: bool = False) -> StrikeFlag:
    """The strike flag for `today` from (collection day, records) pairs, in any order.

    `days` must include today's records (not stored yet when the runner calls this) and the
    stored days up to `REACH_DAYS` back; older days are ignored. `sources` gives source names.
    """
    if ai_unavailable:
        return StrikeFlag(None, None, ai_unavailable=True)
    failures: list[dict] = []
    reports = _reports(days, today, failures)
    names = {source.id: source.name for source in sources}

    groups: dict[str, list[_Report]] = {}
    unsure: list[_Report] = []
    lone: list[_Report] = []
    for report in reports:
        if report.strike_id is None:
            lone.append(report)  # no id to group by: a strike of its own (safe side)
        elif report.match == "unsure":
            unsure.append(report)
        else:
            groups.setdefault(report.strike_id, []).append(report)

    counted = {sid: max(members, key=lambda r: r.order) for sid, members in groups.items()
               if any(_in_reach(r, today) for r in members)}
    judged = {sid: _judge(newest, today) for sid, newest in counted.items()}
    strikes: list[_Judged] = [_judge(report, today) for report in lone if _in_reach(report, today)]

    for report in unsure:
        if not _in_reach(report, today):
            continue
        own = _judge(report, today)
        target = judged.get(report.strike_id)
        if target is None:
            if own.level is not None:
                strikes.append(own)
            continue
        if _RANK[own.level] > _RANK[target.level]:
            strikes.append(_Judged(own.level, own.value, report, target.deciding, "possibly the same as"))
        elif report.order > target.deciding.order and (target.partner is None
                                                       or report.order > target.partner.order):
            judged[report.strike_id] = _Judged(target.level, target.value, target.deciding, report)

    strikes.extend(judged.values())
    active = [s for s in strikes if s.level is not None]
    if active:
        worst = max(_RANK[s.level] for s in active)
        top = max((s for s in active if _RANK[s.level] == worst), key=lambda s: s.deciding.order)
        return StrikeFlag(top.level, top.value, _linked(top, today, names), failures)

    called_off = [s.deciding for s in judged.values()
                  if s.deciding.state == "cancelled" and s.deciding.rotterdam]
    if called_off:
        newest = max(called_off, key=lambda r: r.order)
        value = _with_location("Strike called off", newest)
        return StrikeFlag("green", value, [_shown(newest, "decides", today, names)], failures)
    return StrikeFlag("green", "No active strike", [], failures)


def _judge(report: _Report, today: date) -> _Judged:
    """A strike's level and text from its newest item (§5.7 table)."""
    def judged(level, text):
        return _Judged(level, _with_location(text, report) if level else None, report)

    if not report.rotterdam or report.state == "cancelled":
        return judged(None, None)
    if report.end is not None and report.end < today:
        return judged(None, None)  # over
    if report.state == "ongoing":
        if report.end is not None:
            return judged("red", "Strike ongoing")
        return _no_end(report, today, "Strike ongoing", f"Strike ongoing as of {_day(report.as_of)}")
    # announced
    if report.start is not None and report.start > today:
        return judged("amber", f"Strike announced for {_day(report.start)}")
    if report.start == today or (report.start is not None and report.end is not None):
        return judged("red", "Strike today")  # dates include today
    if report.start is not None:  # started before today, no end given: read as ongoing
        text = f"Strike since {_day(report.start)}"
        return _no_end(report, today, text, text)
    if report.end is not None:
        return judged("amber", f"Strike announced until {_day(report.end)}")
    return judged("amber", "Strike announced, no date given")


def _no_end(report: _Report, today: date, fresh: str, stale: str) -> _Judged:
    if (today - report.as_of).days <= FRESH_DAYS:
        return _Judged("red", _with_location(fresh, report), report)
    return _Judged("amber", _with_location(f"{stale}, no newer report", report), report)


def _in_reach(report: _Report, today: date) -> bool:
    if (today - report.day).days <= WINDOW_DAYS:
        return True
    return any(d is not None and d >= today for d in (report.start, report.end))


def _linked(top: _Judged, today: date, names: dict) -> list[dict]:
    items = [_shown(top.deciding, "decides", today, names)]
    if top.partner is not None:
        items.append(_shown(top.partner, top.partner_role, today, names))
    return items


def _shown(report: _Report, role: str, today: date, names: dict) -> dict:
    """What the status line needs to link an item (§5.7 point 6)."""
    record = report.record
    return {
        "headline": record.get("headline"),
        "url": record.get("url"),
        "source": names.get(record.get("source"), record.get("source")),
        "published": record.get("published"),
        "day": report.day.isoformat(),
        "day_page": None if report.day == today else f"days/{report.day.isoformat()}.html",
        "role": role,
        "state": report.state,
        "match": report.match,
    }


# --- reading the records ---------------------------------------------------------------


def _reports(days, today: date, failures: list[dict]) -> list[_Report]:
    reports = []
    for day, records in days:
        if not 0 <= (today - day).days <= REACH_DAYS:
            continue
        for position, record in enumerate(records or ()):
            if not isinstance(record, dict) or not isinstance(record.get("strike"), dict):
                continue
            if not (isinstance(record.get("filter"), dict) and record["filter"].get("kept") is True):
                continue
            report = _report(record, day, position, failures)
            if report is not None:
                reports.append(report)
    return reports


def _report(record: dict, day: date, position: int, failures: list[dict]) -> _Report | None:
    details = record["strike"]
    where = f"item {position + 1} of {day.isoformat()}"
    state, match = details.get("state"), details.get("match")
    if state not in STATES or match not in MATCHES or not isinstance(details.get("affects_rotterdam"), bool):
        failures.append({"source": FAILURE_SOURCE,
                         "error": f"{where}: {UNREADABLE_DETAILS}"})
        return None
    start = _date(details.get("start"), "start", where, failures)
    end = _date(details.get("end"), "end", where, failures)
    moment = age_start(record.get("published"))
    location = details.get("location")
    strike_id = details.get("strike_id")
    return _Report(
        record=record,
        day=day,
        order=(day, moment is not None, moment.timestamp() if moment else 0.0, position),
        state=state,
        location=location if isinstance(location, str) and location.strip() else None,
        rotterdam=details["affects_rotterdam"],
        start=start,
        end=end,
        match=match,
        strike_id=strike_id if isinstance(strike_id, str) and strike_id else None,
        as_of=published_day(record.get("published")) or day,
    )


def _date(value, key: str, where: str, failures: list[dict]) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        failures.append({"source": FAILURE_SOURCE,
                         "error": f"{where}: strike {key} date unreadable; read as no date"})
        return None


def _day(day: date) -> str:
    return f"{day.day} {_MONTHS[day.month - 1]}"


def _with_location(text: str, report: _Report) -> str:
    return f"{text} · {report.location}" if report.location else text


# --- the status reading, and the stored days -------------------------------------------


def reading(flag: StrikeFlag, observed_at: datetime) -> dict:
    """The §6 `status[]` entry. `source_name`/`source_url` are the first linked item's."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at has no timezone; it must be timezone-aware.")
    first = flag.items[0] if flag.items else None
    return {
        "key": "strike",
        "label": "Strike flag",
        "icon": "megaphone",
        "value": flag.value,
        "level": flag.level,
        "place": PLACE,
        "items": list(flag.items),
        "observed_at": observed_at.astimezone(AMSTERDAM).isoformat(timespec="seconds"),
        "source_name": first["source"] if first else NOTHING_LINKED,
        "source_url": first["url"] if first else None,
        "note": NO_AI_NOTE if flag.ai_unavailable else None,
    }


def read_strike_flag(today_records: list, today: date, observed_at: datetime, sources=(),
                     ai_unavailable: bool = False, data_dir: Path = storage.DATA_DIR) -> StrikeResult:
    """The flag from today's records plus the stored items of the 60 days before. Never raises.

    `observed_at` is the time the sources were read (the runner passes `feeds_read_at`).
    """
    if ai_unavailable:
        return StrikeResult(reading(StrikeFlag(None, None, ai_unavailable=True), observed_at))
    try:
        stored = storage.read_recent("items", before=today, days=REACH_DAYS, data_dir=data_dir)
        flag = flag_from_items([(today, today_records), *stored], today, sources)
    except Exception as error:  # a broken file or a bug of ours must not stop the run (rule 9)
        problem = f"stored items could not be read ({type(error).__name__}: {error})"
        failed = StrikeFlag(None, None, failures=[{"source": FAILURE_SOURCE, "error": problem}])
        return StrikeResult(reading(failed, observed_at), failed.failures)
    return StrikeResult(reading(flag, observed_at), flag.failures)
