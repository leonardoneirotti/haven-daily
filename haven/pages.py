"""Page collectors: read the HTML news lists into the common item shape (spec §4, §5.8; issue #10).

The HTML sources in config/sources.toml: Port Authority news, Contargo business news, ECT news,
Kuehne+Nagel SeaNews (all `use`) and the NL Times port tag page (headline-only).

Each source has one small parser below that finds the news cards on its page and reads a
headline, link and date from each. The items are the same `Item` the feed collectors return
(`haven/feeds.py`), so the collect step treats both alike. What may be kept depends on access:

- **headline-only** (hard rules 12 and 13): only headline, link and date. A teaser on the page
  is not read and no article page is opened.
- **full** (`use`): a teaser on the list, if there is one, is kept as `snippet` **in memory
  only**, for the relevance filter (§5.4), exactly like a feed's description.

**Kuehne+Nagel SeaNews: the Rotterdam paragraph only.** Of all K+N articles only the weekly
"Port operational updates" roundup is collected. Its article page is opened, and only the
section under the bold "Rotterdam:" label is kept (in memory, as `article_text` and
`snippet`). Nothing else from the page is passed on: not the intro, not the other ports. If
K+N becomes headline-only (terms check, owner checklist #43), only the verdict in config
changes: the weekly roundup's headline and link are kept and no article page is opened.

**A layout change is a failure, never an exception** (hard rule 9): a page on which no news
cards are found, a K+N roundup without a Rotterdam paragraph, a fetch error or even a bug in
our own parser is recorded as `{"source": <name>, "error": <one line>}` for build.failures,
and the other sources are not affected.

HTML is read with BeautifulSoup (`beautifulsoup4`) on Python's built-in `html.parser`: CSS
selectors keep each parser to a few readable lines, so when a site changes its layout the fix
is usually one selector.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from haven.clock import AMSTERDAM
from haven.config import Source
from haven.feeds import SNIPPET_MAX, FeedResult, Item
from haven.fetch import Fetcher, FetchError

ARTICLE_TEXT_MAX = 6000  # characters of article text kept in memory for the summariser (spec §5.8)

KN_SOURCE_ID = "kn-seanews"
KN_WEEKLY_PREFIX = "port operational updates"  # headline of K+N's weekly roundup, lower case

NO_ITEMS = "no news items found on the page (layout changed?)"
NO_PARAGRAPH = "no Rotterdam paragraph found in the weekly port update (layout changed?)"
NO_PARSER = "no page parser for this source in haven/pages.py, so it was not fetched"

_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_ROTTERDAM_LABEL = re.compile(r"(?:^|\s)Rotterdam\s*:?$", re.IGNORECASE)
_WRITTEN_DATE = re.compile(r"^(\d{1,2}) ([A-Za-z]+) (\d{4})$")  # "30 October 2026" (ECT)
_MONTHS = {
    name: number
    for number, name in enumerate(
        ("january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"),
        start=1,
    )
}


@dataclass(frozen=True)
class Card:
    """One news card as a parser found it. Headline or url may be missing (then it is skipped)."""

    headline: str | None
    url: str | None
    published: str | None
    snippet: str | None = field(default=None, repr=False)
    article_text: str | None = field(default=None, repr=False)


# (page, final url after redirects, read teasers?) -> cards in page order
Parser = Callable[[BeautifulSoup, str, bool], list[Card]]


# --- one parser per page ------------------------------------------------------------------


def parse_port_authority(soup: BeautifulSoup, base_url: str, with_snippet: bool) -> list[Card]:
    """Drupal cards `div.news-item`: link, `<time datetime>`, `h3` title. No teaser on the list.

    The link's `title` attribute holds the Dutch headline; the visible `h3` is the English one.
    """
    return [
        Card(
            headline=_text(card.select_one(".news-item__title")),
            url=_url(base_url, _attr(card.select_one("a.news-item__link"), "href")),
            published=page_date(_attr(card.select_one("time[datetime]"), "datetime")),
        )
        for card in soup.select("div.news-item")
    ]


def parse_contargo(soup: BeautifulSoup, base_url: str, with_snippet: bool) -> list[Card]:
    """TYPO3 cards `div.news-item`: `h5` title, `<time datetime="YYYY-MM-DD">`, teaser paragraphs."""
    cards = []
    for card in soup.select("div.news-item"):
        snippet = None
        if with_snippet:
            snippet = _cap(" ".join(filter(None, (_text(p) for p in card.select("div.text p")))), SNIPPET_MAX)
        cards.append(
            Card(
                headline=_text(card.select_one("h5")),
                url=_url(base_url, _attr(card.select_one("a[href]"), "href")),
                published=page_date(_attr(card.select_one("time[datetime]"), "datetime")),
                snippet=snippet,
            )
        )
    return cards


def parse_ect(soup: BeautifulSoup, base_url: str, with_snippet: bool) -> list[Card]:
    """Drupal teasers `node--type-nieuws`: title, written date ("30 October 2026"), body, "Read more"."""
    cards = []
    for card in soup.select("div.node--type-nieuws"):
        link = card.select_one("li.node-readmore a[href]") or card.select_one(".field--name-node-title a[href]")
        cards.append(
            Card(
                headline=_text(card.select_one(".field--name-node-title")),
                url=_url(base_url, _attr(link, "href")),
                published=page_date(_text(card.select_one(".field--name-node-post-date"))),
                snippet=_cap(_text(card.select_one(".field--name-body")), SNIPPET_MAX) if with_snippet else None,
            )
        )
    return cards


def parse_nl_times(soup: BeautifulSoup, base_url: str, with_snippet: bool) -> list[Card]:
    """Drupal `div.news-card`: title link and `<time datetime>`. Headline-only: nothing else is read."""
    cards = []
    for card in soup.select("div.news-card"):
        link = card.select_one(".news-card__title a")
        cards.append(
            Card(
                headline=_text(link),
                url=_url(base_url, _attr(link, "href")),
                published=page_date(_attr(card.select_one(".news-card__date time[datetime]"), "datetime")),
            )
        )
    return cards


def parse_kn_list(soup: BeautifulSoup, base_url: str, with_snippet: bool) -> list[Card]:
    """Astro list: featured cards `a.featured-card` and list headlines `h2.article__headline a`.

    The large featured card has its headline in an `h2`, the small ones in an `h3` with another
    class, so the first heading in the card is used. The list cards carry no date; the weekly
    roundup's date comes from its article page.
    """
    cards = [
        Card(headline=_text(card.select_one("h2, h3")), url=_url(base_url, _attr(card, "href")), published=None)
        for card in soup.select("a.featured-card")
    ]
    cards += [
        Card(headline=_text(link), url=_url(base_url, _attr(link, "href")), published=None)
        for link in soup.select("h2.article__headline a")
    ]
    return cards


PARSERS: dict[str, Parser] = {
    "port-authority-news": parse_port_authority,
    "contargo-news": parse_contargo,
    "ect-news": parse_ect,
    KN_SOURCE_ID: parse_kn_list,
    "nl-times": parse_nl_times,
}


# --- collecting one source -------------------------------------------------------------


def collect_page(source: Source, fetcher: Fetcher) -> FeedResult:
    """Read every page URL of an HTML source. Never raises for a broken page or a layout change."""
    if not source.fetched:
        raise ValueError(f"{source.id}: verdict 'drop' sources are never fetched")
    if source.access != "html":
        raise ValueError(f"{source.id}: access is {source.access!r}; collect_page reads only 'html' sources")

    failures: list[dict] = []

    def fail(error: str) -> None:
        failures.append({"source": source.name, "error": error})

    parser = PARSERS.get(source.id)
    if parser is None:
        fail(NO_PARSER)
        return FeedResult(items=[], failures=failures)

    access = fetcher.source_access(source)
    if access.note:
        fail(access.note.removeprefix(f"{source.name}: "))  # the page already shows the name
    full = access.verdict == "use"

    cards: list[Card] = []
    seen: set[str] = set()
    for url in source.urls:
        try:
            response = fetcher.fetch(url)
            found = parser(BeautifulSoup(response.text(), "html.parser"), response.url, full)
        except FetchError as error:
            fail(f"{url}: {error.problem}")
            continue
        except Exception as error:  # a bug of ours on odd input must not stop the morning run
            fail(f"{url}: unexpected error ({type(error).__name__}: {error})")
            continue
        if not found:
            fail(f"{url}: {NO_ITEMS}")
            continue
        usable = [card for card in found if card.headline and card.url]
        if len(usable) < len(found):
            fail(f"{url}: {len(found) - len(usable)} entries without a headline or link were skipped")
        for card in usable:
            if card.url not in seen:  # the same story twice on one page (e.g. featured and listed)
                seen.add(card.url)
                cards.append(card)

    if source.id == KN_SOURCE_ID:
        cards = _kn_weekly_updates(cards, fetcher, full, fail)

    items = [
        Item(
            source=source.id,
            headline=card.headline,
            url=card.url,
            published=card.published,
            language=source.language,
            access="full" if full else "headline-only",
            snippet=card.snippet if full else None,
            article_text=card.article_text if full else None,
        )
        for card in cards
    ]
    return FeedResult(items=items, failures=failures)


def _kn_weekly_updates(cards: list[Card], fetcher: Fetcher, full: bool, fail: Callable[[str], None]) -> list[Card]:
    """Keep only K+N's weekly roundups; for `use`, replace each with its Rotterdam paragraph.

    No roundup on the list is normal (it is on the first page only a few days a week), so it is
    not a failure. A roundup whose Rotterdam paragraph can't be found is, and gives no item.
    """
    weekly = [card for card in cards if card.headline.lower().startswith(KN_WEEKLY_PREFIX)]
    if not full:
        return weekly  # headline-only: the article page is never opened
    kept = []
    for card in weekly:
        try:
            response = fetcher.fetch(card.url)
            soup = BeautifulSoup(response.text(), "html.parser")
            paragraph = _rotterdam_paragraph(soup)
            published = _json_ld_date(soup)
        except FetchError as error:
            fail(f"{card.url}: {error.problem}")
            continue
        except Exception as error:
            fail(f"{card.url}: unexpected error ({type(error).__name__}: {error})")
            continue
        if not paragraph:
            fail(f"{card.url}: {NO_PARAGRAPH}")
            continue
        kept.append(
            Card(
                headline=card.headline,
                url=card.url,
                published=published,
                snippet=_cap(paragraph, SNIPPET_MAX),
                article_text=paragraph,
            )
        )
    return kept


# --- the Rotterdam paragraph -------------------------------------------------------------


def rotterdam_paragraph(page_html: str) -> str | None:
    """The text under the bold "Rotterdam:" label of a K+N article, or None if there is none."""
    return _rotterdam_paragraph(BeautifulSoup(page_html, "html.parser"))


def _rotterdam_paragraph(soup: BeautifulSoup) -> str | None:
    """In the roundup each port is a bold label ("Netherlands <br>Rotterdam:") followed by its text.

    The paragraph runs from the label to the next bold label, a heading, or the end of the
    block (`p`, `li`, `div`) the label is in, whichever comes first. The label itself and
    everything before it (e.g. an intro that also mentions Rotterdam) are left out.
    """
    body = soup.select_one("div.article__content")
    if body is None:
        return None
    for label in body.find_all(["strong", "b"]):
        if not _ROTTERDAM_LABEL.search(_text(label) or ""):
            continue
        block = label.find_parent(["p", "li", "div"])
        parts: list[str] = []
        for element in label.next_elements:
            if not _inside(element, block):
                break
            if _inside(element, label):
                continue
            if isinstance(element, Tag):
                if element.name in _HEADINGS or (element.name in ("strong", "b") and _text(element)):
                    break
                if element.name == "br":
                    parts.append(" ")
            elif type(element) is NavigableString:  # not comments, scripts or CDATA
                parts.append(str(element))
        text = _cap(" ".join("".join(parts).split()), ARTICLE_TEXT_MAX)
        if text:
            return text
    return None


def _inside(element, ancestor: Tag | None) -> bool:
    return ancestor is not None and any(parent is ancestor for parent in element.parents)


def _json_ld_date(soup: BeautifulSoup) -> str | None:
    """`datePublished` from the page's JSON-LD (schema.org NewsArticle), in Amsterdam time."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        found = _find_key(data, "datePublished")
        if isinstance(found, str):
            return page_date(found)
    return None


def _find_key(data, key: str):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        data = list(data.values())
    if isinstance(data, list):
        for value in data:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


# --- small helpers ----------------------------------------------------------------------


def page_date(raw: str | None) -> str | None:
    """A date as a page writes it -> ISO 8601. Unreadable or missing = None, never a guess.

    - A timestamp is converted to Amsterdam time, whole seconds. Without a zone it is read as
      Amsterdam time (all these publishers write local time).
    - A date without a time ("2026-10-30", "30 October 2026") stays a date: "2026-10-30".
      No time of day is made up.
    """
    raw = " ".join((raw or "").split())
    if not raw:
        return None
    written = _WRITTEN_DATE.match(raw)
    if written:
        month = _MONTHS.get(written.group(2).lower())
        if month is None:
            return None
        try:
            return date(int(written.group(3)), month, int(written.group(1))).isoformat()
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            return None
    if not re.match(r"\d{4}-\d{2}-\d{2}[T ]\d", raw):
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=AMSTERDAM)
    return moment.astimezone(AMSTERDAM).replace(microsecond=0).isoformat()


def _text(element: Tag | None) -> str | None:
    """Visible text of an element on one line (comments left out), or None."""
    if element is None:
        return None
    return " ".join(element.get_text(" ").split()) or None


def _attr(element: Tag | None, name: str) -> str | None:
    if element is None:
        return None
    value = element.get(name)
    return value.strip() if isinstance(value, str) else None


def _url(base_url: str, href: str | None) -> str | None:
    """Absolute http(s) link without #fragment, like the feed collectors; else None."""
    if not href:
        return None
    url = urldefrag(urljoin(base_url, href)).url
    return url if url.startswith(("https://", "http://")) else None


def _cap(text: str | None, limit: int) -> str | None:
    return (text or "")[:limit].rstrip() or None


# --- manual smoke run ---------------------------------------------------------------------


def main() -> None:
    """`python -m haven.pages`: read the real pages once and print headlines and links only."""
    from haven.config import load_sources

    fetcher = Fetcher()
    for source in load_sources():
        if not source.fetched or source.access != "html":
            continue
        result = collect_page(source, fetcher)
        print(f"\n== {source.name} ({len(result.items)} items)")
        for item in result.items:
            print(f"  {item.published or 'no date':25}  {item.access:13}  {item.headline}\n{'':43}{item.url}")
            if item.article_text:
                print(f"{'':43}(Rotterdam paragraph: {len(item.article_text)} characters, in memory only)")
        for failure in result.failures:
            print(f"  FAILURE: {failure['error']}")


if __name__ == "__main__":
    main()
