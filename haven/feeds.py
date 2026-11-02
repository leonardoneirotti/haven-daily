"""Feed collectors: read the RSS sources into one common item shape (spec §4, §5.8; issue #9).

The RSS sources in config/sources.toml: PIN notices (use) and Nieuwsblad Transport,
PortsEurope, The Loadstar and RTV Rijnmond (all four headline-only).

Each feed entry becomes an `Item`: source id, headline, url, published (Amsterdam time),
language and access ("full" or "headline-only"). What may be kept depends on the access:

- **headline-only** (hard rules 12 and 13): only the headline, link and date are read. The
  body text in the feed (`description`, `content:encoded`) is never even parsed, and the
  article page is never fetched.
- **full** (`use` sources): the feed's `description` is kept as a short plain-text
  `snippet` **in memory only**, for the relevance filter (spec §5.4). `Item.record()`, the
  dict that goes into data/items/, never contains it, and `repr()` doesn't show it.
  PIN's description is the whole notice, not a teaser, so it is also kept (up to 6,000
  characters, in memory only) as the item's `article_text` for the summariser: no notice
  page needs to be opened (`FULL_TEXT_FEEDS`, issue #11).

A `use` source that opts out of AI use this morning (robots.txt, `haven/fetch.py`) is read
as headline-only, with a note in the failures so the owner updates SOURCES.md.

A broken feed is a failure, never an exception (hard rule 9): `collect_feed` returns the
items it could read plus `{"source": <name>, "error": <one line>}` entries for build.failures.

**PIN gap check (spec §5.8):** the PIN feed keeps only ~10 notices. If even the oldest
notice in it is newer than the previous run, notices published in between may have dropped
out of the feed unseen, and that is recorded in the failures.

XML is read with the standard library (`xml.etree.ElementTree`), so no extra dependency.
A feed that declares its own XML entities is refused: real feeds don't need them, and they
are the way to make a small file expand into a huge one.
"""

from __future__ import annotations

import copy
import email.utils
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin

from haven.clock import AMSTERDAM
from haven.config import Source
from haven.fetch import Fetcher, FetchError

PIN_SOURCE_ID = "pin-notices"
GAP_MESSAGE = "some notices may have been missed (feed rolled over)"
SNIPPET_MAX = 1000  # characters of feed text kept in memory for the relevance filter
ARTICLE_TEXT_MAX = 6000  # characters of article text kept in memory for the summariser (spec §5.8)
# Feeds whose description is the whole text, not a teaser (checked 1 Nov 2026): the article text
# comes from the feed, so no article page is opened for them (spec §5.8, issue #11).
FULL_TEXT_FEEDS = frozenset({PIN_SOURCE_ID})

_DC = "{http://purl.org/dc/elements/1.1/}"
_ENTITY_DECLARATION = re.compile(rb"<!ENTITY", re.IGNORECASE)
_BLOCK_TAGS = {"p", "br", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "table", "blockquote"}


class FeedError(Exception):
    """A feed was fetched but can't be read. `str(error)` is one line: `"<url>: <problem>"`."""

    def __init__(self, url: str, problem: str):
        self.url = url
        self.problem = problem
        super().__init__(f"{url}: {problem}")


@dataclass(frozen=True)
class Entry:
    """One usable entry of a feed, before it is tied to a source."""

    headline: str
    url: str
    published: str | None  # ISO 8601 in Amsterdam time, or None if the feed gives no readable date
    snippet: str | None = field(default=None, repr=False)
    text: str | None = field(default=None, repr=False)  # the whole description, up to ARTICLE_TEXT_MAX


@dataclass(frozen=True)
class ParsedFeed:
    entries: list[Entry]
    skipped: int  # entries without a headline or a usable link


@dataclass(frozen=True)
class Item:
    """A collected item in the common shape every collector returns (GLOSSARY: Item)."""

    source: str  # source id from config/sources.toml
    headline: str
    url: str
    published: str | None  # ISO 8601 in Amsterdam time, or None
    language: str  # "en" / "nl"
    access: str  # "full" / "headline-only" (spec §6, items[].access)
    snippet: str | None = field(default=None, repr=False)  # in memory only, never stored (hard rule 13)
    # Text for the summariser, in memory only, never stored (hard rule 13). Set by the K+N page
    # collector (the Rotterdam paragraph only, haven/pages.py); the collect step (#11) fills it
    # for the other `use` items and must not replace one that is already set.
    article_text: str | None = field(default=None, repr=False)
    # The relevance filter's decision, {"kept": bool, "stage": "rules" | "ai", "reason": str}
    # (spec §5.4). None until a stage has decided: the rules (haven/filter.py) set it for items
    # they keep or drop; the AI check (#13) for the rest.
    filter: dict | None = None
    # The summariser's output (haven/summarise.py, #15): severity, summary, impact, affects, map,
    # strike, written_by, and unlisted when something was discarded (spec §5.10). None until the
    # summariser has run; for an unrated item the fields are there with null values.
    ai: dict | None = None

    def record(self) -> dict:
        """The fields that may be stored in data/items/: everything except snippet and article text."""
        record = {
            "source": self.source,
            "headline": self.headline,
            "url": self.url,
            "published": self.published,
            "language": self.language,
            "access": self.access,
        }
        if self.filter is not None:
            record["filter"] = dict(self.filter)
        if self.ai is not None:
            record.update(copy.deepcopy(self.ai))  # a copy: changing the record can't change the item
        return record


@dataclass(frozen=True)
class FeedResult:
    items: list[Item]
    failures: list[dict]  # {"source": <source name>, "error": <one line>}, for build.failures


# --- collecting one source -------------------------------------------------------------


def collect_feed(source: Source, fetcher: Fetcher, previous_run: datetime | None = None) -> FeedResult:
    """Read every feed URL of an RSS source. Never raises for a broken feed.

    `previous_run` (timezone-aware) is when the previous morning run read the feeds; it is
    only used for the PIN gap check. None = no previous run known, so no gap check.
    """
    if not source.fetched:
        raise ValueError(f"{source.id}: verdict 'drop' sources are never fetched")
    if source.access != "rss":
        raise ValueError(f"{source.id}: access is {source.access!r}; collect_feed reads only 'rss' sources")

    failures: list[dict] = []

    def fail(error: str) -> None:
        failures.append({"source": source.name, "error": error})

    access = fetcher.source_access(source)
    if access.note:
        fail(access.note.removeprefix(f"{source.name}: "))  # the page already shows the name
    full = access.verdict == "use"

    items: list[Item] = []
    seen: set[str] = set()
    any_feed_read = False
    for url in source.urls:
        try:
            response = fetcher.fetch(url)
            parsed = parse_feed(response.body, response.url, with_snippet=full)
        except (FetchError, FeedError) as error:
            fail(f"{url}: {error.problem}")
            continue
        except Exception as error:  # a bug of ours on odd input must not stop the morning run
            fail(f"{url}: unexpected error ({type(error).__name__}: {error})")
            continue
        any_feed_read = True
        if parsed.skipped:
            fail(f"{url}: {parsed.skipped} entries without a headline or link were skipped")
        for entry in parsed.entries:
            if entry.url in seen:  # the same story in two feeds of one source (Nieuwsblad Transport)
                continue
            seen.add(entry.url)
            items.append(
                Item(
                    source=source.id,
                    headline=entry.headline,
                    url=entry.url,
                    published=entry.published,
                    language=source.language,
                    access="full" if full else "headline-only",
                    snippet=entry.snippet if full else None,
                    article_text=entry.text if full and source.id in FULL_TEXT_FEEDS else None,
                )
            )

    if source.id == PIN_SOURCE_ID and any_feed_read:
        gap = rollover_gap(items, previous_run)
        if gap:
            fail(gap)
    return FeedResult(items=items, failures=failures)


def rollover_gap(items: list[Item], previous_run: datetime | None) -> str | None:
    """GAP_MESSAGE if the oldest dated item is newer than the previous run, else None."""
    if previous_run is None:
        return None
    if previous_run.tzinfo is None or previous_run.utcoffset() is None:
        raise ValueError("previous_run has no timezone; pass a timezone-aware datetime")
    dates = [datetime.fromisoformat(item.published) for item in items if item.published]
    if not dates:
        return None
    return GAP_MESSAGE if min(dates) > previous_run else None


# --- reading RSS -------------------------------------------------------------------------


def parse_feed(body: bytes, feed_url: str, with_snippet: bool) -> ParsedFeed:
    """Read an RSS 2.0 document. Raises FeedError if it isn't one.

    `with_snippet=False` (headline-only sources): the entries' body text is not read at all.
    """
    if _ENTITY_DECLARATION.search(body):
        raise FeedError(feed_url, "feed declares its own XML entities; refused")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise FeedError(feed_url, f"not valid XML ({error})") from None
    if root.tag != "rss":
        raise FeedError(feed_url, f"not an RSS feed (the document starts with <{_local(root.tag)}>)")
    channel = root.find("channel")
    if channel is None:
        raise FeedError(feed_url, "RSS feed without a <channel>")

    entries: list[Entry] = []
    skipped = 0
    for element in channel.findall("item"):
        headline = _plain(element.findtext("title") or "")
        url = _link(element, feed_url)
        if not headline or not url:
            skipped += 1
            continue
        snippet = text = None
        if with_snippet:
            description = _plain(element.findtext("description") or "")
            snippet = description[:SNIPPET_MAX].rstrip() or None
            text = description[:ARTICLE_TEXT_MAX].rstrip() or None
        entries.append(Entry(headline=headline, url=url, published=_published(element), snippet=snippet, text=text))
    return ParsedFeed(entries=entries, skipped=skipped)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _link(element: ET.Element, feed_url: str) -> str | None:
    """The entry's own address: <link>, else a permalink <guid>. Only http(s), without #fragment."""
    raw = (element.findtext("link") or "").strip()
    if not raw:
        guid = element.find("guid")
        if guid is not None and guid.get("isPermaLink", "true").lower() != "false":
            raw = (guid.text or "").strip()
    if not raw:
        return None
    url = urldefrag(urljoin(feed_url, raw)).url
    return url if url.startswith(("https://", "http://")) else None


def _published(element: ET.Element) -> str | None:
    """<pubDate> (RFC 822), else <dc:date> (ISO 8601), in Amsterdam time. Unreadable = None.

    A date without a timezone is read as UTC, as RFC 5322 does for "-0000".
    """
    moment = None
    pub_date = (element.findtext("pubDate") or "").strip()
    if pub_date:
        try:
            moment = email.utils.parsedate_to_datetime(pub_date)
        except (TypeError, ValueError, IndexError):
            moment = None
    if moment is None:
        dc_date = (element.findtext(f"{_DC}date") or "").strip()
        if dc_date:
            try:
                moment = datetime.fromisoformat(dc_date)
            except ValueError:
                moment = None
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(AMSTERDAM).replace(microsecond=0).isoformat()


class _TextOnly(HTMLParser):
    """Collects the text of an HTML fragment; block tags become spaces."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        self.parts.append(data)


def _plain(fragment: str) -> str:
    """HTML or escaped text -> one line of plain text (also fixes double-escaped `&amp;#8217;`)."""
    parser = _TextOnly()
    parser.feed(fragment)
    parser.close()
    return " ".join("".join(parser.parts).split())


# --- manual smoke run ---------------------------------------------------------------------


def main() -> None:
    """`python -m haven.feeds`: read the real RSS feeds once and print headlines and links only."""
    from haven.config import load_sources

    fetcher = Fetcher()
    for source in load_sources():
        if not source.fetched or source.access != "rss":
            continue
        result = collect_feed(source, fetcher)
        print(f"\n== {source.name} ({len(result.items)} items)")
        for item in result.items:
            print(f"  {item.published or 'no date':25}  {item.access:13}  {item.headline}\n{'':43}{item.url}")
        for failure in result.failures:
            print(f"  FAILURE: {failure['error']}")


if __name__ == "__main__":
    main()
