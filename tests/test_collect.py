"""Collect step (spec §5.1 step 1, §5.4, §5.8, §6.1, hard rules 9 and 13; issue #11).

Fake sources, fake collectors and fake stored days in pytest's `tmp_path`; article pages
are written by us with the real containers and invented text (hard rule 13). The network
is a fake; no test touches the internet or really waits.
"""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from haven import collect, storage
from haven.clock import AMSTERDAM
from haven.collect import add_article_text, previous_feeds_read_at, run_collect, url_key
from haven.config import Source, load_sources
from haven.feeds import PIN_SOURCE_ID, FeedResult, Item
from haven.fetch import Fetcher, RawResponse, TransportError
from haven.pages import KN_SOURCE_ID

TODAY = date(2026, 11, 20)
NOW = datetime(2026, 11, 20, 6, 46, 5, tzinfo=AMSTERDAM)
SECRET = "Invented article sentence that must never reach a file"

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


def fetcher_for(routes=()):
    net = FakeNet(routes)
    return Fetcher(transport=net, clock=lambda: 0.0, sleep=lambda s: None), net


def html(body, status=200, headers=None):
    return RawResponse(status, headers or {"content-type": "text/html; charset=utf-8"}, body.encode("utf-8"))


def src(id, name=None, verdict="use", access="rss", language="en"):
    return Source(id=id, name=name or f"Source {id}", verdict=verdict, urls=(f"https://{id}.test/",),
                  access=access, language=language)


def item(source="a", n=1, url=None, access="full", **extra):
    return Item(source=source, headline=f"Invented headline {n}", url=url or f"https://{source}.test/news/{n}",
                published="2026-11-20T05:00:00+01:00", language="en", access=access, **extra)


class FakeCollectors:
    """source id -> FeedResult (or exception); records what each call was given."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def __call__(self, source, fetcher, previous_run):
        self.calls.append((source.id, previous_run))
        answer = self.results.get(source.id, FeedResult(items=[], failures=[]))
        if isinstance(answer, Exception):
            raise answer
        return answer


def ok(*items):
    return FeedResult(items=list(items), failures=[])


def store_items(tmp_path, day, *items):
    storage.write("items", day, [i.record() if isinstance(i, Item) else i for i in items], data_dir=tmp_path)


def store_brief(tmp_path, day, build):
    storage.write("briefs", day, {"date": day.isoformat(), "items": [], "status": [], "corrections": [],
                                  "built_at": f"{day.isoformat()}T06:52:00+01:00", "build": build}, data_dir=tmp_path)


def run(tmp_path, sources, results, today=TODAY):
    collectors = FakeCollectors(results)
    fetcher, _ = fetcher_for()
    result = run_collect(sources, fetcher, today=today, data_dir=tmp_path, now=lambda: NOW, collector=collectors)
    return result, collectors


# --- every source, one failing never stops the others ----------------------------------


def test_every_fetched_source_is_collected_in_config_order_and_dropped_ones_never(tmp_path):
    sources = [src("a"), src("b", verdict="headline-only", access="html"), src("gone", verdict="drop"), src("c")]
    result, collectors = run(tmp_path, sources, {"a": ok(item("a")), "b": ok(item("b", access="headline-only")),
                                                 "c": ok(item("c"))})
    assert [c[0] for c in collectors.calls] == ["a", "b", "c"]
    assert [i.source for i in result.items] == ["a", "b", "c"]
    assert result.sources_checked == 3
    assert result.items_collected == 3
    assert result.failures == []


def test_one_failing_source_never_stops_the_others_and_is_listed_by_name(tmp_path):
    sources = [src("a", name="Alpha"), src("b", name="Bravo"), src("c", name="Charlie")]
    result, _ = run(tmp_path, sources, {
        "a": RuntimeError("invented crash"),
        "b": FeedResult(items=[item("b")], failures=[{"source": "Bravo", "error": "https://b.test/: HTTP 500"}]),
        "c": ok(item("c")),
    })
    assert [i.source for i in result.items] == ["b", "c"]
    assert result.failures == [
        {"source": "Alpha", "error": "unexpected error (RuntimeError: invented crash)"},
        {"source": "Bravo", "error": "https://b.test/: HTTP 500"},
    ]


def test_the_real_dispatch_reads_rss_with_feeds_and_html_with_pages(monkeypatch):
    seen = []
    monkeypatch.setattr(collect, "collect_feed", lambda s, f, p: seen.append(("feed", s.id, p)) or ok())
    monkeypatch.setattr(collect, "collect_page", lambda s, f: seen.append(("page", s.id)) or ok())
    previous = datetime(2026, 11, 19, 6, 45, tzinfo=AMSTERDAM)
    collect.collect_source(src("r"), None, previous)
    collect.collect_source(src("h", access="html"), None, previous)
    assert seen == [("feed", "r", previous), ("page", "h")]


# --- duplicates: once, here, by normalised link ------------------------------------------


@pytest.mark.parametrize(
    "a, b",
    [
        ("https://www.ect.nl/en/news/x", "http://ect.nl/en/news/x"),  # scheme and www. ignored
        ("https://ECT.nl/en/news/x", "https://ect.nl/en/news/x"),  # host is case-insensitive
        ("https://ect.nl/en/news/x/", "https://ect.nl/en/news/x"),  # trailing slash ignored
        ("https://ect.nl:443/en/news/x", "https://ect.nl/en/news/x"),  # default port ignored
        ("https://ect.nl/", "https://ect.nl"),
    ],
)
def test_url_key_treats_spelling_variants_of_one_link_as_the_same(a, b):
    assert url_key(a) == url_key(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("https://ect.nl/en/news/x", "https://ect.nl/EN/news/x"),  # paths can be case-sensitive
        ("https://pin.test/notice?id=1", "https://pin.test/notice?id=2"),  # query can identify the article
        ("https://ect.nl/en/news/x", "https://ect.com/en/news/x"),
        ("https://a.test/news/1", "https://a.test/news/1/2"),
    ],
)
def test_url_key_keeps_different_links_apart(a, b):
    assert url_key(a) != url_key(b)


def test_items_seen_in_the_last_14_days_are_not_returned_again(tmp_path):
    store_items(tmp_path, TODAY - timedelta(days=1), item("a", 1))
    store_items(tmp_path, TODAY - timedelta(days=14), item("a", 2))  # oldest day still checked
    store_items(tmp_path, TODAY - timedelta(days=15), item("a", 3))  # too old: may come back
    todays = [item("a", n) for n in (1, 2, 3, 4)]
    result, _ = run(tmp_path, [src("a")], {"a": ok(*todays)})
    assert [i.headline for i in result.items] == ["Invented headline 3", "Invented headline 4"]
    assert result.items_collected == 4
    assert result.duplicates == 2


def test_a_link_written_differently_still_counts_as_seen(tmp_path):
    store_items(tmp_path, TODAY - timedelta(days=3), item("a", url="http://www.a.test/news/1/"))
    result, _ = run(tmp_path, [src("a")], {"a": ok(item("a", url="https://a.test/news/1"))})
    assert result.items == []


@pytest.mark.parametrize(
    "a, b",
    [
        ("https://a.test/news/1#comments", "https://a.test/news/1"),
        ("https://a.test/news/1#top", "https://a.test/news/1#bottom"),
        ("https://a.test/n?id=5#x", "https://a.test/n?id=5"),
    ],
)
def test_url_key_ignores_the_fragment(a, b):
    """Owner's decision (1 Nov 2026): the #fragment never makes a link a different one."""
    assert url_key(a) == url_key(b)


@pytest.mark.parametrize(
    "a, b, same",
    [
        ("https://a.test/n?id=5&utm_source=rss&utm_medium=feed", "https://a.test/n?id=5", True),
        ("https://a.test/n?utm_campaign=autumn", "https://a.test/n", True),  # nothing left: no "?"
        ("https://a.test/n?UTM_Source=rss&id=5", "https://a.test/n?id=5", True),  # name case doesn't matter
        ("https://a.test/n?utm_source=a&id=5&page=2", "https://a.test/n?id=5&page=2", True),  # others kept, in order
        ("https://a.test/n?id=5&utm_source=rss", "https://a.test/n?id=6", False),  # other parameters still count
        ("https://a.test/n?ref=rss", "https://a.test/n", False),  # only utm_* is stripped
        ("https://a.test/n?xutm_source=1", "https://a.test/n", False),  # must start with utm_
    ],
)
def test_url_key_strips_only_utm_parameters(a, b, same):
    """Owner's decision (1 Nov 2026): utm_* tracking parameters are ignored; every other one is kept."""
    assert (url_key(a) == url_key(b)) is same


def test_a_stored_link_with_a_fragment_or_utm_tags_counts_as_seen(tmp_path):
    store_items(tmp_path, TODAY - timedelta(days=2),
                item("a", 1, url="https://a.test/news/1#comments"),
                item("a", 2, url="https://a.test/news/2?utm_source=rss&id=2"))
    result, _ = run(tmp_path, [src("a")], {"a": ok(item("a", 1, url="https://a.test/news/1"),
                                                   item("a", 2, url="https://a.test/news/2?id=2&utm_medium=feed"),
                                                   item("a", 3, url="https://a.test/news/2?id=3"))})
    assert [i.url for i in result.items] == ["https://a.test/news/2?id=3"]
    assert result.duplicates == 2


def test_the_same_link_from_two_sources_today_is_kept_once_first_source_wins(tmp_path):
    shared = "https://shared.test/story"
    result, _ = run(tmp_path, [src("a"), src("b")], {"a": ok(item("a", url=shared)), "b": ok(item("b", url=shared))})
    assert [i.source for i in result.items] == ["a"]
    assert result.duplicates == 1


def test_a_broken_stored_day_is_a_failure_and_the_other_days_still_count(tmp_path):
    store_items(tmp_path, TODAY - timedelta(days=2), item("a", 1))
    broken = storage.path("items", TODAY - timedelta(days=1), tmp_path)
    broken.write_text('{"url": "https://a.test/news/2"}\n{not json\n', encoding="utf-8")
    result, _ = run(tmp_path, [src("a")], {"a": ok(item("a", 1), item("a", 3))})
    assert [i.headline for i in result.items] == ["Invented headline 3"]
    [failure] = result.failures
    assert failure["source"] == collect.DUPLICATE_CHECK
    assert broken.name in failure["error"] and "line 2" in failure["error"]


# --- feed read time and previous_run (PIN gap check) -------------------------------------


def test_the_run_records_when_it_started_reading_the_sources(tmp_path):
    result, _ = run(tmp_path, [src("a")], {})
    assert result.feeds_read_at == "2026-11-20T06:46:05+01:00"


def test_previous_run_comes_from_the_latest_brief_and_reaches_the_collectors(tmp_path):
    store_brief(tmp_path, TODAY - timedelta(days=2), {"feeds_read_at": "2026-11-18T06:45:10+01:00"})
    store_brief(tmp_path, TODAY - timedelta(days=1), {"feeds_read_at": "2026-11-19T07:46:02+01:00"})
    _, collectors = run(tmp_path, [src("a"), src("b")], {})
    expected = datetime(2026, 11, 19, 7, 46, 2, tzinfo=AMSTERDAM)
    assert collectors.calls == [("a", expected), ("b", expected)]


def test_no_earlier_brief_means_no_previous_run(tmp_path):
    assert previous_feeds_read_at(TODAY, data_dir=tmp_path) is None
    _, collectors = run(tmp_path, [src("a")], {})
    assert collectors.calls == [("a", None)]


def test_a_brief_without_a_read_time_is_skipped_for_an_older_one(tmp_path):
    """Using an older time can only make the gap check warn more, never less (safe side)."""
    store_brief(tmp_path, TODAY - timedelta(days=3), {"feeds_read_at": "2026-11-17T06:45:00+01:00"})
    store_brief(tmp_path, TODAY - timedelta(days=1), {"sources_checked": 9})
    assert previous_feeds_read_at(TODAY, data_dir=tmp_path) == datetime(2026, 11, 17, 6, 45, tzinfo=AMSTERDAM)


def test_a_brief_older_than_14_days_is_not_used(tmp_path):
    store_brief(tmp_path, TODAY - timedelta(days=15), {"feeds_read_at": "2026-11-05T06:45:00+01:00"})
    assert previous_feeds_read_at(TODAY, data_dir=tmp_path) is None


def test_an_unreadable_read_time_is_ignored(tmp_path):
    store_brief(tmp_path, TODAY - timedelta(days=1), {"feeds_read_at": "yesterday morning"})
    store_brief(tmp_path, TODAY - timedelta(days=2), {"feeds_read_at": "2026-11-18T06:45:00"})  # no zone: refused
    assert previous_feeds_read_at(TODAY, data_dir=tmp_path) is None


# --- K+N gone quiet: no item in 14 days -----------------------------------------------------

KN = Source(id=KN_SOURCE_ID, name="Kuehne+Nagel SeaNews", verdict="use", urls=("https://kn.test/news",),
            access="html", language="en")
QUIET = {"source": "Kuehne+Nagel SeaNews", "error": collect.KN_QUIET}


def first_run(tmp_path, days_ago):
    store_items(tmp_path, TODAY - timedelta(days=days_ago), item("a", 99))


def test_kn_check_waits_until_14_days_after_the_first_collect_run(tmp_path):
    first_run(tmp_path, days_ago=13)
    result, _ = run(tmp_path, [src("a"), KN], {})
    assert QUIET not in result.failures


def test_kn_check_starts_14_days_after_the_first_collect_run_of_any_source(tmp_path):
    """No K+N item ever stored: a collector broken from day one is still caught."""
    first_run(tmp_path, days_ago=14)
    result, _ = run(tmp_path, [src("a"), KN], {})
    assert QUIET in result.failures


def test_no_check_on_the_very_first_run(tmp_path):
    result, _ = run(tmp_path, [src("a"), KN], {})
    assert QUIET not in result.failures


def test_a_kn_item_in_the_13_days_before_today_is_enough(tmp_path):
    first_run(tmp_path, days_ago=30)
    store_items(tmp_path, TODAY - timedelta(days=13), item(KN_SOURCE_ID, 1))
    result, _ = run(tmp_path, [src("a"), KN], {})
    assert QUIET not in result.failures


def test_a_kn_item_14_days_ago_is_outside_the_window(tmp_path):
    first_run(tmp_path, days_ago=30)
    store_items(tmp_path, TODAY - timedelta(days=14), item(KN_SOURCE_ID, 1))
    result, _ = run(tmp_path, [src("a"), KN], {})
    assert QUIET in result.failures


def test_a_new_kn_item_today_is_enough(tmp_path):
    first_run(tmp_path, days_ago=30)
    result, _ = run(tmp_path, [src("a"), KN], {KN_SOURCE_ID: ok(item(KN_SOURCE_ID, 1))})
    assert QUIET not in result.failures


def test_a_headline_only_kn_item_counts_too(tmp_path):
    first_run(tmp_path, days_ago=30)
    store_items(tmp_path, TODAY - timedelta(days=5), item(KN_SOURCE_ID, 1, access="headline-only"))
    result, _ = run(tmp_path, [src("a"), KN], {})
    assert QUIET not in result.failures


def test_no_kn_check_while_kn_is_dropped(tmp_path):
    first_run(tmp_path, days_ago=30)
    result, _ = run(tmp_path, [src("a"), replace(KN, verdict="drop")], {})
    assert QUIET not in result.failures


def test_the_quiet_note_is_one_line_for_the_page(tmp_path):
    assert "\n" not in collect.KN_QUIET and "14 days" in collect.KN_QUIET


# --- article text: in memory only ------------------------------------------------------------

PA_ARTICLE = "https://www.portofrotterdam.com/en/news-and-press-releases/invented-quay"
CONTARGO_ARTICLE = "https://www.contargo.net/en/business/business-news/detail-business/invented/"
ECT_ARTICLE = "https://www.ect.nl/en/news/news-feed/invented-gate-hours"


def page(body):
    return f"<!DOCTYPE html><html><head><title>Invented</title></head><body><nav><ul><li>Invented menu item that is long enough</li></ul></nav>{body}<footer><p>Invented footer text</p></footer></body></html>"


PA_PAGE = page(
    '<main><div class="main-content"><div class="content-wrapper news-page portofrotterdam-page">'
    '<div class="hero hero--without-background-img"><h1>Invented headline</h1><p>31 / 10 / 2026</p></div>'
    f'<p class="has-medium-font-size">{SECRET} One.</p><p>Invented second paragraph.</p>'
    '<h2 class="wp-block-heading">Invented subheading</h2><ul><li>Invented list point.</li></ul>'
    '<div class="views-element-container block"><h3>Invented more news</h3><ul><li>Other invented story</li></ul></div>'
    "</div></div></main>"
)
CONTARGO_PAGE = page(
    '<main><div class="content-wrap content-wrap-large"><div class="text"><h1>Invented page title</h1></div></div>'
    f'<div class="content-wrap content-wrap-small"><div class="text"><h2>Invented heading</h2><p>{SECRET} Two.</p>'
    "<p>Invented waiting time paragraph.</p></div></div></main>"
)
ECT_PAGE = page(
    '<div class="block block-system block-system-main-block"><div class="layout layout--onecol">'
    f'<div class="clearfix text-formatted field field--name-body"><p>{SECRET} Three.</p>'
    "<ul><li><p>Invented point inside a paragraph.</p></li></ul></div></div></div>"
)


def use_item(source, url, **extra):
    return Item(source=source, headline="Invented headline", url=url, published=None, language="en",
                access="full", **extra)


SOURCES = list(load_sources())


def test_article_text_is_read_from_each_sites_article_container_only():
    fetcher, _ = fetcher_for({PA_ARTICLE: html(PA_PAGE), CONTARGO_ARTICLE: html(CONTARGO_PAGE),
                              ECT_ARTICLE: html(ECT_PAGE)})
    result = add_article_text([use_item("port-authority-news", PA_ARTICLE), use_item("contargo-news", CONTARGO_ARTICLE),
                               use_item("ect-news", ECT_ARTICLE)], SOURCES, fetcher)
    assert result.failures == []
    pa, contargo, ect = (i.article_text for i in result.items)
    assert pa == f"{SECRET} One. Invented second paragraph. Invented subheading Invented list point."
    assert contargo == f"Invented page title Invented heading {SECRET} Two. Invented waiting time paragraph."
    assert ect == f"{SECRET} Three. Invented point inside a paragraph."
    for text in (pa, contargo, ect):
        for noise in ("menu item", "footer", "more news", "Other invented story", "31 / 10"):
            assert noise not in text


def test_article_text_is_capped():
    long = "Invented word. " * 1000
    fetcher, _ = fetcher_for({ECT_ARTICLE: html(page(
        f'<div class="block-system-main-block"><div class="field--name-body"><p>{long}</p></div></div>'))})
    [done] = add_article_text([use_item("ect-news", ECT_ARTICLE)], SOURCES, fetcher).items
    assert len(done.article_text) <= collect.ARTICLE_TEXT_MAX


def test_headline_only_items_never_get_their_page_opened():
    fetcher, net = fetcher_for()
    nlt = Item(source="nl-times", headline="Invented", url="https://nltimes.nl/2026/11/20/invented",
               published=None, language="en", access="headline-only")
    result = add_article_text([nlt], SOURCES, fetcher)
    assert result.items == [nlt] and result.failures == []
    assert net.calls == []


@pytest.mark.parametrize("source_id", [KN_SOURCE_ID, PIN_SOURCE_ID])
def test_text_that_is_already_set_is_never_replaced(source_id):
    """K+N holds only its Rotterdam paragraph; opening the article again would pass on all of it."""
    fetcher, net = fetcher_for()
    already = use_item(source_id, "https://mykn.kuehne-nagel.com/news/article/invented", article_text="Only this.")
    result = add_article_text([already], SOURCES, fetcher)
    assert result.items[0].article_text == "Only this."
    assert net.calls == []


def test_an_article_that_cannot_be_fetched_is_a_failure_and_the_item_stays():
    fetcher, _ = fetcher_for({ECT_ARTICLE: html("gone", status=404)})
    result = add_article_text([use_item("ect-news", ECT_ARTICLE)], SOURCES, fetcher)
    [kept] = result.items
    assert kept.article_text is None and kept.access == "full"
    assert result.failures == [{"source": "ECT news", "error": f"{ECT_ARTICLE}: HTTP 404"}]


def test_an_article_page_whose_layout_changed_is_a_failure_and_the_item_stays():
    fetcher, _ = fetcher_for({ECT_ARTICLE: html(page("<div class='redesign'><p>Invented</p></div>"))})
    result = add_article_text([use_item("ect-news", ECT_ARTICLE)], SOURCES, fetcher)
    assert result.items[0].article_text is None
    assert result.failures == [{"source": "ECT news", "error": f"{ECT_ARTICLE}: {collect.NO_ARTICLE_TEXT}"}]


def test_an_article_site_that_opts_out_of_ai_makes_the_item_headline_only():
    robots = "User-agent: GPTBot\nDisallow: /\n"
    fetcher, net = fetcher_for({"https://www.ect.nl/robots.txt": html(robots, headers={"content-type": "text/plain"}),
                                ECT_ARTICLE: html(ECT_PAGE)})
    result = add_article_text([use_item("ect-news", ECT_ARTICLE, snippet="Invented teaser")], SOURCES, fetcher)
    [done] = result.items
    assert done.access == "headline-only" and done.snippet is None and done.article_text is None
    assert ECT_ARTICLE not in net.calls
    [note] = result.failures
    assert note["source"] == "ECT news" and "GPTBot" in note["error"] and "headline-only" in note["error"]


def test_a_use_source_without_an_article_reader_is_a_failure_not_a_crash():
    fetcher, net = fetcher_for()
    odd = Source(id="invented", name="Invented source", verdict="use", urls=("https://invented.test/",),
                 access="html", language="en")
    result = add_article_text([use_item("invented", "https://invented.test/a")], SOURCES + [odd], fetcher)
    assert result.items[0].article_text is None
    assert result.failures == [{"source": "Invented source", "error": f"https://invented.test/a: {collect.NO_READER}"}]
    assert net.calls == []


def test_an_unexpected_error_while_reading_an_article_is_a_failure(monkeypatch):
    monkeypatch.setattr(collect, "article_text", lambda body, selector: 1 / 0)
    fetcher, _ = fetcher_for({ECT_ARTICLE: html(ECT_PAGE)})
    result = add_article_text([use_item("ect-news", ECT_ARTICLE)], SOURCES, fetcher)
    assert result.items[0].article_text is None
    assert result.failures == [{"source": "ECT news",
                                "error": f"{ECT_ARTICLE}: unexpected error (ZeroDivisionError: division by zero)"}]


def test_every_use_source_has_a_way_to_get_its_text():
    use = {s.id for s in load_sources() if s.verdict == "use"}
    assert use == set(collect.ARTICLE_BODY) | {PIN_SOURCE_ID, KN_SOURCE_ID}


def test_article_text_lives_in_memory_only_and_never_reaches_a_file(tmp_path):
    fetcher, _ = fetcher_for({ECT_ARTICLE: html(ECT_PAGE)})
    [done] = add_article_text([use_item("ect-news", ECT_ARTICLE)], SOURCES, fetcher).items
    assert SECRET in done.article_text  # present in memory, for the summariser
    assert SECRET not in repr(done)
    store_items(tmp_path, TODAY, done)
    written = storage.path("items", TODAY, tmp_path).read_text(encoding="utf-8")
    assert SECRET not in written and "article_text" not in written
