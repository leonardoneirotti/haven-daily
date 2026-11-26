"""Render the Haven Daily static site from daily brief files.

A brief is one JSON file per day (see data/sample/briefs/ for the format).
This module only turns briefs into HTML. Collecting, filtering, summarising and
the AIS snapshot happen in earlier steps of the pipeline.

Usage, from the project folder:
    python -m haven.render --out site                             # real briefs, or the samples if none yet
    python -m haven.render --briefs data/sample/briefs --out site  # the samples, always
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date, datetime, timedelta
from itertools import groupby
from pathlib import Path
from urllib.parse import urlencode, urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from haven import filter as haven_filter
from haven import strike as haven_strike
from haven import summarise
from haven.clock import AMSTERDAM
from haven.config import (CONFIG_DIR, RhineMeanings, RhineThresholds, SiteConfig, Source, load_rhine,
                          load_rhine_meanings, load_site, load_sources, preview_image_size)
from haven.feeds import LEAD_PARAGRAPH_FEEDS
from haven.flags import FLAGS, SOURCE as FLAG_SOURCE

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_DIR / "templates"
STATIC_DIR = PROJECT_DIR / "static"

# The owner's one identity sentence, used everywhere he is described (owner, #138): the footer of
# every page, the Today page's About block, "Who makes this" on How it works, and the README.
IDENTITY = ("Second-year International Business student (Supply Chain Management) "
            "at Rotterdam University of Applied Sciences.")

SITE = {
    "name": "Haven Daily",
    "author": "Leonardo Neirotti",
    # The owner's own words (spec §7.8, #86): used exactly, so they live here once.
    "tagline": ("What affects the Port of Rotterdam today, and what it means for logistics planners. "
                "Updated every morning."),
    # The page description search engines show, on every page (owner, 3 Nov 2026, PR #93).
    "description": ("What affects the Port of Rotterdam today, and what it means for logistics planners. "
                    "Independent, unofficial portfolio project."),
    # Who the owner is now has one sentence of its own (IDENTITY, #138), shown under the name.
    "about": ("Haven Daily is an independent portfolio project by Leonardo Neirotti. Every morning an automated "
              "pipeline reads public sources, uses AI to filter and summarise what matters for logistics planners, "
              "and publishes this brief. It is not affiliated with the Port of Rotterdam Authority or any company "
              "named here."),
    "identity": IDENTITY,
    # Under the About text in "Who makes this" (owner, 3 Nov 2026, PR #93; the identity moved out, #138).
    "built_by": "Built with Python and GitHub Actions.",
    # The site's addresses (base URL, LinkedIn, repository) are in config/site.toml (#28);
    # make_environment adds them to `site` for the templates.
}

# The sample-data note's words (base.html shows them on sample pages; hard rule 10). A sample day
# page's preview description says the same, so a shared link can't pass invented news as real.
SAMPLE_NOTE = "Sample data. The ships, news and readings on this page are invented to preview the design."
QUIET_DAY = "Nothing significant on this day. The port status still applies."
PREVIEW_SIZE = (1200, 630)  # og:image, the size LinkedIn shows uncropped (§7.7)

MAX_ITEMS = 5
# Ship positions (the AIS snapshot) come in v2 (#31). Until then a brief without ships says
# they are not collected yet, not that a snapshot failed. Set to True when #31 is built.
AIS_SNAPSHOT_BUILT = False
# MeteoAlarm's disclaimer, verbatim (its Terms §5, spec §2.2): shown with the weather dial.
METEOALARM_DISCLAIMER = (
    "Time delays between this website and the www.meteoalarm.org website are possible. For the most "
    "up-to-date awareness information as published by the participating National Meteorological and "
    "Hydrological Services, please refer to www.meteoalarm.org."
)
# Method page (issue #24): where the Rhine thresholds in config/rhine.toml come from (spec §2.2).
PEGELONLINE_KAUB_URL = (
    "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/KAUB/W.json?includeCharacteristicValues=true"
)
RHINE_LOW_SOURCES = (
    {"name": "Contargo low-water surcharge", "url": "https://www.contargo.net/en/goodtoknow/lws"},
    {"name": "Maersk Rhine low water surcharge",
     "url": "https://www.maersk.com/news/articles/2026/07/09/rhine-river-low-water-surcharge"},
)
RHINE_SOURCES_READ = "2 Nov 2026"  # low side; the high side was read 31 Oct 2026 (config/rhine.toml)
# How the Method page names the models the pipeline calls. A model id missing here stops the
# build (KeyError), so a model change in filter.py or summarise.py can't leave the page out of date.
MODEL_NAMES = {
    "claude-haiku-5-5": "Claude Haiku 5.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-opus-5-5": "Claude Opus 5.5",
}
SOURCE_GROUPS = (
    ("use", "Summarised"),
    ("headline-only", "Headline and link only"),
    ("drop", "Not used"),
)

SEVERITIES = ("high", "medium", "low")
# severity null = unrated: the AI failed for that item (spec §2.1, §5.6). It sorts after
# every rated item and still counts toward MAX_ITEMS. "unrated" is its CSS key.
UNRATED = "unrated"
SEVERITY_KEYS = SEVERITIES + (UNRATED,)
LANGUAGE_NAMES = {"en": "English", "nl": "Dutch", "de": "German"}

# What the chart shows first. Wide screens: the whole port, from the anchorages to
# Rotterdam city, to the right of the news panel. Phones: the western port, from
# the anchorage to Europoort.
MAP_VIEW_HOME = {"south": 51.845, "west": 3.76, "north": 52.07, "east": 4.58}
MAP_VIEW_COMPACT = {"south": 51.84, "west": 3.74, "north": 52.08, "east": 4.26}

# Ships seen from above, bow up, 24 units long and 6 wide (static/map.js turns them
# to their heading and scales them). The deck shows the type: container stacks,
# a tanker's pipeline and manifold, a bulk carrier's hatch covers. The block near
# the stern is the bridge.
SHIP_HULL = "M0,-12C2.2,-9 3,-6 3,-2.5V10.5Q3,11.8 1.8,11.8H-1.8Q-3,11.8 -3,10.5V-2.5C-3,-6 -2.2,-9 0,-12Z"
SHIP_DECKS = {
    "container": "M-2.1,-8.6h4.2v2.3h-4.2zM-2.1,-5.8h4.2v2.3h-4.2zM-2.1,-3h4.2v2.3h-4.2z"
    "M-2.1,-0.2h4.2v2.3h-4.2zM-2.1,2.6h4.2v2.3h-4.2zM-2.6,6.4h5.2v2.6h-5.2z",
    "tanker": "M-0.4,-9h0.8v15h-0.8zM-2.2,-1.8h4.4v1h-4.4zM-2.6,7.2h5.2v2.8h-5.2z",
    "bulk": "M-1.7,-8h3.4v2.6h-3.4zM-1.7,-4.6h3.4v2.6h-3.4zM-1.7,-1.2h3.4v2.6h-3.4z"
    "M-1.7,2.2h3.4v2.6h-3.4zM-2.6,7.2h5.2v2.8h-5.2z",
}

# Status colour as stored (the green/amber/red wording from CLAUDE.md)
# -> CSS key and the word shown next to the colour.
LEVELS = {
    "green": ("ok", "Normal"),
    "amber": ("watch", "Watch"),
    "red": ("alert", "Alert"),
    None: ("nodata", "No data"),
}
# What a weather or strike level means for a planner, shown next to the level (design review S6,
# issue #83): one constant, never written per day. The Rhine's meanings sit next to its
# thresholds in config/rhine.toml. No data has none: it shows only "No data".
# Wording confirmed by the owner 3 Nov 2026 (PR #89), Normal texts changed by the owner.
STATUS_MEANINGS = {
    "weather": {
        "green": "no KNMI warning for the port area for the rest of today",
        "amber": "weather may slow port operations and road transport today",
        "red": "weather likely to disrupt port operations and road transport today",
    },
    "strike": {
        # The window: news kept today and in the 14 days before; Normal = none of it reports a
        # Rotterdam strike on today (or ongoing) or announced for a later day (spec §5.7).
        "green": f"no Rotterdam strike today or coming up, in the news of the last {haven_strike.WINDOW_DAYS} days",
        "amber": "no strike confirmed for today; check the dates",
        "red": "a strike is on today",
    },
}

# The archive's status icons, as short text labels on phones (design review S9, issue #84): a
# mouse-over `title` alone shows nothing on a touch screen. An indicator not listed here shows
# its own label.
STATUS_SHORT_LABELS = {"weather": "Weather", "rhine": "Rhine", "strike": "Strike"}

# Shape carries the meaning as well as colour: octagon = act now, triangle = keep an eye on it.
LEVEL_ICONS = {
    "ok": "circle-check",
    "watch": "triangle-alert",
    "alert": "octagon-alert",
    "nodata": "circle-minus",
}

SHIP_TYPES = {"container": "Container ship", "tanker": "Tanker", "bulk": "Bulk carrier"}
SHIP_TYPE_PLURALS = {"container": "Container", "tanker": "Tanker", "bulk": "Bulk"}
SHIP_STATUS = {"underway": "Under way", "moored": "Moored", "anchored": "At anchor"}
FLAG_NAMES = {
    "BS": "Bahamas", "CY": "Cyprus", "DK": "Denmark", "GR": "Greece", "HK": "Hong Kong",
    "LR": "Liberia", "MH": "Marshall Islands", "MT": "Malta", "NL": "Netherlands",
    "PA": "Panama", "PT": "Portugal", "SG": "Singapore",
}

# Inner SVG markup of Lucide icons (lucide.dev, ISC licence), drawn on a 24x24 grid.
ICONS = {
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/>'
    '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "octagon-alert": '<path d="M12 16h.01"/><path d="M12 8v4"/>'
    '<path d="M15.312 2a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 '
    "1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586l-4.688-4.688A2 2 0 0 1 2 "
    '15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2z"/>',
    "triangle-alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
    '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "circle-check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "circle-minus": '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
    "wind": '<path d="M12.8 19.6A2 2 0 1 0 14 16H2"/><path d="M17.5 8a2.5 2.5 0 1 1 2 4H2"/>'
    '<path d="M9.8 4.4A2 2 0 1 1 11 8H2"/>',
    "waves": '<path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>'
    '<path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>'
    '<path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>',
    "megaphone": '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    "ship": '<path d="M12 10.189V14"/><path d="M12 2v3"/><path d="M19 13V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6"/>'
    '<path d="M19.38 20A11.6 11.6 0 0 0 21 14l-8.188-3.639a2 2 0 0 0-1.624 0L3 14a11.6 11.6 0 0 0 2.81 7.76"/>'
    '<path d="M2 21c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1s1.2 1 2.5 1c2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>',
    "languages": '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/>'
    '<path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
    "map-pin": '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/>'
    '<circle cx="12" cy="10" r="3"/>',
    "anchor": '<path d="M12 22V8"/><path d="M5 12H2a10 10 0 0 0 20 0h-3"/><circle cx="12" cy="5" r="3"/>',
    "expand": '<path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="m21 3-7 7"/><path d="m3 21 7-7"/>',
    "arrow-left": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "pencil": '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 '
    '.623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
}


def long_date(day: date) -> str:
    """Thursday 29 October 2026"""
    return f"{day:%A} {day.day} {day:%B %Y}"


def date_only(day: date) -> str:
    """29 October 2026"""
    return f"{day.day} {day:%B %Y}"


def short_date(day: date) -> str:
    """Thu 29 Oct"""
    return f"{day:%a} {day.day} {day:%b}"


def clock(timestamp: str) -> str:
    """Local clock time from an ISO timestamp, e.g. 06:31."""
    return datetime.fromisoformat(timestamp).strftime("%H:%M")


def amsterdam_time(timestamp: str) -> datetime:
    """An ISO timestamp as Amsterdam time. A timestamp without a zone is refused, never guessed."""
    moment = datetime.fromisoformat(timestamp)
    if moment.tzinfo is None:
        raise ValueError(f"Timestamp {timestamp!r} has no timezone; write it with its offset, e.g. +01:00.")
    return moment.astimezone(AMSTERDAM)


def correction_time(at: str, built_at: str) -> str:
    """When a correction was made: "09:14", or "30 Oct 09:14" if it was on a later day than the build."""
    moment = amsterdam_time(at)
    if moment.date() == amsterdam_time(built_at).date():
        return f"{moment:%H:%M}"
    return f"{moment.day} {moment:%b %H:%M}"


def latest_correction(corrections: list[dict]) -> dict | None:
    """The most recent correction by its time (not its place in the list), or None."""
    return max(corrections, key=lambda c: amsterdam_time(c["at"]), default=None)


def publication_line(built_at: str, corrections: list[dict]) -> str:
    """ "Published 06:52 · Amsterdam time", plus "Corrected 09:14" after a correction (spec §2.3)."""
    parts = [f"Published {amsterdam_time(built_at):%H:%M}"]
    latest = latest_correction(corrections)
    if latest:
        parts.append(f"Corrected {correction_time(latest['at'], built_at)}")
    parts.append("Amsterdam time")
    return " · ".join(parts)


def _day_month(day: date) -> str:
    """5 Nov (no locale, like the strike flag's value texts)."""
    return f"{day.day} {day:%b}"


def _moment(value) -> datetime | None:
    """A timestamp as Amsterdam time; a zone-less one is read as Amsterdam time (as the filter does,
    spec §5.4). None for anything unreadable: the page then shows no time rather than a guess."""
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.replace(tzinfo=AMSTERDAM) if moment.tzinfo is None else moment.astimezone(AMSTERDAM)


def _date(value) -> date | None:
    """The Amsterdam date of a timestamp, or a date-only value as it is."""
    moment = _moment(value)
    if moment is not None:
        return moment.date()
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _time_on(moment: datetime, brief_date: str) -> str:
    """ "05:12" on the brief's own day, "19 Nov 21:30" on another day."""
    if moment.date() == date.fromisoformat(brief_date):
        return f"{moment:%H:%M}"
    return f"{_day_month(moment.date())} {moment:%H:%M}"


def published_label(published, brief_date: str) -> str | None:
    """When an item was published, as shown on its card (Amsterdam time; the date too if not the brief's day)."""
    moment = _moment(published)
    if moment is not None:
        return _time_on(moment, brief_date)
    day = _date(published)
    return _day_month(day) if day else None


def weather_mapping(indicator: dict) -> str | None:
    """KNMI's own level and hazard next to ours (MeteoAlarm requirement, spec §2.2):
    "KNMI: Code yellow · Wind → Watch". None on No data or a reading without KNMI's level."""
    knmi_level = indicator.get("knmi_level")
    if not knmi_level or indicator.get("level") is None:
        return None
    hazards = ", ".join(indicator.get("hazards") or [])
    original = f"Code {knmi_level}" + (f" · {hazards}" if hazards else "")
    return f"KNMI: {original} → {LEVELS[indicator['level']][1]}"


def issue_time(issued_at, brief_date: str) -> str | None:
    """The warning's time of issue (MeteoAlarm requirement); None when there are no warnings (§5.11 point 6)."""
    moment = _moment(issued_at)
    return f"Issued {_time_on(moment, brief_date)}" if moment else None


STRIKE_ROLES = {"decides": None, "possibly the same as": "Possibly the same as"}


def strike_link(link: dict, ranks: dict[str, int] | None, today: str) -> dict:
    """One item linked from the strike line (spec §5.7 point 6): role, "NL Times · 2 Nov", and the
    item's card on the day page it appeared on, if that day's brief shows it.

    `ranks` = {url: rank} of the items shown on the item's collection day, None if that day has no brief.
    """
    role = link.get("role")
    if role == "unsure":
        label = "Possibly called off" if link.get("state") == "cancelled" else "Possibly the same strike"
    else:
        label = STRIKE_ROLES.get(role)
    day = _date(link.get("published")) or _date(link.get("day"))
    meta = " · ".join(part for part in (link.get("source"), _day_month(day) if day else None) if part)
    rank = (ranks or {}).get(link.get("url"))
    day_link = None
    if link.get("day") and link["day"] != today and rank:
        day_link = {"href": f"days/{link['day']}.html#item-{rank}",
                    "label": f"In the {_day_month(date.fromisoformat(link['day']))} brief"}
    return {"headline": link_title(link), "url": outside_url(link.get("url")), "role_label": label, "meta": meta,
            "day_link": day_link}


def link_title(link: dict) -> str | None:
    """A strike link's title, always English (#153): the item's own, its English title, or a plain
    line naming the source (an item in Dutch without one, e.g. rated from its headline)."""
    if (link.get("language") or "en") == "en":
        return link.get("headline")
    if link.get("headline_en"):
        return link["headline_en"]
    name = LANGUAGE_NAMES.get(link.get("language"), link.get("language"))
    return f"An item from {link.get('source') or 'a source'} (in {name})"


# Failure notes for readers (#138). The stored brief keeps the technical line ("<address>: HTTP 403"),
# which the owner needs to fix things; the page turns it into one plain sentence naming the source.
# A line the rules don't recognise keeps its own words, without the address.
_ADDRESS = re.compile(r"^(https?://\S+?): (.+)$", re.S)
_UNREACHABLE = re.compile(r"^HTTP \d{3}\b|timed out|tried twice|network error|redirects|robots\.txt could not be read",
                          re.I)
_ROBOTS_BLOCK = re.compile(r"^robots\.txt (disallows|asks for)")
_CHANGED = re.compile(r"layout changed|feed changed|feed shape changed|area renamed|not RSS|no <channel>|Atom feed|"
                      r"not valid XML|not JSON|not a MeteoAlarm|without a headline or link", re.I)
_FAULT = re.compile(r"^unexpected error")
FAILURE_SENTENCES = {
    "unreachable": "{name} could not be reached today.",
    "robots": "{name} was not read today: its website asks automated readers not to visit.",
    "changed": "{name} could not be read today: its {kind} has changed.",
    "fault": "{name} could not be read today because of a fault in Haven Daily.",
    "article": "One {name} article could not be opened, so that item has no summary.",
}


def _source_reads() -> dict[str, tuple[tuple[str, ...], str | None]]:
    """{source name: (the addresses the job reads, access)} from config/sources.toml."""
    return {source.name: (source.urls, source.access) for source in load_sources()}


def plain_failure(failure: dict, reads: dict | None = None) -> str:
    """One failure line as a reader should see it (#138): no addresses, no status codes."""
    reads = _source_reads() if reads is None else reads
    name = failure.get("source") or "Unknown step"
    error = (failure.get("error") or "").strip()
    match = _ADDRESS.match(error)
    url, problem = (match.group(1), match.group(2).strip()) if match else (None, error)
    urls, access = reads.get(name, ((), None))
    article = bool(url and urls and url not in urls)  # an article page, not the list or feed itself
    if _FAULT.match(problem):
        kind = "fault"
    elif _ROBOTS_BLOCK.match(problem):
        kind = "robots"
    elif _UNREACHABLE.search(problem):
        kind = "article" if article else "unreachable"
    elif _CHANGED.search(problem):
        kind = "article" if article else "changed"
    else:
        return f"{name}: {problem.rstrip('.')}."
    return FAILURE_SENTENCES[kind].format(name=name, kind="page" if access == "html" else "feed")


def failure_lines(failures: list[dict], reads: dict | None = None) -> list[str]:
    """Every failure as a plain sentence, each sentence once, in the order they first appear."""
    reads = _source_reads() if reads is None else reads
    return list(dict.fromkeys(plain_failure(failure, reads) for failure in failures))


def outside_url(url) -> str | None:
    """The link itself when it is an http(s) address, else None: then the page shows the text with no
    link (#125). The collectors already keep only http(s) links (haven/feeds.py, haven/pages.py); this
    checks again when the page is built, so a hand-edited brief (a correction) or a future collector
    can never put a `javascript:` or `data:` link on the page."""
    if not isinstance(url, str):
        return None
    parts = urlparse(url)
    if url != url.strip() or parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return url


def translate_url(url: str, source_language: str) -> str:
    """Link that opens the original article through Google Translate.

    We link to the translation instead of storing one: the page never
    republishes someone else's article text.
    """
    query = urlencode({"sl": source_language, "tl": "en", "u": url})
    return f"https://translate.google.com/translate?{query}"


def severity_key(severity: str | None) -> str:
    """CSS key and sort key for a severity: "high", "medium", "low", or "unrated" for null."""
    return UNRATED if severity is None else severity


def rank_items(items: list[dict]) -> list[dict]:
    """Most severe first, unrated last, at most MAX_ITEMS. Quiet days stay short: never pad.

    Within a severity, items with a summary (full-text sources) come before headline-only ones
    (owner, 24 Nov 2026, #123): a summary tells a planner more. The sort is stable, so otherwise
    items keep the order they came in.
    """
    ranked = sorted((item for item in items if has_english_title(item)),
                    key=lambda item: (SEVERITY_KEYS.index(severity_key(item["severity"])), not item.get("summary")))
    return ranked[:MAX_ITEMS]


def has_english_title(item: dict) -> bool:
    """Every title on the site is English (#153, owner 26 Nov 2026): an item in another language is
    shown only with the English title written from Haven Daily's summary. One without (a Dutch
    headline-only or unrated item) is not shown at all."""
    return (item.get("language") or "en") == "en" or bool(item.get("headline_en"))


def describe_change(indicator: dict, previous: dict | None, is_first: bool) -> str | None:
    """One line comparing today's status value with the previous brief."""
    now = indicator["value"]
    if now is None:
        return None
    if is_first:
        return "First reading"
    if previous is None or previous["value"] is None:
        return "No reading yesterday"
    before = previous["value"]
    if isinstance(now, (int, float)) and isinstance(before, (int, float)):
        diff = now - before
        if diff == 0:
            return "Unchanged since yesterday"
        sign = "+" if diff > 0 else "−"
        return f"{sign}{abs(diff):g} {indicator['unit']} since yesterday".replace("  ", " ")
    if now == before:
        return "Same as yesterday"
    return f"Yesterday: {before}"


def gauge_percent(indicator: dict) -> float | None:
    """How full the little river gauge is drawn, from 0 to 100."""
    gauge_max = indicator.get("gauge_max")
    value = indicator["value"]
    if not gauge_max or not isinstance(value, (int, float)):
        return None
    return round(max(0.0, min(value / gauge_max, 1.0)) * 100, 1)


def status_meaning(indicator: dict, thresholds: RhineThresholds, meanings: RhineMeanings) -> str | None:
    """What the level means for a planner (design review S6, issue #83), or None on No data.

    The Rhine's text comes from config/rhine.toml. Watch and Alert have a low and a high side; the
    side is read from the value (below or above the middle of the Normal band), so a reading
    stored under older thresholds still gets the right side's text."""
    level = indicator.get("level")
    if level is None or indicator.get("value") is None:
        return None
    if indicator["key"] == "rhine":
        if level == "green":
            return meanings.normal
        low = indicator["value"] < (thresholds.watch_at_or_below + thresholds.watch_above) / 2
        if level == "amber":
            return meanings.watch_low if low else meanings.watch_high
        return meanings.alert_low if low else meanings.alert_high
    return STATUS_MEANINGS.get(indicator["key"], {}).get(level)


def gauge_marks(indicator: dict, thresholds: RhineThresholds) -> list[dict]:
    """Watch and Alert lines on the Kaub gauge, at the thresholds in config/rhine.toml (design
    review S7, issue #83), lowest first. A threshold above the top of the gauge is left out."""
    gauge_max = indicator.get("gauge_max")
    if indicator.get("key") != "rhine" or not gauge_max or indicator.get("value") is None:
        return []
    lines = (
        (thresholds.alert_at_or_below, "alert"),
        (thresholds.watch_at_or_below, "watch"),
        (thresholds.watch_above, "watch"),
        (thresholds.alert_above, "alert"),
    )
    return [{"cm": cm, "level_key": key, "percent": round(cm / gauge_max * 100, 1)}
            for cm, key in lines if cm <= gauge_max]


def gauge_label(indicator: dict, thresholds: RhineThresholds) -> str:
    """What the gauge shows, for screen readers: the reading and where the lines are."""
    unit = indicator["unit"]
    return (
        f"Gauge: {indicator['display_value']} {unit} on a scale of 0 to {indicator['gauge_max']} {unit}. "
        f"Watch at {thresholds.watch_at_or_below} {unit} or below and above {thresholds.watch_above} {unit}; "
        f"Alert at {thresholds.alert_at_or_below} {unit} or below and above {thresholds.alert_above} {unit}."
    )


def prepare_indicator(indicator: dict, previous: dict | None, is_first: bool, brief_date: str,
                      shown_ranks: dict[str, dict[str, int]], thresholds: RhineThresholds,
                      meanings: RhineMeanings) -> None:
    indicator.setdefault("value", None)
    indicator.setdefault("unit", "")
    indicator.setdefault("place", None)
    indicator.setdefault("note", None)
    indicator.setdefault("observed_at", None)
    indicator.setdefault("gauge_max", None)
    indicator.setdefault("source_url", None)  # null when nothing is linked (strike flag, §5.7)
    indicator["level_key"], indicator["level_label"] = LEVELS[indicator.get("level")]
    indicator["short_label"] = STATUS_SHORT_LABELS.get(indicator["key"], indicator["label"])
    value = indicator["value"]
    indicator["is_number"] = isinstance(value, (int, float))
    indicator["display_value"] = f"{value:g}" if indicator["is_number"] else value
    indicator["change"] = describe_change(indicator, previous, is_first)
    indicator["gauge_pct"] = gauge_percent(indicator)
    indicator["meaning"] = status_meaning(indicator, thresholds, meanings)
    indicator["gauge_marks"] = gauge_marks(indicator, thresholds)
    indicator["gauge_label"] = gauge_label(indicator, thresholds) if indicator["gauge_marks"] else None
    indicator["source_url"] = outside_url(indicator["source_url"])  # #125: text only if not http(s)
    indicator["is_external"] = indicator["source_url"] is not None
    indicator["is_weather"] = indicator["key"] == "weather"
    indicator["mapping"] = weather_mapping(indicator)
    indicator["issued"] = issue_time(indicator.get("issued_at"), brief_date)
    # Strike flag: the items that decided it are listed instead of one source link.
    indicator["links"] = [
        strike_link(link, shown_ranks.get(link.get("day")), brief_date) for link in indicator.get("items") or []
    ]


# The one grey line of a short card, an item with no summary (design review S5, #82, spec §7.5).
# Shortened by the owner (option A, #138; was the owner's longer wording of PR #80/#88): why a source
# is headline-only is said once, on How it works. The panel shows the same line when opened.
HEADLINE_NOTES = {
    "headline-only": "Headline only · severity from the headline",
    "unread": "Headline only · article couldn't be read · severity from the headline",
    "unrated": "Headline only · AI step failed · no summary or severity",
}


def headline_note(item: dict) -> str | None:
    """Why an item has no summary, or None when it has one (then the card is the full card)."""
    if item["summary"]:
        return None
    if item["severity"] is None:
        return HEADLINE_NOTES["unrated"]
    if item["access"] == "headline-only":
        return HEADLINE_NOTES["headline-only"]
    return HEADLINE_NOTES["unread"]


# Next to every summary written under a publisher's written permission (#107): the publisher asked
# that the page makes clear Haven Daily is independent and the publisher not responsible. The owner's
# short wording for card and panel (PR #108 review); How it works has the full sentence
# (`permission_statement`).
PERMISSION_NOTE = ("AI summary, with {source}'s permission. Haven Daily is independent; "
                   "{source} is not responsible for it.")
SENTENCE_WORDS = {1: "one sentence", 2: "two sentences", 3: "three sentences"}
# The impact label's second part for an item under a publisher's permission (#115); "interpretation" otherwise.
IMPACT_WHOSE = "Haven Daily's interpretation, not {source}'s"


def permission_note(item: dict) -> str | None:
    """The publisher's note for an item summarised under its written permission, else None."""
    if not item.get("permission"):
        return None
    return PERMISSION_NOTE.format(source=item["source"])


def prepare_item(item: dict, brief_date: str) -> None:
    item.setdefault("summary", None)
    item.setdefault("impact", None)
    item.setdefault("affects", [])
    item.setdefault("published", None)
    item.setdefault("access", "full")  # "headline-only" for paywalled sources
    item.setdefault("map", None)  # {"lat", "lon", "label"} when the item has a place on the map
    item.setdefault("permission", None)  # {"granted", "max_sentences", "impact"}: written permission (#107)
    # The English title written from Haven Daily's summary of a Dutch item (#153) is the one shown;
    # the card credits the source and its language instead of showing the Dutch headline.
    item.setdefault("headline_en", None)
    item["shown_headline"] = item["headline_en"] or item["headline"]
    item["permission_note"] = permission_note(item)
    # No impact block when the publisher's permission doesn't cover one (#107), or when the impact was
    # left out because it sounded confirmed twice (#115): not "Not enough information".
    permission = item["permission"]
    item["shows_impact"] = not item.get("impact_left_out") and (
        not permission or (bool(permission.get("impact")) and not permission.get("impact_left_out")))
    # Under a publisher's permission the label says whose interpretation it is (RTV Rijnmond's condition, #115).
    item["impact_whose"] = IMPACT_WHOSE.format(source=item["source"]) if permission else "interpretation"
    item["severity_key"] = severity_key(item["severity"])
    item["language_name"] = LANGUAGE_NAMES.get(item["language"], item["language"])
    item["credit"] = None if item["language"] == "en" else f"Source: {item['source']} (in {item['language_name']})"
    item["published_label"] = published_label(item["published"], brief_date)
    # A severity with no summary was rated from the headline alone (spec §2.1, §5.5 point 2): a
    # headline-only source, or a `use` item whose article couldn't be read.
    item["rated_from_headline"] = item["severity"] is not None and not item["summary"]
    item["headline_note"] = headline_note(item)
    item["url"] = outside_url(item.get("url"))  # #125: the headline without a link if not http(s)
    if item["language"] == "en" or item["url"] is None:
        item["translate_url"] = None
    else:
        item["translate_url"] = translate_url(item["url"], item["language"])


def model_name(model: str) -> str:
    """How the page names a model. A stored brief naming a model missing from MODEL_NAMES shows the
    id: an old day must never stop the build (hard rule 9). The Method page, which names the
    models the code calls now, stops instead (`method_page`)."""
    return MODEL_NAMES.get(model, model)


def summaries_line(items: list[dict], summaries: dict | None) -> str | None:
    """Who wrote the day's summaries, in plain words (design review S8, issue #84):
    "10 by Claude Sonnet 5.5, 0 by the backup model".

    Counted from each rated item's `written_by.model` over **all** the brief's items (every kept
    item, not only the five shown), so a rephrase retry by the main model, which `build.summaries`
    counts under "fallback" (§5.5 point 4), is credited to the model that wrote it. The backup
    model is `summarise.FALLBACK_MODEL`, always named last, with its count even at 0. None when the
    brief has no `build.summaries` (a reduced brief, or older shapes): then the line is left out."""
    if not summaries:
        return None
    counts: dict[str, int] = {}
    for item in items:
        model = (item.get("written_by") or {}).get("model")
        if item.get("severity") is not None and model:
            counts[model] = counts.get(model, 0) + 1
    if not counts:
        return "None"
    backup = summarise.FALLBACK_MODEL
    main = sorted((m for m in counts if m != backup), key=lambda m: -counts[m])  # stable: ties keep their order
    parts = [f"{counts[m]} by {model_name(m)}" for m in main]
    used = counts.get(backup, 0)
    parts.append(f"{used} by the backup model" + (f" ({model_name(backup)})" if used else ""))
    return ", ".join(parts)


def prepare_ships(brief: dict) -> None:
    """Add labels and counts to the AIS snapshot. None means the snapshot failed."""
    ships = brief.setdefault("ships", None)
    if not ships:
        brief["ships"] = None
        return
    items = brief["items"]
    for ship in ships["vessels"]:
        ship.setdefault("news_item", None)  # rank of the item about this ship's terminal
        ship["type_label"] = SHIP_TYPES[ship["type"]]
        ship["status_label"] = SHIP_STATUS[ship["status"]]
        ship["flag_name"] = FLAG_NAMES.get(ship["flag"], ship["flag"])
        rank = ship["news_item"]
        ship["news_severity"] = items[rank - 1]["severity_key"] if rank and rank <= len(items) else None
    vessels = ships["vessels"]
    ships["count"] = len(vessels)
    ships["by_type"] = {kind: sum(1 for ship in vessels if ship["type"] == kind) for kind in SHIP_TYPES}
    ships["at_anchor"] = sum(1 for ship in vessels if ship["status"] == "anchored")
    ships["underway"] = sum(1 for ship in vessels if ship["status"] == "underway")
    ships["linked"] = sum(1 for ship in vessels if ship["news_severity"])
    ships["vessels"] = sorted(vessels, key=lambda ship: (ship["area"], ship["name"]))


def map_payload(brief: dict) -> dict:
    """Everything static/map.js needs, embedded in the page as JSON."""
    callouts = [
        {
            "rank": rank,
            "severity": item["severity_key"],
            "title": item["shown_headline"],
            # What the pin card shows (#134): the credit of a Dutch item (#153), the summary (or the
            # short card's line), and the same links as the card below.
            "credit": item["credit"],
            "language": item["language"],
            "summary": item["summary"],
            "note": item["headline_note"] if not item["summary"] else None,
            "url": item["url"],
            "translate_url": item["translate_url"],
            **item["map"],
        }
        for rank, item in enumerate(brief["items"], start=1)
        if item["map"]
    ]
    ship_fields = (
        "name", "type", "type_label", "status", "status_label", "lat", "lon", "heading", "speed_kn",
        "length_m", "flag_name", "area", "destination", "destination_raw", "news_item", "news_severity",
    )
    ships = brief["ships"]
    return {
        "view_home": MAP_VIEW_HOME,
        "view_compact": MAP_VIEW_COMPACT,
        "ship_shapes": {"hull": SHIP_HULL, "decks": SHIP_DECKS},
        "callouts": callouts,
        "ships": [{key: ship[key] for key in ship_fields} for ship in ships["vessels"]] if ships else None,
        "ships_source": ships["source_name"] if ships else None,
    }


def prepare_briefs(briefs: list[dict], rhine_path: Path = CONFIG_DIR / "rhine.toml") -> list[dict]:
    """Add the fields the templates need: edition number, ranked items, status changes and
    meanings, map data. The Rhine's thresholds and meanings come from `rhine_path`."""
    thresholds, meanings = load_rhine(rhine_path), load_rhine_meanings(rhine_path)
    reads = _source_reads()  # for the failure notes (#138)
    briefs.sort(key=lambda brief: brief["date"])
    # Items shown on each day's page, {date: {url: rank}}: the strike line links an earlier
    # item's card only if its day page really shows it (spec §5.7 point 10).
    for brief in briefs:
        # Who wrote the summaries is counted over every kept item, before the cut to five (#84).
        brief["summaries_line"] = summaries_line(brief.get("items", []), (brief.get("build") or {}).get("summaries"))
        brief["items"] = rank_items(brief.get("items", []))
    shown_ranks = {
        brief["date"]: {item["url"]: rank for rank, item in enumerate(brief["items"], start=1)} for brief in briefs
    }
    previous_status: dict[str, dict] = {}
    previous_day: date | None = None
    for number, brief in enumerate(briefs, start=1):
        brief["day"] = date.fromisoformat(brief["date"])
        brief["edition"] = number
        brief.setdefault("sample", False)
        # Published directly by the morning job; hand-made fixes are listed, never silent (spec §6).
        corrections = brief.setdefault("corrections", [])
        for fix in corrections:
            fix["when"] = correction_time(fix["at"], brief["built_at"])
        corrections.sort(key=lambda fix: amsterdam_time(fix["at"]))
        brief["publication"] = publication_line(brief["built_at"], corrections)
        build = brief.setdefault("build", {})
        for key in ("sources_checked", "items_collected", "items_kept"):
            build.setdefault(key, None)
        build.setdefault("failures", [])
        # True only on a reduced brief: the AI was down all morning (spec §5.6).
        build.setdefault("ai_unavailable", False)

        build.setdefault("summaries", None)
        brief["failure_lines"] = failure_lines(build["failures"], reads)

        # "Since yesterday" only against the day before: after a missing day there is no yesterday.
        yesterday = previous_status if previous_day == brief["day"] - timedelta(days=1) else {}
        for indicator in brief["status"]:
            prepare_indicator(indicator, yesterday.get(indicator["key"]), number == 1, brief["date"], shown_ranks,
                              thresholds, meanings)
        previous_status = {indicator["key"]: indicator for indicator in brief["status"]}
        previous_day = brief["day"]

        for item in brief["items"]:
            prepare_item(item, brief["date"])
        brief["counts"] = {
            key: sum(1 for item in brief["items"] if item["severity_key"] == key) for key in SEVERITY_KEYS
        }
        prepare_ships(brief)
        brief["map"] = map_payload(brief)
        # Nothing to show on the chart (no shown item has a place, no ships): the page draws
        # it as a short strip instead of a full screen of empty map (#81, spec §7.4).
        brief["chart_empty"] = not brief["map"]["callouts"] and not brief["ships"]
    return briefs


def load_briefs(briefs_dir: Path) -> list[dict]:
    briefs = []
    for path in sorted(briefs_dir.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            briefs.append(json.load(f))
    return briefs


def group_by_month(briefs: list[dict]) -> list[tuple[str, list[dict]]]:
    """Newest month first, newest day first within each month."""
    newest_first = sorted(briefs, key=lambda brief: brief["date"], reverse=True)
    grouped = groupby(newest_first, key=lambda brief: brief["day"].replace(day=1))
    return [(f"{month:%B %Y}", list(days)) for month, days in grouped]


# A paused source (`enabled = false`, #138): listed with its verdict, not read for now.
PAUSED_USE = "Paused for now: its website refuses Haven Daily's automated reader, so it isn't read."


# A Dutch headline-only source (#153): every title on the site is English, written from a summary.
DUTCH_NOT_SHOWN = ("Its headlines are in Dutch and it hasn't given permission for summaries, so it is not shown for now: "
                   "Haven Daily writes English titles only from its own summaries.")


def source_use(source: Source) -> str:
    """One line on how the pipeline uses a source, from its config (Method page, #24)."""
    if source.verdict != "drop" and not source.enabled:  # paused (#138): said first, it is the state today
        return PAUSED_USE
    if source.dutch_without_permission:  # #153
        return DUTCH_NOT_SHOWN
    if source.effective_verdict == "use" and source.permission is not None:  # #107
        permission = source.permission
        text = "the lead paragraph in its feed" if source.id in LEAD_PARAGRAPH_FEEDS else "the article"
        length = SENTENCE_WORDS.get(permission.max_sentences, f"{permission.max_sentences} sentences")
        line = (f"With {source.name}'s written permission: new items go through the AI relevance check, "
                f"and kept ones are summarised from {text}, in at most {length}")
        if not permission.impact:
            return line + ", with no impact for planners."
        return line + (". The impact for planners is Haven Daily's own interpretation, written as possible "
                       "and checked for wording that sounds confirmed.")
    if source.verdict == "use" and source.auto_keep:
        return "Rotterdam-specific, so it skips the AI relevance check; summarised from the article."
    if source.verdict == "use":
        return "AI relevance check; kept items are summarised from the article."
    if source.verdict == "headline-only":
        return "Headline and link only; the AI sees the headline alone."
    return "Not collected."


def permission_statement(source: Source) -> str:
    """How it works: who gave written permission, when, and that they aren't responsible (#107)."""
    granted = source.permission.granted
    statement = (f"{source.name} gave Haven Daily written permission on {granted.day} {granted:%B %Y} for short "
                 f"AI-generated summaries of its articles. Haven Daily is an independent project; "
                 f"{source.name} is not responsible for the AI-generated summaries.")
    if source.permission.impact:  # #115
        statement += (f" The impact for planners on its items is Haven Daily's own interpretation, "
                      f"not {source.name}'s.")
    return statement


def method_page(sources: tuple[Source, ...], rhine: RhineThresholds) -> dict:
    """What the Method page shows that lives in config or code, so the page can't drift from it:
    the sources by verdict, the Kaub thresholds and the AI models (issue #24)."""
    groups = []
    for verdict, label in SOURCE_GROUPS:
        listed = [
            {
                "name": src.name,
                "home": src.home,  # the name links the source's normal public page
                "read_url": src.urls[0] if src.urls else None,  # what the job reads
                "read_label": "page" if src.access == "html" else "feed",  # "(page)" / "(feed)", owner PR #76
                "language_name": LANGUAGE_NAMES.get(src.language, src.language) if src.language else None,
                "access": {"rss": "RSS feed", "html": "Web page"}.get(src.access),
                "how": source_use(src),
                "why": src.why,
            }
            for src in sources if src.effective_verdict == verdict  # after any written permission (#107)
        ]
        if listed:
            groups.append({"verdict": verdict, "label": label, "sources": listed})
    return {
        "source_groups": groups,
        "permissions": [permission_statement(src) for src in sources if src.permission is not None],
        "rhine": {
            "normal": f"{rhine.watch_at_or_below + 1}–{rhine.watch_above} cm",
            "watch_low": f"{rhine.watch_at_or_below} cm or below",
            "watch_high": f"above {rhine.watch_above} cm",
            "alert_low": f"{rhine.alert_at_or_below} cm or below",
            "alert_high": f"above {rhine.alert_above} cm",
            "low_sources": RHINE_LOW_SOURCES,
            "low_read": RHINE_SOURCES_READ,
            "pegelonline_url": PEGELONLINE_KAUB_URL,
        },
        "models": {
            "filter": MODEL_NAMES[haven_filter.AI_MODEL],
            "summary": MODEL_NAMES[summarise.SUMMARY_MODEL],
            "fallback": MODEL_NAMES[summarise.FALLBACK_MODEL],
            "batch_wait_minutes": summarise.BATCH_WAIT // 60,
        },
    }


def social_image(site: SiteConfig) -> dict | None:
    """The og:image tags' values, or None while static/ has no preview image of the right size
    (issue #28: "only output og:image once the image exists"; a wrong size is left out too)."""
    path = STATIC_DIR / site.social_image
    if not path.exists() or preview_image_size(path) != PREVIEW_SIZE:
        return None
    return {"url": f"{site.base_url}static/{site.social_image}", "width": PREVIEW_SIZE[0],
            "height": PREVIEW_SIZE[1], "alt": site.social_image_alt}


def day_preview(brief: dict) -> dict:
    """A day page's preview title and description: the date, and the top headline (issue #28).
    Sample days say they are sample data instead (hard rule 10)."""
    title = f"{long_date(brief['day'])} · {SITE['name']}"
    if brief["sample"]:
        return {"title": f"{title} (sample data)", "description": SAMPLE_NOTE}
    items = brief["items"]  # ranked: most severe first
    if not items:
        return {"title": title, "description": QUIET_DAY}
    more = f" (and {len(items) - 1} more)" if len(items) > 1 else ""
    return {"title": title, "description": items[0]["shown_headline"] + more}


def site_preview(path: str, page: str | None) -> dict:
    """Today, Archive and "How it works": the page's title and the site description (issue #28)."""
    return {"title": f"{page} · {SITE['name']}" if page else SITE["name"], "description": SITE["description"],
            "path": path}


def make_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,  # a typo in a template fails the build instead of printing nothing
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(long_date=long_date, date_only=date_only, short_date=short_date, clock=clock)
    site = load_site()
    env.globals.update(
        # The owner's texts (SITE) and the addresses from config/site.toml, as one `site`.
        site={**SITE, "base_url": site.base_url, "linkedin_url": site.linkedin_url, "repo_url": site.repo_url},
        social_image=social_image(site),
        page_base=site.base_url,  # every page's own address starts here; render_site adds "sample/" there
        icons=ICONS,
        severity_keys=SEVERITY_KEYS,
        level_icons=LEVEL_ICONS,
        language_names=LANGUAGE_NAMES,
        ship_type_plurals=SHIP_TYPE_PLURALS,
        ship_hull=SHIP_HULL,
        ship_decks=SHIP_DECKS,
        max_items=MAX_ITEMS,
        ais_snapshot_built=AIS_SNAPSHOT_BUILT,
        meteoalarm_disclaimer=METEOALARM_DISCLAIMER,
        signal_flags=FLAGS,  # the logo, the 404 page and the flag key (#117)
        flag_source=FLAG_SOURCE,
    )
    return env


def write_page(env: Environment, template: str, path: Path, **context) -> None:
    html = env.get_template(template).render(**context)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def render_site(briefs_dir: Path, out_dir: Path, rhine_path: Path | None = None, *, sub_path: str = "",
                link_sample: bool = False) -> int:
    """The site from `briefs_dir` into `out_dir`. `sub_path` is where it is published below the
    site's address (`base_url`): "" for the real site, "sample/" for the sample site, so each page's
    canonical and preview address is right. `link_sample`: How it works links the sample site."""
    rhine_path = rhine_path or CONFIG_DIR / "rhine.toml"
    briefs = prepare_briefs(load_briefs(briefs_dir), rhine_path)
    if not briefs:
        raise SystemExit(f"No briefs found in {briefs_dir}")

    env = make_environment()
    # Every page's own address (canonical link, og:url): the one setting, base_url, + where this site is.
    env.globals["page_base"] = load_site().base_url + sub_path
    shutil.copytree(STATIC_DIR, out_dir / "static", dirs_exist_ok=True)
    sample = any(brief["sample"] for brief in briefs)

    # Pages in days/ sit one folder down, so their links start with "../".
    # Relative links keep the site working under GitHub Pages' /<repo>/ path.
    for i, brief in enumerate(briefs):
        older = briefs[i - 1] if i > 0 else None
        newer = briefs[i + 1] if i + 1 < len(briefs) else None
        write_page(
            env, "day.html", out_dir / "days" / f"{brief['date']}.html",
            root="../", active=None, sample=brief["sample"], is_index=False,
            brief=brief, older=older, newer=newer, is_latest=newer is None,
            preview=dict(day_preview(brief), path=f"days/{brief['date']}.html"),
        )

    latest = briefs[-1]
    write_page(
        env, "day.html", out_dir / "index.html",
        root="", active="today", sample=latest["sample"], is_index=True,
        brief=latest, older=briefs[-2] if len(briefs) > 1 else None, newer=None, is_latest=True,
        preview=site_preview("", None),
    )
    write_page(
        env, "archive.html", out_dir / "archive.html",
        root="", active="archive", sample=sample, months=group_by_month(briefs),
        preview=site_preview("archive.html", "Archive"),
    )
    write_page(env, "about.html", out_dir / "about.html", root="", active="method", sample=sample,
               method=method_page(load_sources(), load_rhine(rhine_path)), sample_link=link_sample and not sample,
               preview=site_preview("about.html", "How it works"))
    # GitHub Pages serves 404.html at whatever address was missing (#117), so its links start from
    # the site's own path ("/haven-daily/"), not from where the page happens to be.
    write_page(env, "404.html", out_dir / "404.html", root=urlparse(load_site().base_url).path, active=None,
               sample=sample, preview=site_preview("404.html", "Page not found"))
    if not sample and not sub_path:  # search engines: the real site's pages only
        write_search_files(out_dir, briefs)
    return len(briefs)


def write_search_files(out_dir: Path, briefs: list[dict]) -> None:
    """sitemap.xml (Today, Archive, How it works, every day page) and robots.txt pointing at it,
    both from base_url. The sample site has neither, and its pages are noindex."""
    base = load_site().base_url
    addresses = [base, f"{base}archive.html", f"{base}about.html"] + [f"{base}days/{b['date']}.html" for b in briefs]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{address}</loc></url>" for address in addresses] + ["</urlset>", ""]
    (out_dir / "sitemap.xml").write_text("\n".join(sitemap), encoding="utf-8", newline="\n")
    (out_dir / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n", encoding="utf-8",
                                        newline="\n")


SAMPLE_PATH = "sample/"  # where the sample site is published, below base_url (owner, 25 Nov 2026)


def render_published(briefs_dir: Path, out_dir: Path) -> int:
    """What GitHub Pages publishes: the site, and the sample site at sample/ once the site is built
    from real briefs (until then the site itself is the samples, so there is no second copy)."""
    real = Path(briefs_dir).resolve() != (PROJECT_DIR / "data" / "sample" / "briefs").resolve()
    count = render_site(briefs_dir, out_dir, link_sample=real)
    if real:
        render_site(PROJECT_DIR / "data" / "sample" / "briefs", Path(out_dir) / SAMPLE_PATH.rstrip("/"),
                    sub_path=SAMPLE_PATH)
    return count


def default_briefs_dir(data_dir: Path = PROJECT_DIR / "data") -> Path:
    """The real briefs (`data/briefs/`) as soon as there is one, else the samples (#26).

    Never both: a site of real days with invented ones mixed in would break hard rule 10. Real
    briefs are never deleted (§5.9), so once the first morning run has committed one, the site
    never falls back to the samples."""
    real = Path(data_dir) / "briefs"
    if real.is_dir() and any(real.glob("*.json")):
        return real
    return Path(data_dir) / "sample" / "briefs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Haven Daily site from brief files.")
    parser.add_argument("--briefs", type=Path, default=None,
                        help="default: data/briefs once it holds a brief, else data/sample/briefs")
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "site")
    parser.add_argument("--with-sample", action="store_true",
                        help="also the sample site at sample/ (what GitHub Pages publishes)")
    args = parser.parse_args()
    briefs = args.briefs if args.briefs is not None else default_briefs_dir()
    count = render_published(briefs, args.out) if args.with_sample else render_site(briefs, args.out)
    print(f"Rendered {count} briefs from {briefs} to {args.out}")


if __name__ == "__main__":
    main()
