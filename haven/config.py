"""Read and check the config files in config/ (spec §5.2.1).

The files are TOML, read with Python's built-in `tomllib`, so no extra
dependency. Every check fails with a ConfigError that names the file, the
source and what is wrong, so a typo stops the run at once instead of
silently dropping a source.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

VERDICTS = ("use", "headline-only", "drop")
ACCESS_TYPES = ("rss", "html")

_SOURCE_FIELDS = {"id", "name", "verdict", "urls", "access", "language", "auto_keep", "note"}
_LANGUAGE = re.compile(r"^[a-z]{2}$")

# Place list (spec §5.10). "barrier" and "bridge" are Claude's additions to the
# spec's five kinds, not yet confirmed by the owner.
PLACE_KINDS = ("terminal", "area", "anchorage", "lock", "barrier", "bridge", "fairway")
LABEL_SIDES = ("right", "left")
# The chart sheet (south, west, north, east), spec §8.1: every place must be on it.
SHEET_BBOX = (51.74, 3.40, 52.16, 4.62)
_PLACE_FIELDS = {"id", "label", "kind", "lat", "lon", "side", "osm"}
_PLACE_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_OSM_ID = re.compile(r"^(node|way|relation)/[1-9][0-9]*$")


class ConfigError(Exception):
    """A config file is missing, unreadable or breaks one of the rules."""


@dataclass(frozen=True)
class Source:
    """One source from config/sources.toml (vocabulary: GLOSSARY.md)."""

    id: str
    name: str
    verdict: str  # "use" / "headline-only" / "drop" (spec §4)
    urls: tuple[str, ...] = ()
    access: str | None = None  # "rss" / "html"; None for dropped sources
    language: str | None = None  # two-letter code, e.g. "en", "nl"
    auto_keep: bool = False  # skips the AI relevance check (spec §5.4)
    note: str | None = None

    @property
    def fetched(self) -> bool:
        """Dropped sources are listed for the record but never fetched."""
        return self.verdict != "drop"


@dataclass(frozen=True)
class FilterConfig:
    """Word lists for the rule stage of the relevance filter (spec §5.4)."""

    off_topic: dict[str, tuple[str, ...]] = field(default_factory=dict)  # language -> words


@dataclass(frozen=True)
class Place:
    """One place from config/places.toml (GLOSSARY: Place). Coordinates come from OpenStreetMap."""

    id: str
    label: str
    kind: str  # one of PLACE_KINDS
    lat: float
    lon: float
    side: str  # "right" / "left": which side of the pin number the label goes
    osm: str  # the OSM element the coordinates were taken from, e.g. "way/145614140"


def _read_toml(path: Path) -> dict:
    path = Path(path)
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"{path}: config file not found") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.name}: not valid TOML ({e})") from None


def load_sources(path: Path = CONFIG_DIR / "sources.toml") -> tuple[Source, ...]:
    """All sources in file order, checked. Raises ConfigError on the first problem."""
    path = Path(path)
    data = _read_toml(path)
    unknown_top = set(data) - {"source"}
    if unknown_top:
        raise ConfigError(f"{path.name}: unknown section {sorted(unknown_top)[0]!r} (only [[source]] is allowed)")
    entries = data.get("source")
    if not entries:
        raise ConfigError(f"{path.name}: no [[source]] entries")
    if not isinstance(entries, list):
        raise ConfigError(f"{path.name}: 'source' must be written as [[source]] tables")

    sources: list[Source] = []
    seen: set[str] = set()
    for number, entry in enumerate(entries, start=1):
        source = _check_source(path.name, number, entry)
        if source.id in seen:
            raise ConfigError(f"{path.name}: duplicate id {source.id!r} (source #{number})")
        seen.add(source.id)
        sources.append(source)
    return tuple(sources)


def load_filter(path: Path = CONFIG_DIR / "filter.toml") -> FilterConfig:
    """Off-topic word lists, one per language. Empty lists are fine (nothing dropped by words)."""
    path = Path(path)
    data = _read_toml(path)
    unknown_top = sorted(set(data) - {"off_topic"})
    if unknown_top:
        raise ConfigError(f"{path.name}: unknown section {unknown_top[0]!r} (allowed: off_topic)")
    if "off_topic" not in data:
        raise ConfigError(f"{path.name}: missing [off_topic] section")

    off_topic: dict[str, tuple[str, ...]] = {}
    for language, words in data["off_topic"].items():
        where = f"{path.name}, off_topic.{language}"
        if not _LANGUAGE.match(language):
            raise ConfigError(f"{where}: {language!r} must be a two-letter language code such as 'en' or 'nl'")
        if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
            raise ConfigError(f"{where}: must be a list of words, e.g. [\"football\"]")
        if any(not w.strip() for w in words):
            raise ConfigError(f"{where}: contains an empty word, which would match every headline")
        for word in words:
            if "*" in word[:-1] or not word.rstrip("*").strip():
                raise ConfigError(
                    f"{where}: {word!r}: a * is only allowed once, at the end of a word "
                    f"(\"voetbal*\" matches voetbalclub)")
        off_topic[language] = tuple(words)
    return FilterConfig(off_topic=off_topic)


def load_places(path: Path = CONFIG_DIR / "places.toml") -> tuple[Place, ...]:
    """The fixed place list, in file order, checked. Raises ConfigError on the first problem."""
    path = Path(path)
    data = _read_toml(path)
    unknown_top = sorted(set(data) - {"place"})
    if unknown_top:
        raise ConfigError(f"{path.name}: unknown section {unknown_top[0]!r} (only [[place]] is allowed)")
    entries = data.get("place")
    if not entries or not isinstance(entries, list):
        raise ConfigError(f"{path.name}: no [[place]] entries")

    places: list[Place] = []
    ids: set[str] = set()
    labels: set[str] = set()
    for number, entry in enumerate(entries, start=1):
        place = _check_place(path.name, number, entry)
        if place.id in ids:
            raise ConfigError(f"{path.name}: duplicate id {place.id!r} (place #{number})")
        if place.label.casefold() in labels:
            raise ConfigError(f"{path.name}: duplicate label {place.label!r} (place #{number})")
        ids.add(place.id)
        labels.add(place.label.casefold())
        places.append(place)
    return tuple(places)


def _check_place(file: str, number: int, entry: dict) -> Place:
    where = f"{file}, place #{number}"
    if isinstance(entry.get("id"), str) and entry["id"]:
        where = f"{file}, place {entry['id']!r}"

    def fail(problem: str):
        raise ConfigError(f"{where}: {problem}")

    unknown = sorted(set(entry) - _PLACE_FIELDS)
    if unknown:
        fail(f"unknown field {unknown[0]!r} (allowed: {', '.join(sorted(_PLACE_FIELDS))})")
    for name in ("id", "label", "kind", "lat", "lon", "side", "osm"):
        if name not in entry:
            fail(f"missing {name!r}")
    for name in ("id", "label", "kind", "side", "osm"):
        if not isinstance(entry[name], str) or not entry[name].strip():
            fail(f"{name!r} must be non-empty text")
    if entry["id"] == "none":
        fail("'none' can't be an id: it is the AI's answer for \"no place\"")
    if not _PLACE_ID.match(entry["id"]):
        fail(f"id {entry['id']!r} may only use lowercase letters, digits and - (e.g. \"ect-delta\")")
    if entry["kind"] not in PLACE_KINDS:
        fail(f"unknown kind {entry['kind']!r} (allowed: {', '.join(PLACE_KINDS)})")
    if entry["side"] not in LABEL_SIDES:
        fail(f"side {entry['side']!r} must be one of: {', '.join(LABEL_SIDES)}")
    if not _OSM_ID.match(entry["osm"]):
        fail(f"osm {entry['osm']!r} must name an OpenStreetMap element, e.g. \"way/145614140\"")
    for name in ("lat", "lon"):
        if isinstance(entry[name], bool) or not isinstance(entry[name], (int, float)):
            fail(f"{name!r} must be a number")
    south, west, north, east = SHEET_BBOX
    if not (south <= entry["lat"] <= north and west <= entry["lon"] <= east):
        fail(f"({entry['lat']}, {entry['lon']}) is outside the chart sheet {SHEET_BBOX} (spec §8.1)")
    return Place(id=entry["id"], label=entry["label"], kind=entry["kind"], lat=float(entry["lat"]),
                 lon=float(entry["lon"]), side=entry["side"], osm=entry["osm"])


def load_tags(path: Path = CONFIG_DIR / "tags.toml") -> tuple[str, ...]:
    """The fixed "affects" tags (without the place labels, which are added by haven/places.py)."""
    path = Path(path)
    data = _read_toml(path)
    unknown_top = sorted(set(data) - {"affects"})
    if unknown_top:
        raise ConfigError(f"{path.name}: unknown key {unknown_top[0]!r} (only 'affects' is allowed)")
    if "affects" not in data:
        raise ConfigError(f"{path.name}: missing 'affects' list")
    tags = data["affects"]
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ConfigError(f"{path.name}: 'affects' must be a list of tags, e.g. [\"Containers\"]")
    seen: set[str] = set()
    for tag in tags:
        if not tag.strip():
            raise ConfigError(f"{path.name}: 'affects' contains an empty tag")
        if tag.casefold() in seen:
            raise ConfigError(f"{path.name}: duplicate tag {tag!r} (tags are matched ignoring upper/lower case)")
        seen.add(tag.casefold())
    return tuple(tags)


def _check_source(file: str, number: int, entry: dict) -> Source:
    where = f"{file}, source #{number}"
    if isinstance(entry.get("id"), str) and entry["id"]:
        where = f"{file}, source {entry['id']!r}"

    def fail(problem: str):
        raise ConfigError(f"{where}: {problem}")

    unknown = sorted(set(entry) - _SOURCE_FIELDS)
    if unknown:
        fail(f"unknown field {unknown[0]!r} (allowed: {', '.join(sorted(_SOURCE_FIELDS))})")

    for name in ("id", "name", "verdict"):
        if name not in entry:
            fail(f"missing {name!r}")
        if not isinstance(entry[name], str) or not entry[name].strip():
            fail(f"{name!r} must be non-empty text")

    verdict = entry["verdict"]
    if verdict not in VERDICTS:
        fail(f"unknown verdict {verdict!r} (allowed: {', '.join(VERDICTS)})")

    urls = entry.get("urls", [])
    if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
        fail("'urls' must be a list of web addresses")
    for url in urls:
        if not url.startswith(("https://", "http://")):
            fail(f"URL {url!r} must start with https:// or http://")

    access = entry.get("access")
    if access is not None and access not in ACCESS_TYPES:
        fail(f"unknown access {access!r} (allowed: {', '.join(ACCESS_TYPES)})")

    language = entry.get("language")
    if language is not None and (not isinstance(language, str) or not _LANGUAGE.match(language)):
        fail(f"language {language!r} must be a two-letter code such as 'en' or 'nl'")

    auto_keep = entry.get("auto_keep", False)
    if not isinstance(auto_keep, bool):
        fail("'auto_keep' must be true or false")

    note = entry.get("note")
    if note is not None and not isinstance(note, str):
        fail("'note' must be text")

    if verdict != "drop":
        if not urls:
            fail(f"has no URL (a {verdict!r} source is fetched, so it needs at least one)")
        for name in ("access", "language"):
            if entry.get(name) is None:
                fail(f"missing {name!r} (needed to fetch a {verdict!r} source)")

    return Source(
        id=entry["id"],
        name=entry["name"],
        verdict=verdict,
        urls=tuple(urls),
        access=access,
        language=language,
        auto_keep=auto_keep,
        note=note,
    )
