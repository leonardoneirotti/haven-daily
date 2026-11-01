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
