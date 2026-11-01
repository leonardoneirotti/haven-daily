"""Feed collectors (RSS) + PIN gap check (spec §4, §5.8, hard rules 12 and 13; issue #9).

Every feed here is written by us: the same structure as the real feeds, with
invented headlines and text (hard rule 13: no third-party article text in the
repo). The network is a fake; no test touches the internet or really waits.
"""

import json
from datetime import date, datetime, timezone

import pytest

from haven import feeds, storage
from haven.config import Source, load_sources
from haven.feeds import Item, collect_feed, parse_feed, rollover_gap
from haven.fetch import Fetcher, RawResponse, TransportError

# --- fakes and helpers ------------------------------------------------------------------


class FakeNet:
    """url -> response or exception. Unknown robots.txt = 404 (everything allowed)."""

    def __init__(self, routes):
        self.routes = dict(routes)
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append(url)
        answer = self.routes.get(url)
        if answer is None:
            if url.endswith("/robots.txt"):
                return RawResponse(404, {}, b"")
            raise TransportError("no route in test")
        if isinstance(answer, Exception):
            raise answer
        return answer


def fetcher_for(routes):
    net = FakeNet(routes)
    return Fetcher(transport=net, clock=lambda: 0.0, sleep=lambda s: None), net


def xml(body, status=200):
    return RawResponse(status, {"content-type": "application/rss+xml; charset=utf-8"}, body.encode("utf-8"))


def rss(*items, extra_ns=""):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        f'xmlns:content="http://purl.org/rss/1.0/modules/content/"{extra_ns}>'
        "<channel><title>Invented feed</title><link>https://feed.test/</link>"
        + "".join(items)
        + "</channel></rss>"
    )


def entry(title="Invented headline", link="https://feed.test/news/1", date="Sun, 01 Nov 2026 05:30:00 +0000", extra=""):
    parts = ["<item>"]
    if title is not None:
        parts.append(f"<title>{title}</title>")
    if link is not None:
        parts.append(f"<link>{link}</link>")
    if date is not None:
        parts.append(f"<pubDate>{date}</pubDate>")
    parts.append(extra)
    parts.append("</item>")
    return "".join(parts)


def source(verdict="use", urls=("https://feed.test/rss.xml",), id="test-feed", name="Test Feed", language="en", access="rss"):
    return Source(id=id, name=name, verdict=verdict, urls=tuple(urls), access=access, language=language)


FEED = "https://feed.test/rss.xml"
SECRET_SNIPPET = "Invented body text that must never leave memory"


# --- the common item shape ---------------------------------------------------------------


def test_use_feed_maps_to_the_common_item_shape():
    body = rss(entry(title="Fictional lock closed for maintenance", extra=f"<description>{SECRET_SNIPPET}</description>"))
    fetcher, _ = fetcher_for({FEED: xml(body)})

    result = collect_feed(source(), fetcher)

    assert result.failures == []
    [item] = result.items
    assert item.source == "test-feed"
    assert item.headline == "Fictional lock closed for maintenance"
    assert item.url == "https://feed.test/news/1"
    assert item.published == "2026-11-01T06:30:00+01:00"  # Amsterdam time
    assert item.language == "en"
    assert item.access == "full"
    assert item.snippet == SECRET_SNIPPET  # in memory, for the relevance filter


def test_record_is_what_gets_stored_and_never_holds_the_snippet(tmp_path):
    body = rss(entry(extra=f"<description>{SECRET_SNIPPET}</description>"))
    fetcher, _ = fetcher_for({FEED: xml(body)})
    [item] = collect_feed(source(), fetcher).items

    record = item.record()

    assert record == {
        "source": "test-feed",
        "headline": "Invented headline",
        "url": "https://feed.test/news/1",
        "published": "2026-11-01T06:30:00+01:00",
        "language": "en",
        "access": "full",
    }
    # The storage guard (hard rule 13) accepts it, and the text is nowhere in the file.
    written = storage.write("items", date(2026, 11, 1), [record], data_dir=tmp_path)
    assert SECRET_SNIPPET not in written.read_text(encoding="utf-8")


def test_snippet_is_not_shown_in_repr_so_it_cannot_leak_into_logs():
    body = rss(entry(extra=f"<description>{SECRET_SNIPPET}</description>"))
    fetcher, _ = fetcher_for({FEED: xml(body)})
    [item] = collect_feed(source(), fetcher).items
    assert SECRET_SNIPPET not in repr(item)


def test_snippet_is_plain_text_and_capped():
    long_html = "<![CDATA[<p>Invented <b>notice</b> &amp; more</p>" + " word" * 1000 + "]]>"
    fetcher, _ = fetcher_for({FEED: xml(rss(entry(extra=f"<description>{long_html}</description>")))})
    [item] = collect_feed(source(), fetcher).items
    assert item.snippet.startswith("Invented notice & more word")
    assert "<" not in item.snippet
    assert len(item.snippet) <= feeds.SNIPPET_MAX


def test_item_without_description_has_no_snippet():
    fetcher, _ = fetcher_for({FEED: xml(rss(entry()))})
    [item] = collect_feed(source(), fetcher).items
    assert item.snippet is None


# --- headline-only sources (hard rules 12 and 13) -----------------------------------------


def test_headline_only_item_carries_no_text_at_all():
    extra = f"<description>{SECRET_SNIPPET}</description><content:encoded><![CDATA[<p>{SECRET_SNIPPET}</p>]]></content:encoded>"
    fetcher, _ = fetcher_for({FEED: xml(rss(entry(extra=extra)))})

    [item] = collect_feed(source(verdict="headline-only", language="nl"), fetcher).items

    assert item.access == "headline-only"
    assert item.language == "nl"
    assert item.snippet is None
    assert SECRET_SNIPPET not in repr(item)
    assert SECRET_SNIPPET not in json.dumps(item.record())


def test_headline_only_source_never_fetches_the_article_page():
    links = [f"https://feed.test/news/{n}" for n in range(3)]
    fetcher, net = fetcher_for({FEED: xml(rss(*(entry(link=link) for link in links)))})

    collect_feed(source(verdict="headline-only"), fetcher)

    assert net.calls == ["https://feed.test/robots.txt", FEED]


def test_use_source_that_opts_out_of_ai_becomes_headline_only_with_a_note():
    robots = RawResponse(200, {}, b"User-agent: *\nAllow: /\nContent-Signal: ai-train=no\n")
    body = rss(entry(extra=f"<description>{SECRET_SNIPPET}</description>"))
    fetcher, _ = fetcher_for({"https://feed.test/robots.txt": robots, FEED: xml(body)})

    result = collect_feed(source(name="Test Feed"), fetcher)

    [item] = result.items
    assert item.access == "headline-only"
    assert item.snippet is None
    [failure] = result.failures
    assert failure["source"] == "Test Feed"
    assert "ai-train=no" in failure["error"]
    assert "SOURCES.md" in failure["error"]
    assert not failure["error"].startswith("Test Feed:")  # the page already shows the source name


# --- the configured RSS sources ----------------------------------------------------------

RSS_SOURCES = [s for s in load_sources() if s.fetched and s.access == "rss"]


def test_the_five_rss_sources_of_issue_9_are_configured():
    assert {s.id: s.verdict for s in RSS_SOURCES} == {
        "pin-notices": "use",
        "nieuwsblad-transport": "headline-only",
        "portseurope": "headline-only",
        "loadstar": "headline-only",
        "rtv-rijnmond": "headline-only",
    }


@pytest.mark.parametrize("configured", RSS_SOURCES, ids=lambda s: s.id)
def test_each_configured_feed_maps_with_the_right_access_and_language(configured):
    body = rss(entry(link="https://example.org/a/1", extra=f"<description>{SECRET_SNIPPET}</description>"))
    fetcher, _ = fetcher_for({url: xml(body) for url in configured.urls})

    result = collect_feed(configured, fetcher)

    assert result.failures == []
    [item] = result.items  # the same link in two feeds is one item
    assert item.source == configured.id
    assert item.language == configured.language
    if configured.verdict == "use":
        assert (item.access, item.snippet) == ("full", SECRET_SNIPPET)
    else:
        assert (item.access, item.snippet) == ("headline-only", None)


# --- several feeds for one source (Nieuwsblad Transport) ---------------------------------


def test_two_feeds_are_merged_and_duplicates_dropped_in_order():
    first, second = "https://feed.test/havens/feed/", "https://feed.test/tag/rotterdam/feed/"
    fetcher, _ = fetcher_for(
        {
            first: xml(rss(entry(title="A", link="https://feed.test/a"), entry(title="B", link="https://feed.test/b"))),
            second: xml(rss(entry(title="B again", link="https://feed.test/b#comments"), entry(title="C", link="https://feed.test/c"))),
        }
    )

    result = collect_feed(source(verdict="headline-only", urls=(first, second)), fetcher)

    assert [i.headline for i in result.items] == ["A", "B", "C"]
    assert [i.url for i in result.items] == ["https://feed.test/a", "https://feed.test/b", "https://feed.test/c"]


def test_one_broken_feed_of_two_still_returns_the_other():
    first, second = "https://feed.test/havens/feed/", "https://feed.test/tag/rotterdam/feed/"
    fetcher, _ = fetcher_for({first: xml("", status=500), second: xml(rss(entry(title="C")))})

    result = collect_feed(source(verdict="headline-only", urls=(first, second), name="NT"), fetcher)

    assert [i.headline for i in result.items] == ["C"]
    [failure] = result.failures
    assert failure["source"] == "NT"
    assert failure["error"].startswith(first)
    assert "HTTP 500" in failure["error"]


# --- broken feeds: a failure, never an exception -------------------------------------------


BROKEN = {
    "server error": xml("", status=500),
    "not found": xml("", status=404),
    "timeout": TimeoutError("slow"),
    "network down": TransportError("connection refused"),
    "not xml": xml("this is not a feed"),
    "cut off": xml(rss(entry())[:120]),
    "html page instead of a feed": xml("<html><body><p>Checking your browser</p></body></html>"),
    "atom instead of rss": xml('<feed xmlns="http://www.w3.org/2005/Atom"><title>x</title></feed>'),
    "rss without channel": xml('<rss version="2.0"></rss>'),
    "entity declarations": xml('<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "aaaa">]><rss version="2.0"><channel><title>&a;</title></channel></rss>'),
}


@pytest.mark.parametrize("answer", BROKEN.values(), ids=BROKEN.keys())
def test_a_broken_feed_returns_a_failure_not_an_exception(answer):
    fetcher, _ = fetcher_for({FEED: answer})

    result = collect_feed(source(name="Test Feed"), fetcher)

    assert result.items == []
    [failure] = result.failures
    assert failure["source"] == "Test Feed"
    assert failure["error"].startswith(FEED + ": ")
    assert "\n" not in failure["error"]


def test_robots_block_is_a_failure_and_the_feed_is_not_requested():
    robots = RawResponse(200, {}, b"User-agent: *\nDisallow: /rss.xml\n")
    fetcher, net = fetcher_for({"https://feed.test/robots.txt": robots, FEED: xml(rss(entry()))})

    result = collect_feed(source(), fetcher)

    assert result.items == []
    assert "robots.txt disallows" in result.failures[0]["error"]
    assert FEED not in net.calls


def test_an_unexpected_parser_error_is_still_a_failure(monkeypatch):
    def explode(body, feed_url, with_snippet):
        raise RuntimeError("bug in our own code")

    monkeypatch.setattr(feeds, "parse_feed", explode)
    fetcher, _ = fetcher_for({FEED: xml(rss(entry()))})

    result = collect_feed(source(), fetcher)

    assert result.items == []
    assert "RuntimeError: bug in our own code" in result.failures[0]["error"]


def test_an_empty_feed_is_not_a_failure():
    fetcher, _ = fetcher_for({FEED: xml(rss())})
    assert collect_feed(source(), fetcher) == feeds.FeedResult(items=[], failures=[])


def test_only_rss_sources_that_are_fetched_can_be_collected():
    fetcher, _ = fetcher_for({})
    with pytest.raises(ValueError, match="html"):
        collect_feed(source(access="html"), fetcher)
    with pytest.raises(ValueError, match="drop"):
        collect_feed(Source(id="x", name="X", verdict="drop"), fetcher)


# --- reading one entry ----------------------------------------------------------------


def parse_one(item_xml, feed_url=FEED, with_snippet=True):
    parsed = parse_feed(rss(item_xml).encode("utf-8"), feed_url, with_snippet=with_snippet)
    assert parsed.skipped == 0
    [one] = parsed.entries
    return one


def test_headline_whitespace_and_double_escaped_entities_are_cleaned():
    parsed = parse_one(entry(title="  Invented\n   strike &amp;#8216;called&amp;#8217; &amp;amp; more  "))
    assert parsed.headline == "Invented strike ‘called’ & more"


def test_cdata_headline():
    assert parse_one(entry(title="<![CDATA[Invented <b>quay</b> news]]>")).headline == "Invented quay news"


def test_relative_link_is_made_absolute():
    assert parse_one(entry(link="/news/7")).url == "https://feed.test/news/7"


def test_permalink_guid_is_used_when_there_is_no_link():
    item_xml = entry(link=None, extra='<guid isPermaLink="true">https://feed.test/news/9</guid>')
    assert parse_one(item_xml).url == "https://feed.test/news/9"


def test_guid_that_is_not_a_permalink_is_not_used_as_link():
    item_xml = entry(link=None, extra='<guid isPermaLink="false">12345</guid>')
    parsed = parse_feed(rss(item_xml).encode(), FEED, with_snippet=True)
    assert (parsed.entries, parsed.skipped) == ([], 1)


def test_headline_only_body_text_is_never_even_read():
    item_xml = entry(extra=f"<description>{SECRET_SNIPPET}</description>")
    assert parse_one(item_xml, with_snippet=False).snippet is None


def test_entries_without_headline_or_usable_link_are_skipped_and_reported():
    body = rss(
        entry(title=None),
        entry(title="   "),
        entry(link=None),
        entry(link="javascript:alert(1)"),
        entry(title="Kept", link="https://feed.test/ok"),
    )
    fetcher, _ = fetcher_for({FEED: xml(body)})

    result = collect_feed(source(name="Test Feed"), fetcher)

    assert [i.headline for i in result.items] == ["Kept"]
    [failure] = result.failures
    assert failure["error"] == f"{FEED}: 4 entries without a headline or link were skipped"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Sun, 01 Nov 2026 05:30:00 +0000", "2026-11-01T06:30:00+01:00"),
        ("Sun, 01 Nov 2026 05:30:00 GMT", "2026-11-01T06:30:00+01:00"),
        ("Sat, 31 Oct 2026 09:00:00 +0100", "2026-10-31T09:00:00+01:00"),
        ("Fri, 30 Oct 2026 09:00:00 +0200", "2026-10-30T08:00:00+01:00"),  # summer time in Amsterdam ended 25 Oct
        ("Sat, 01 Aug 2026 10:00:00 +0000", "2026-08-01T12:00:00+02:00"),
        ("Sun, 01 Nov 2026 05:30:00 -0000", "2026-11-01T06:30:00+01:00"),  # RFC 5322: -0000 = UTC
        ("Sun, 01 Nov 2026 05:30:00", "2026-11-01T06:30:00+01:00"),  # no zone: read as UTC, like -0000
        ("yesterday morning", None),
        ("Sat, 31 Feb 2026 10:00:00 +0000", None),
        ("", None),
    ],
)
def test_pubdate_is_stored_in_amsterdam_time(raw, expected):
    assert parse_one(entry(date=raw)).published == expected


def test_dc_date_is_used_when_there_is_no_pubdate():
    parsed = parse_one(entry(date=None, extra="<dc:date>2026-11-01T05:30:00Z</dc:date>"))
    assert parsed.published == "2026-11-01T06:30:00+01:00"


def test_missing_date_is_none_and_the_item_is_kept():
    parsed = parse_one(entry(date=None))
    assert parsed.published is None
    assert parsed.headline == "Invented headline"


# --- PIN gap check (spec §5.8) --------------------------------------------------------------


def item(published):
    return Item(source="pin-notices", headline="h", url="https://feed.test/x", published=published, language="en", access="full")


PREVIOUS_RUN = datetime(2026, 10, 31, 5, 50, tzinfo=timezone.utc)  # 06:50 Amsterdam


def test_gap_fires_when_the_oldest_item_is_newer_than_the_previous_run():
    items = [item("2026-11-01T06:10:00+01:00"), item("2026-10-31T07:05:00+01:00")]
    assert rollover_gap(items, PREVIOUS_RUN) == "some notices may have been missed (feed rolled over)"


def test_no_gap_when_the_feed_still_reaches_back_past_the_previous_run():
    items = [item("2026-11-01T06:10:00+01:00"), item("2026-10-31T06:40:00+01:00")]
    assert rollover_gap(items, PREVIOUS_RUN) is None


def test_no_gap_when_the_oldest_item_is_exactly_the_previous_run():
    assert rollover_gap([item("2026-10-31T06:50:00+01:00")], PREVIOUS_RUN) is None


def test_no_gap_check_without_a_previous_run_or_without_items():
    assert rollover_gap([item("2026-11-01T06:10:00+01:00")], None) is None
    assert rollover_gap([], PREVIOUS_RUN) is None


def test_undated_items_are_ignored_by_the_gap_check():
    assert rollover_gap([item(None), item("2026-10-31T06:00:00+01:00")], PREVIOUS_RUN) is None
    assert rollover_gap([item(None)], PREVIOUS_RUN) is None


def test_previous_run_without_timezone_is_refused():
    with pytest.raises(ValueError, match="timezone"):
        rollover_gap([item("2026-11-01T06:10:00+01:00")], datetime(2026, 10, 31, 6, 50))


PIN = next(s for s in load_sources() if s.id == "pin-notices")


def pin_fetcher(*dates):
    body = rss(*(entry(link=f"https://pin.test/{n}", date=d) for n, d in enumerate(dates)))
    return fetcher_for({PIN.urls[0]: xml(body)})[0]


def test_collecting_pin_records_the_gap_in_failures():
    fetcher = pin_fetcher("Sun, 01 Nov 2026 05:10:00 +0000", "Sat, 31 Oct 2026 07:00:00 +0000")

    result = collect_feed(PIN, fetcher, previous_run=PREVIOUS_RUN)

    assert len(result.items) == 2
    assert result.failures == [{"source": PIN.name, "error": "some notices may have been missed (feed rolled over)"}]


def test_collecting_pin_without_rollover_records_nothing():
    fetcher = pin_fetcher("Sun, 01 Nov 2026 05:10:00 +0000", "Sat, 31 Oct 2026 05:00:00 +0000")
    assert collect_feed(PIN, fetcher, previous_run=PREVIOUS_RUN).failures == []


def test_gap_check_is_only_for_pin():
    body = rss(entry(date="Sun, 01 Nov 2026 05:10:00 +0000"))
    fetcher, _ = fetcher_for({FEED: xml(body)})
    assert collect_feed(source(), fetcher, previous_run=PREVIOUS_RUN).failures == []


def test_no_gap_check_when_the_pin_feed_failed():
    fetcher, _ = fetcher_for({PIN.urls[0]: xml("", status=503)})
    result = collect_feed(PIN, fetcher, previous_run=PREVIOUS_RUN)
    assert len(result.failures) == 1
    assert "HTTP 503" in result.failures[0]["error"]
