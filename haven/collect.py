"""Collect step: every source, duplicates, feed read time, article text (spec §5.1 step 1, §5.8; issue #11).

`run_collect()` is step 1 of the morning job:

1. **Every `use` and `headline-only` source** is read, in config order, by its collector
   (`haven/feeds.py` for RSS, `haven/pages.py` for HTML). One source failing never stops the
   others (hard rule 9); even a crash inside a collector becomes a failure line.
2. **Duplicates are dropped here, once**: an item whose link is already in `data/items/` of the
   previous 14 days is not returned again, and the same link from two sources today counts
   once (first source in config order wins). Links are compared by `url_key()`, which ignores
   only spelling differences of one address (see there).
3. **Feed read time:** the result carries `feeds_read_at`, the moment this run started reading
   the sources. The runner (#22) stores it in the brief as `build.feeds_read_at`; the next run
   reads it back (`previous_feeds_read_at`) and passes it as `previous_run` to the PIN gap check.
   If no brief of the previous 14 days has it (e.g. the first run), the gap check is skipped
   and a note says so.
4. **K+N gone quiet:** if Kuehne+Nagel SeaNews gave no item in 14 days (today plus the 13 days
   before), that is recorded as a failure, so a renamed weekly series can't go unnoticed. The
   check starts 14 days after the first collect run of any source.

The step returns items **in memory**; nothing is written here. The runner writes the day's
items file once, after the filter and summariser have added their fields.

`add_article_text()` opens the article page of `use` items and keeps up to 6,000 characters of
its text **in memory only** (`Item.article_text`, never in `record()`, hard rule 13). The runner
calls it for **kept** items only, after the relevance filter, so pages of items that are
dropped anyway are never requested. Text that is already set is never replaced: K+N's holds
only its Rotterdam paragraph, PIN's comes from its feed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Callable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from haven import clock, storage
from haven.clock import AMSTERDAM
from haven.config import Source
from haven.feeds import ARTICLE_TEXT_MAX, PIN_SOURCE_ID, FeedResult, Item, collect_feed
from haven.fetch import Fetcher, FetchError
from haven.pages import KN_SOURCE_ID, collect_page

DUPLICATE_DAYS = 14  # stored days whose links count as already seen (spec §5.4, §6.1)
BRIEF_DAYS = 14  # how far back the previous run's feed read time is looked for
KN_QUIET_DAYS = 14  # K+N must give an item within this many days (today included)
UTM_PREFIX = "utm_"  # tracking parameters ignored by the duplicate check (owner's decision, 1 Nov 2026)

DUPLICATE_CHECK = "Duplicate check"  # the `source` of failures in reading stored days
KN_QUIET = "no item collected in the last 14 days (weekly port update renamed, or the collector broken?)"
NO_ARTICLE_TEXT = "article text not found on the page (layout changed?)"
NO_READER = "no article reader for this source in haven/collect.py, so the article was not opened"
GAP_CHECK_SKIPPED = "gap check skipped: no brief of the last 14 days records when the feeds were last read"

# Where the article text sits on each `use` source's article pages (checked 1 Nov 2026).
# PIN (whole notice in its feed) and K+N (Rotterdam paragraph, haven/pages.py) set their text
# themselves; a test keeps this list and the `use` sources in config in step.
ARTICLE_BODY = {
    "port-authority-news": "div.news-page",
    "contargo-news": "main div.text",
    "ect-news": ".block-system-main-block .field--name-body",
}
# Never part of the text, even inside the container: the Port Authority's header block with
# headline and date, its "more news" box, and page furniture.
ARTICLE_SKIP = ".hero, .views-element-container, nav, header, footer, aside, form, figure, script, style, noscript"
_TEXT_BLOCKS = ["p", "li", "h1", "h2", "h3", "h4", "h5", "h6"]

CollectSource = Callable[[Source, Fetcher, "datetime | None"], FeedResult]


@dataclass(frozen=True)
class CollectResult:
    items: list[Item]  # new items only, in config order, then page/feed order
    failures: list[dict]  # {"source": <name>, "error": <one line>}, for build.failures
    feeds_read_at: str  # ISO 8601, Amsterdam time: when this run started reading the sources
    sources_checked: int  # sources that were read (dropped ones are not)
    items_collected: int  # before duplicates were removed
    duplicates: int  # items left out because their link was already seen


@dataclass(frozen=True)
class ArticleResult:
    items: list[Item]
    failures: list[dict]


# --- the collect step ----------------------------------------------------------------------


def collect_source(source: Source, fetcher: Fetcher, previous_run: datetime | None) -> FeedResult:
    """One source, by its access type. `previous_run` matters only for the PIN gap check."""
    if source.access == "rss":
        return collect_feed(source, fetcher, previous_run)
    if source.access == "html":
        return collect_page(source, fetcher)
    raise ValueError(f"{source.id}: unknown access {source.access!r}")


def run_collect(
    sources,
    fetcher: Fetcher,
    today: date,
    data_dir=storage.DATA_DIR,
    now: Callable[[], datetime] = clock.now,
    collector: CollectSource | None = None,
) -> CollectResult:
    """Read every fetched source and return today's new items. Never raises for one source.

    `collector` replaces `collect_source` in tests (fake sources).
    """
    collect_one = collector or collect_source
    read_at = now().astimezone(AMSTERDAM).replace(microsecond=0).isoformat()
    previous_run = previous_feeds_read_at(today, data_dir)

    failures: list[dict] = []
    pin = next((source for source in sources if source.id == PIN_SOURCE_ID and source.fetched), None)
    if previous_run is None and pin is not None:  # say so, so a missed rollover isn't silently unchecked
        failures.append({"source": pin.name, "error": GAP_CHECK_SKIPPED})
    stored = _stored_items(today, data_dir, failures)
    seen = {url_key(line["url"]) for _, lines in stored for line in lines
            if isinstance(line, dict) and isinstance(line.get("url"), str)}

    fetched = [source for source in sources if source.fetched]
    items: list[Item] = []
    collected = duplicates = 0
    for source in fetched:
        try:
            result = collect_one(source, fetcher, previous_run)
        except Exception as error:  # a collector must never take the others down (hard rule 9)
            failures.append({"source": source.name, "error": f"unexpected error ({type(error).__name__}: {error})"})
            continue
        failures.extend(result.failures)
        for item in result.items:
            collected += 1
            key = url_key(item.url)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            items.append(item)

    failures.extend(_kn_quiet(sources, items, stored, today, data_dir))
    return CollectResult(
        items=items,
        failures=failures,
        feeds_read_at=read_at,
        sources_checked=len(fetched),
        items_collected=collected,
        duplicates=duplicates,
    )


def url_key(url: str) -> str:
    """The form in which two links are compared for the duplicate check.

    Ignored, because they don't change which page it is: `http` vs `https`, upper/lower case
    in the host name, a leading `www.`, the default port, a trailing `/`, the `#fragment`, and
    `utm_*` tracking parameters (any case). Kept, because they can: the path's case and every
    other query parameter, as written and in their order (`?id=123` names the article on some
    sites). The stored link itself is never changed; this is only for comparing.
    """
    parts = urlsplit(url.strip())
    query = "&".join(
        part for part in parts.query.split("&")
        if part and not part.split("=", 1)[0].lower().startswith(UTM_PREFIX)
    )
    host = (parts.hostname or "").lower().removeprefix("www.")
    try:
        port = parts.port
    except ValueError:  # a malformed port: compare the link as written, still without fragment
        return url.strip().split("#", 1)[0]
    key = (host if port in (None, 80, 443) else f"{host}:{port}") + parts.path.rstrip("/")
    return f"{key}?{query}" if query else key


def previous_feeds_read_at(today: date, data_dir=storage.DATA_DIR) -> datetime | None:
    """`build.feeds_read_at` of the latest brief of the previous 14 days that has a readable one.

    A brief without it (or with a time without timezone) is skipped for an older one: an older
    time can only make the PIN gap check warn more, never less. None = no gap check.
    """
    for back in range(1, BRIEF_DAYS + 1):
        try:
            brief = storage.read("briefs", today - timedelta(days=back), data_dir)
        except storage.StorageError:
            continue  # a broken brief fails the renderer loudly anyway
        build = brief.get("build") if isinstance(brief, dict) else None
        value = build.get("feeds_read_at") if isinstance(build, dict) else None
        if not isinstance(value, str):
            continue
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            continue
        if moment.tzinfo is not None:
            return moment
    return None


def _stored_items(today: date, data_dir, failures: list[dict]) -> list[tuple[date, list]]:
    """Item lines of the previous 14 days, newest first. A broken day is a failure, not a crash."""
    found = []
    for back in range(1, DUPLICATE_DAYS + 1):
        day = today - timedelta(days=back)
        try:
            lines = storage.read("items", day, data_dir)
        except storage.StorageError as error:
            failures.append({"source": DUPLICATE_CHECK, "error": f"{error}; that day's links are not checked"})
            continue
        if lines is not None:
            found.append((day, lines))
    return found


def _kn_quiet(sources, items: list[Item], stored, today: date, data_dir) -> list[dict]:
    """One failure if K+N gave no item today or in the 13 days before (spec §5.8)."""
    kn = next((source for source in sources if source.id == KN_SOURCE_ID), None)
    if kn is None or not kn.fetched:
        return []  # dropped: never fetched, so nothing to expect
    first = storage.first_day("items", data_dir)
    if first is None or today < first + timedelta(days=KN_QUIET_DAYS):
        return []  # less than 14 days since the first collect run of any source
    if any(item.source == KN_SOURCE_ID for item in items):
        return []
    window_start = today - timedelta(days=KN_QUIET_DAYS - 1)
    for day, lines in stored:
        if day >= window_start and any(isinstance(line, dict) and line.get("source") == KN_SOURCE_ID for line in lines):
            return []
    return [{"source": kn.name, "error": KN_QUIET}]


# --- article text, in memory only ---------------------------------------------------------


def add_article_text(items: list[Item], sources, fetcher: Fetcher) -> ArticleResult:
    """Open each `use` item's article page and attach its text. Never raises for one page.

    Headline-only items and items whose text is already set are passed through untouched,
    without any request. A page that can't be read leaves the item without text and adds a
    failure line; the item itself stays (what the summariser does then is #15's decision).
    """
    names = {source.id: source.name for source in sources}
    done: list[Item] = []
    failures: list[dict] = []
    for item in items:
        if item.access != "full" or item.article_text:
            done.append(item)
            continue

        def fail(error: str) -> None:
            failures.append({"source": names.get(item.source, item.source), "error": f"{item.url}: {error}"})

        selector = ARTICLE_BODY.get(item.source)
        if selector is None:
            fail(NO_READER)
            done.append(item)
            continue
        try:
            reason = fetcher.ai_opt_out(item.url)  # the article may sit on another host than the list
            if reason:
                fail(f"{reason}, so this item is treated as headline-only (hard rule 12). "
                     "Update SOURCES.md and config/sources.toml.")
                done.append(replace(item, access="headline-only", snippet=None))
                continue
            text = article_text(fetcher.fetch(item.url).text(), selector)
        except FetchError as error:
            fail(error.problem)
            done.append(item)
            continue
        except Exception as error:  # a bug of ours on an odd page must not stop the morning run
            fail(f"unexpected error ({type(error).__name__}: {error})")
            done.append(item)
            continue
        if not text:
            fail(NO_ARTICLE_TEXT)
            done.append(item)
            continue
        done.append(replace(item, article_text=text))
    return ArticleResult(items=done, failures=failures)


def article_text(page_html: str, selector: str) -> str | None:
    """The text of the paragraphs, list points and headings inside the article container.

    Everything in ARTICLE_SKIP is left out; a block inside another block (`li > p`) is read
    once. At most ARTICLE_TEXT_MAX characters. None if the container isn't on the page or holds
    no readable text (empty, whitespace, or only skipped parts): both count as a failed read.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    containers = soup.select(selector)
    outer = [c for c in containers if not any(parent in containers for parent in c.parents)]
    parts: list[str] = []
    for container in outer:
        for unwanted in container.select(ARTICLE_SKIP):
            unwanted.decompose()
        blocks = container.find_all(_TEXT_BLOCKS)
        chosen = {id(block) for block in blocks}
        for block in blocks:
            if any(id(parent) in chosen for parent in block.parents):
                continue
            text = " ".join(block.get_text(" ").split())
            if text:
                parts.append(text)
    return " ".join(parts)[:ARTICLE_TEXT_MAX].rstrip() or None


# --- manual check ----------------------------------------------------------------------------


def main(argv=None) -> None:
    """`python -m haven.collect [--with-text]`: run the collect step once and print a table.

    Writes nothing. With --with-text, also opens the article pages of the `use` items and
    prints only how many characters were read (the text itself is never shown).
    """
    from haven.config import load_sources

    parser = argparse.ArgumentParser(prog="python -m haven.collect")
    parser.add_argument("--with-text", action="store_true", help="also read article text (lengths only)")
    args = parser.parse_args(argv)

    sources = load_sources()
    fetcher = Fetcher()
    result = run_collect(sources, fetcher, today=clock.today())
    items, failures = result.items, list(result.failures)
    if args.with_text:
        texts = add_article_text(items, sources, fetcher)
        items, failures = texts.items, failures + texts.failures

    names = {source.id: source.name for source in sources}
    print(f"{'source':28} {'access':13} {'published':25} headline")
    for item in items:
        line = f"{names.get(item.source, item.source)[:28]:28} {item.access:13} {item.published or 'no date':25} {item.headline}"
        if args.with_text:
            line += f"  [{len(item.article_text)} chars of text]" if item.article_text else "  [no text]"
        print(line)
    print(f"\n{result.sources_checked} sources read at {result.feeds_read_at}: {result.items_collected} items, "
          f"{result.duplicates} already seen, {len(result.items)} new.")
    for failure in failures:
        print(f"FAILURE  {failure['source']}: {failure['error']}")


if __name__ == "__main__":
    main()
