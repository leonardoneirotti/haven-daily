"""Render the Haven Daily static site from daily brief files.

A brief is one JSON file per day (see data/sample/briefs/ for the format).
This module only turns briefs into HTML. Collecting, filtering, summarising and
the AIS snapshot happen in earlier steps of the pipeline.

Usage, from the project folder:
    python -m haven.render --briefs data/sample/briefs --out site
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime
from itertools import groupby
from pathlib import Path
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from haven.clock import AMSTERDAM

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_DIR / "templates"
STATIC_DIR = PROJECT_DIR / "static"

SITE = {
    "name": "Haven Daily",
    "author": "Leonardo Neirotti",
    "linkedin_url": None,  # fill in to show the link in the footer and on the Method page
    "repo_url": None,  # fill in once the GitHub repository is public
}

MAX_ITEMS = 5
SEVERITIES = ("high", "medium", "low")
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


def translate_url(url: str, source_language: str) -> str:
    """Link that opens the original article through Google Translate.

    We link to the translation instead of storing one: the page never
    republishes someone else's article text.
    """
    query = urlencode({"sl": source_language, "tl": "en", "u": url})
    return f"https://translate.google.com/translate?{query}"


def rank_items(items: list[dict]) -> list[dict]:
    """Most severe first, at most MAX_ITEMS. Quiet days stay short: never pad."""
    ranked = sorted(items, key=lambda item: SEVERITIES.index(item["severity"]))
    return ranked[:MAX_ITEMS]


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


def prepare_indicator(indicator: dict, previous: dict | None, is_first: bool) -> None:
    indicator.setdefault("value", None)
    indicator.setdefault("unit", "")
    indicator.setdefault("place", None)
    indicator.setdefault("note", None)
    indicator.setdefault("observed_at", None)
    indicator.setdefault("gauge_max", None)
    indicator["level_key"], indicator["level_label"] = LEVELS[indicator.get("level")]
    value = indicator["value"]
    indicator["is_number"] = isinstance(value, (int, float))
    indicator["display_value"] = f"{value:g}" if indicator["is_number"] else value
    indicator["change"] = describe_change(indicator, previous, is_first)
    indicator["gauge_pct"] = gauge_percent(indicator)
    indicator["is_external"] = indicator["source_url"].startswith("http")


def prepare_item(item: dict) -> None:
    item.setdefault("summary", None)
    item.setdefault("impact", None)
    item.setdefault("affects", [])
    item.setdefault("published", None)
    item.setdefault("access", "full")  # "headline-only" for paywalled sources
    item.setdefault("map", None)  # {"lat", "lon", "label"} when the item has a place on the map
    if item["language"] == "en":
        item["translate_url"] = None
    else:
        item["translate_url"] = translate_url(item["url"], item["language"])


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
        ship["news_severity"] = items[rank - 1]["severity"] if rank and rank <= len(items) else None
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
            "severity": item["severity"],
            "title": item["headline"],
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


def prepare_briefs(briefs: list[dict]) -> list[dict]:
    """Add the fields the templates need: edition number, ranked items, status changes, map data."""
    briefs.sort(key=lambda brief: brief["date"])
    previous_status: dict[str, dict] = {}
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

        for indicator in brief["status"]:
            prepare_indicator(indicator, previous_status.get(indicator["key"]), number == 1)
        previous_status = {indicator["key"]: indicator for indicator in brief["status"]}

        brief["items"] = rank_items(brief.get("items", []))
        for item in brief["items"]:
            prepare_item(item)
        brief["counts"] = {s: sum(1 for item in brief["items"] if item["severity"] == s) for s in SEVERITIES}
        prepare_ships(brief)
        brief["map"] = map_payload(brief)
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


def make_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,  # a typo in a template fails the build instead of printing nothing
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(long_date=long_date, date_only=date_only, short_date=short_date, clock=clock)
    env.globals.update(
        site=SITE,
        icons=ICONS,
        severities=SEVERITIES,
        level_icons=LEVEL_ICONS,
        language_names=LANGUAGE_NAMES,
        ship_type_plurals=SHIP_TYPE_PLURALS,
        ship_hull=SHIP_HULL,
        ship_decks=SHIP_DECKS,
        max_items=MAX_ITEMS,
    )
    return env


def write_page(env: Environment, template: str, path: Path, **context) -> None:
    html = env.get_template(template).render(**context)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def render_site(briefs_dir: Path, out_dir: Path) -> int:
    briefs = prepare_briefs(load_briefs(briefs_dir))
    if not briefs:
        raise SystemExit(f"No briefs found in {briefs_dir}")

    env = make_environment()
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
        )

    latest = briefs[-1]
    write_page(
        env, "day.html", out_dir / "index.html",
        root="", active="today", sample=latest["sample"], is_index=True,
        brief=latest, older=briefs[-2] if len(briefs) > 1 else None, newer=None, is_latest=True,
    )
    write_page(
        env, "archive.html", out_dir / "archive.html",
        root="", active="archive", sample=sample, months=group_by_month(briefs),
    )
    write_page(env, "about.html", out_dir / "about.html", root="", active="method", sample=sample)
    return len(briefs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Haven Daily site from brief files.")
    parser.add_argument("--briefs", type=Path, default=PROJECT_DIR / "data" / "sample" / "briefs")
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "site")
    args = parser.parse_args()
    count = render_site(args.briefs, args.out)
    print(f"Rendered {count} briefs to {args.out}")


if __name__ == "__main__":
    main()
