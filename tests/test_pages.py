"""Page collectors (HTML lists) (spec §4, §5.8, hard rules 9, 12 and 13; issue #10).

Every page here is written by us: the same tags and classes as the real pages
(checked 1 Nov 2026), with invented headlines and text (hard rule 13: no
third-party article text in the repo). The network is a fake; no test touches
the internet or really waits.
"""

from datetime import date

import pytest

from haven import pages, storage
from haven.config import Source, load_sources
from haven.feeds import Item
from haven.fetch import Fetcher, RawResponse, TransportError
from haven.pages import collect_page, rotterdam_paragraph

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


def html(body, status=200, headers=None):
    return RawResponse(status, headers or {"content-type": "text/html; charset=utf-8"}, body.encode("utf-8"))


def doc(inner):
    return f"<!DOCTYPE html><html><head><title>Invented</title></head><body><main>{inner}</main></body></html>"


def real(source_id):
    """The source as configured in config/sources.toml (so ids and URLs stay real)."""
    return next(s for s in load_sources() if s.id == source_id)


def with_verdict(src, verdict):
    return Source(id=src.id, name=src.name, verdict=verdict, urls=src.urls, access=src.access, language=src.language)


SECRET = "Invented teaser text that must never leave memory"

# --- pages with the real structure, invented content -------------------------------------

PA_URL = "https://www.portofrotterdam.com/en/news-and-press-releases"


def pa_card(title="Invented quay wall works start at Waalhaven", href="/en/news-and-press-releases/invented-quay-wall",
            dt="2026-10-31T10:15:00+01:00", nl_title="Verzonnen titel"):
    time = f'<time datetime="{dt}" class="datetime">31 / 10 / 2026</time>' if dt is not None else ""
    heading = f'<h3 class=" news-item__title">{title}</h3>' if title is not None else ""
    link_attrs = f'href="{href}"' if href is not None else ""
    return (
        '<div class="news-item glide__slide col-xs-12 views-row" role="group">'
        f'<a class="news-item__link stretched-link" {link_attrs} title="{nl_title}">'
        '<div class="news-item__image"><img src="/img.jpg" alt="Invented"></div>'
        '<div class="news-item__content"><div class="news-item__info">'
        '<div class="tag news-item__theme">Invented theme</div>'
        f'<div class="date-small news-item__date">{time}</div></div>'
        f'<div class="news-item__title-wrapper">{heading}</div></div></a></div>'
    )


def pa_page(*cards):
    return doc('<section class="glide news-slider"><div class="views-infinite-scroll-content-wrapper">'
               + "".join(cards) + "</div></section>")


CONTARGO_URL = "https://www.contargo.net/en/business/business-news"
CONTARGO_FINAL = "https://www.contargo.net/en/business/business-news/current-customer-information/"


def contargo_card(title="Invented barge waiting times at the seaports",
                  href="/en/business/business-news/detail-business/invented-waiting-times/",
                  dt="2026-10-31", teaser=("Invented: average barge waiting time 30 hours.", "Second invented line.")):
    paragraphs = "".join(f"<p>{line}</p>" for line in teaser)
    return (
        '<div class="grid grid-3-5 news-item"><div class="column"><figure class="image"><div class="img-wrapper">'
        f'<picture><a class="news" title="{title}" href="{href}"><img alt="{title}" src="/x.jpg"></a></picture>'
        '</div></figure></div><div class="column"><div class="column"><div class="text"><div>'
        '<span class="category">Business News</span>'
        f'<time class="date" itemprop="datePublished" datetime="{dt}">10/31/2026</time></div>'
        f"<h5>{title}</h5>{paragraphs}</div>"
        f'<div class="button-list"><a class="button no-background" title="{title}" href="{href}">More information</a></div>'
        "</div></div></div>"
    )


def contargo_page(*cards):
    return doc('<ul class="pagination"><li class="next"><a href="/en/business/business-news/current-customer-information/page-2/">'
               "<span>next</span></a></li></ul>" + "".join(cards))


ECT_URL = "https://www.ect.nl/en/news-feed"


def ect_card(title="Invented gate hours change at Delta", href="/en/news/news-feed/invented-gate-hours",
             posted="31 October 2026", body=f"<p>{SECRET}</p>"):
    return (
        '<div class="views-row"><div class="node node--type-nieuws node--view-mode-teaser ds-1col clearfix">'
        '<div class="field field--name-field-afbeelding"><article class="media media--type-afbeelding">'
        '<img src="/x.jpg" alt=""></article></div>'
        f'<div class="field field--name-node-post-date field--type-ds">{posted}</div>'
        f'<div class="field field--name-node-title field--type-ds"><h3>\n  {title}\n</h3></div>'
        f'<div class="clearfix text-formatted field field--name-body field--type-text-with-summary">{body}</div>'
        '<div class="node__links"><ul class="links inline"><li class="node-readmore">'
        f'<a href="{href}" rel="tag" title="{title}" hreflang="en">Read more<span class="visually-hidden"> about {title}</span></a>'
        "</li></ul></div></div></div>"
    )


def ect_page(*cards):
    return doc('<div class="view view-nieuws"><div class="view-content">' + "".join(cards) + "</div></div>")


NLT_URL = "https://nltimes.nl/tags/port-rotterdam"


def nlt_card(title="Invented dockworkers vote on new contract", href="/2026/10/31/invented-dockworkers-vote",
             dt="2026-10-31T09:40:00+01:00"):
    return (
        '<div class="news-card col-lg-4 col-sm-6 col-xs-12">'
        f'<div class="news-card__image"><a href="https://nltimes.nl{href}"><article class="media"><img src="/x.jpg" alt="Invented"></article></a></div>'
        '<div class="news-card__categories"><span><a href="/categories/business">Business</a></span></div>'
        f'<div class="news-card__title"><a href="{href}" hreflang="en">{title}</a></div>'
        f'<div class="news-card__date"><time datetime="{dt}" class="datetime">31 October 2026 - 09:40</time></div></div>'
    )


def nlt_page(*cards):
    return doc('<div class="region region-content">' + "".join(cards) + "</div>"
               '<div class="region region-sidebar-second"><p>Invented sidebar</p></div>')


KN_URL = "https://mykn.kuehne-nagel.com/news"
KN_WEEKLY = "https://mykn.kuehne-nagel.com/news/article/port-operational-updates-from-27-10-2026"
KN_OTHER = "https://mykn.kuehne-nagel.com/news/article/invented-rotterdam-india-deal"


def kn_list_card(title, slug):
    return (
        '<li data-cy-article_source="SEA_NEWS" class="article">'
        f'<a class="article__thumbnail-wrapper" href="/news/article/{slug}"><img alt="{title}" src="/t.jpg"></a>'
        '<div class="article__details-wrapper"><div><span data-cy="article_source_label" class="article__source"> · Sea news</span></div>'
        f'<h2 class="article__headline"><a data-cy="article_headline" href="/news/article/{slug}">{title}<!----></a></h2>'
        f'<p class="article__subheadline"><a href="/news/article/{slug}">Invented subheadline about Rotterdam</a></p></div></li>'
    )


def kn_featured_card(title, slug):
    return (
        f'<a href="/news/article/{slug}" class="featured-card featured-card--large"><img src="/f.jpg" alt="{title}">'
        '<div class="featured-card__overlay"><div class="meta"><span class="date">Oct 30, 2026 · Sea news</span></div>'
        f'<h2 class="headline">{title}</h2></div></a>'
    )


WEEKLY_TITLE = "Port operational updates from around the world (21 Oct - 27 Oct 2026)"


def kn_list(*cards, featured=()):
    return doc('<section class="featured-grid">' + "".join(featured) + "</section>"
               '<ul class="articles">' + "".join(cards) + "</ul>")


KN_LIST = kn_list(
    kn_list_card("Invented crane delivery in Jakarta", "invented-crane-delivery"),
    kn_list_card(WEEKLY_TITLE, "port-operational-updates-from-27-10-2026"),
    featured=[kn_featured_card("Invented Rotterdam and India sign port deal", "invented-rotterdam-india-deal")],
)

INTRO = "Invented intro: a storm hit Rotterdam APM Terminals and Le Havre."
ROTTERDAM = "The invented 7-day average waiting time is around 9.99 days. Invented yard occupancy at ECT is 11%."
NEXT_PORT = "Invented London Gateway text."


def kn_article(body=None, published="2026-10-27T16:23:33.974Z"):
    if body is None:
        body = (
            f"<p>{INTRO}</p><h2>Europe</h2><p><strong>Belgium <br>Antwerp:</strong> Invented Antwerp text. <br> <br>"
            f"<strong>Netherlands <br>Rotterdam: </strong>{ROTTERDAM}<br><strong><br>United Kingdom<br></strong> "
            f"<strong>London Gateway Port:</strong>{NEXT_PORT}</p><h2>North America</h2><p>Invented US text.</p>"
        )
    ld = (
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":"NewsArticle",'
        f'"headline":"{WEEKLY_TITLE}","datePublished":"{published}"}}</script>'
        if published is not None else ""
    )
    return (
        f"<!DOCTYPE html><html><head><title>Invented</title>{ld}</head><body>"
        f'<h1 class="article__headline">{WEEKLY_TITLE}</h1>'
        f'<div class="article__content article__content-closer"><div><div>{body}</div></div></div>'
        "</body></html>"
    )


# --- each page maps to the common item shape -------------------------------------------


def test_port_authority_cards_become_items_in_the_common_shape():
    fetcher, _ = fetcher_for({PA_URL: html(pa_page(pa_card(), pa_card(
        title="Invented throughput figures", href="/en/news-and-press-releases/invented-throughput",
        dt="2026-10-16T07:38:42+00:00")))})
    result = collect_page(real("port-authority-news"), fetcher)
    assert result.failures == []
    assert [i.record() for i in result.items] == [
        {
            "source": "port-authority-news",
            "headline": "Invented quay wall works start at Waalhaven",
            "url": "https://www.portofrotterdam.com/en/news-and-press-releases/invented-quay-wall",
            "published": "2026-10-31T10:15:00+01:00",
            "language": "en",
            "access": "full",
        },
        {
            "source": "port-authority-news",
            "headline": "Invented throughput figures",
            "url": "https://www.portofrotterdam.com/en/news-and-press-releases/invented-throughput",
            "published": "2026-10-16T09:38:42+02:00",  # UTC -> Amsterdam (summer time)
            "language": "en",
            "access": "full",
        },
    ]


def test_port_authority_headline_is_the_visible_title_not_the_dutch_title_attribute():
    fetcher, _ = fetcher_for({PA_URL: html(pa_page(pa_card(nl_title="Verzonnen Nederlandse titel")))})
    [item] = collect_page(real("port-authority-news"), fetcher).items
    assert item.headline == "Invented quay wall works start at Waalhaven"
    assert item.snippet is None  # the list has no teaser


def test_contargo_follows_the_redirect_and_keeps_a_date_without_a_time_as_a_date():
    fetcher, _ = fetcher_for({
        CONTARGO_URL: html("", status=301, headers={"location": CONTARGO_FINAL}),
        CONTARGO_FINAL: html(contargo_page(contargo_card())),
    })
    result = collect_page(real("contargo-news"), fetcher)
    assert result.failures == []
    [item] = result.items
    assert item.record() == {
        "source": "contargo-news",
        "headline": "Invented barge waiting times at the seaports",
        "url": "https://www.contargo.net/en/business/business-news/detail-business/invented-waiting-times/",
        "published": "2026-10-31",  # the page gives no time; none is made up
        "language": "en",
        "access": "full",
    }
    assert item.snippet == "Invented: average barge waiting time 30 hours. Second invented line."


def test_ect_reads_the_written_date_and_the_read_more_link():
    fetcher, _ = fetcher_for({ECT_URL: html(ect_page(ect_card(), ect_card(
        title="Invented weekly update", href="/en/news/news-feed/invented-weekly", posted="9 September 2026",
        body="<div><p><strong>Invented UPDATE</strong></p></div>")))})
    result = collect_page(real("ect-news"), fetcher)
    assert result.failures == []
    assert [(i.headline, i.url, i.published, i.access) for i in result.items] == [
        ("Invented gate hours change at Delta", "https://www.ect.nl/en/news/news-feed/invented-gate-hours", "2026-10-31", "full"),
        ("Invented weekly update", "https://www.ect.nl/en/news/news-feed/invented-weekly", "2026-09-09", "full"),
    ]
    assert result.items[0].snippet == SECRET


def test_nl_times_is_headline_only_and_no_article_page_is_fetched():
    fetcher, net = fetcher_for({NLT_URL: html(nlt_page(nlt_card(), nlt_card(
        title="Invented bridge closure towards Maasvlakte", href="/2026/09/17/invented-bridge-closure",
        dt="2026-09-17T14:05:00+02:00")))})
    result = collect_page(real("nl-times"), fetcher)
    assert result.failures == []
    assert [i.record() for i in result.items] == [
        {
            "source": "nl-times",
            "headline": "Invented dockworkers vote on new contract",
            "url": "https://nltimes.nl/2026/10/31/invented-dockworkers-vote",
            "published": "2026-10-31T09:40:00+01:00",
            "language": "en",
            "access": "headline-only",
        },
        {
            "source": "nl-times",
            "headline": "Invented bridge closure towards Maasvlakte",
            "url": "https://nltimes.nl/2026/09/17/invented-bridge-closure",
            "published": "2026-09-17T14:05:00+02:00",
            "language": "en",
            "access": "headline-only",
        },
    ]
    assert all(i.snippet is None and i.article_text is None for i in result.items)
    assert [c for c in net.calls if not c.endswith("/robots.txt")] == [NLT_URL]


def test_a_use_source_that_opts_out_of_ai_is_read_headline_only_without_its_teaser():
    robots = "User-agent: ClaudeBot\nDisallow: /\n"
    fetcher, _ = fetcher_for({
        "https://www.ect.nl/robots.txt": html(robots, headers={"content-type": "text/plain"}),
        ECT_URL: html(ect_page(ect_card())),
    })
    result = collect_page(real("ect-news"), fetcher)
    [item] = result.items
    assert item.access == "headline-only"
    assert item.snippet is None
    [note] = result.failures
    assert note["source"] == "ECT news"
    assert "headline-only" in note["error"] and not note["error"].startswith("ECT news")


# --- dates ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-10-31T10:15:00+01:00", "2026-10-31T10:15:00+01:00"),
        ("2026-10-31T09:15:00Z", "2026-10-31T10:15:00+01:00"),
        ("2026-10-27T16:23:33.974Z", "2026-10-27T17:23:33+01:00"),  # whole seconds
        ("2026-10-31T10:15:00", "2026-10-31T10:15:00+01:00"),  # no zone on a page = Amsterdam time
        ("2026-10-31", "2026-10-31"),  # a date only stays a date only
        ("31 October 2026", "2026-10-31"),
        ("1 November 2026", "2026-11-01"),
        ("31/10/2026", None),  # unreadable = no date, never a guess
        ("", None),
        ("32 October 2026", None),
    ],
)
def test_page_dates(raw, expected):
    assert pages.page_date(raw) == expected


def test_a_card_without_a_readable_date_is_still_collected():
    fetcher, _ = fetcher_for({PA_URL: html(pa_page(pa_card(dt=None)))})
    result = collect_page(real("port-authority-news"), fetcher)
    assert result.failures == []
    [item] = result.items
    assert item.published is None


# --- Kuehne+Nagel: only the Rotterdam paragraph -----------------------------------------


def kn_routes(article=None):
    return {KN_URL: html(KN_LIST), KN_WEEKLY: html(kn_article() if article is None else article)}


def test_kn_yields_only_the_weekly_update_with_only_its_rotterdam_paragraph():
    fetcher, net = fetcher_for(kn_routes())
    result = collect_page(real("kn-seanews"), fetcher)
    assert result.failures == []
    [item] = result.items
    assert item.record() == {
        "source": "kn-seanews",
        "headline": WEEKLY_TITLE,
        "url": KN_WEEKLY,
        "published": "2026-10-27T17:23:33+01:00",  # from the article's datePublished
        "language": "en",
        "access": "full",
    }
    assert item.article_text == ROTTERDAM
    assert item.snippet == ROTTERDAM
    # The other articles (one even mentions Rotterdam) are never opened.
    assert KN_OTHER not in net.calls
    assert [c for c in net.calls if not c.endswith("/robots.txt")] == [KN_URL, KN_WEEKLY]


def test_kn_paragraph_leaves_out_the_intro_the_label_and_the_next_port():
    text = rotterdam_paragraph(kn_article())
    assert text == ROTTERDAM
    for other in (INTRO, "Netherlands", "Antwerp", NEXT_PORT, "United Kingdom", "US text"):
        assert other not in text


@pytest.mark.parametrize(
    "body",
    [
        f"<p><strong>Rotterdam:</strong> {ROTTERDAM}</p><p>Invented next paragraph.</p>",  # ends with its block
        f"<p><b>Netherlands<br>Rotterdam</b><br>{ROTTERDAM}</p>",  # <b>, no colon
        f"<ul><li><strong>Rotterdam:</strong> {ROTTERDAM}</li><li><strong>Antwerp:</strong> Invented.</li></ul>",
    ],
)
def test_kn_paragraph_variants(body):
    assert rotterdam_paragraph(kn_article(body=body)) == ROTTERDAM


def test_kn_paragraph_is_capped_at_the_article_text_limit():
    long_text = "Invented word. " * 1000
    text = rotterdam_paragraph(kn_article(body=f"<p><strong>Rotterdam:</strong> {long_text}</p>"))
    assert len(text) <= pages.ARTICLE_TEXT_MAX
    item = collect_page(real("kn-seanews"), fetcher_for(kn_routes(
        kn_article(body=f"<p><strong>Rotterdam:</strong> {long_text}</p>")))[0]).items[0]
    assert len(item.snippet) <= pages.SNIPPET_MAX
    assert len(item.article_text) <= pages.ARTICLE_TEXT_MAX


def test_kn_article_without_a_rotterdam_paragraph_is_a_failure_and_no_item():
    article = kn_article(body=f"<p>{INTRO}</p><p><strong>Antwerp:</strong> Invented Antwerp text.</p>")
    fetcher, _ = fetcher_for(kn_routes(article))
    result = collect_page(real("kn-seanews"), fetcher)
    assert result.items == []
    [failure] = result.failures
    assert failure == {"source": "Kuehne+Nagel SeaNews", "error": f"{KN_WEEKLY}: {pages.NO_PARAGRAPH}"}


def test_kn_article_that_cannot_be_fetched_is_a_failure_and_no_item():
    fetcher, _ = fetcher_for({KN_URL: html(KN_LIST), KN_WEEKLY: html("gone", status=404)})
    result = collect_page(real("kn-seanews"), fetcher)
    assert result.items == []
    [failure] = result.failures
    assert failure["error"].startswith(f"{KN_WEEKLY}: ") and "404" in failure["error"]


def test_kn_without_a_weekly_update_on_the_list_is_quiet():
    """The weekly update is only on the first page for a few days: no item, but no failure either."""
    page = kn_list(kn_list_card("Invented crane delivery in Jakarta", "invented-crane-delivery"))
    fetcher, net = fetcher_for({KN_URL: html(page)})
    result = collect_page(real("kn-seanews"), fetcher)
    assert result.items == [] and result.failures == []
    assert [c for c in net.calls if not c.endswith("/robots.txt")] == [KN_URL]


def test_kn_headline_only_by_config_needs_no_code_change_and_opens_no_article():
    """If the K+N terms check (#43) says no, only the verdict in config changes."""
    fetcher, net = fetcher_for(kn_routes())
    result = collect_page(with_verdict(real("kn-seanews"), "headline-only"), fetcher)
    assert result.failures == []
    [item] = result.items
    assert (item.headline, item.url, item.access, item.published) == (WEEKLY_TITLE, KN_WEEKLY, "headline-only", None)
    assert item.snippet is None and item.article_text is None
    assert KN_WEEKLY not in net.calls


def test_kn_ai_opt_out_also_opens_no_article():
    robots = "User-agent: *\nAllow: /news\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /\n"
    routes = kn_routes()
    routes["https://mykn.kuehne-nagel.com/robots.txt"] = html(robots, headers={"content-type": "text/plain"})
    fetcher, net = fetcher_for(routes)
    result = collect_page(real("kn-seanews"), fetcher)
    [item] = result.items
    assert item.access == "headline-only" and item.article_text is None
    assert KN_WEEKLY not in net.calls
    assert len(result.failures) == 1  # the opt-out note


# --- a layout change or a broken page is a failure, never an exception -----------------


def test_a_page_whose_layout_changed_is_a_failure_and_other_sources_still_work():
    redesigned = doc('<div class="new-design"><a href="/en/x"><span>Invented</span></a></div>')
    fetcher, _ = fetcher_for({PA_URL: html(redesigned), ECT_URL: html(ect_page(ect_card()))})
    broken = collect_page(real("port-authority-news"), fetcher)
    assert broken.items == []
    assert broken.failures == [{"source": "Port of Rotterdam Authority news & press releases",
                                "error": f"{PA_URL}: {pages.NO_ITEMS}"}]
    fine = collect_page(real("ect-news"), fetcher)  # same fetcher, same run
    assert fine.failures == [] and len(fine.items) == 1


def test_kn_list_whose_layout_changed_is_a_failure():
    fetcher, _ = fetcher_for({KN_URL: html(doc("<div>Invented redesign</div>"))})
    result = collect_page(real("kn-seanews"), fetcher)
    assert result.items == []
    assert result.failures == [{"source": "Kuehne+Nagel SeaNews", "error": f"{KN_URL}: {pages.NO_ITEMS}"}]


def test_cards_without_a_headline_or_link_are_skipped_and_counted():
    fetcher, _ = fetcher_for({PA_URL: html(pa_page(pa_card(), pa_card(title=None), pa_card(href=None),
                                                   pa_card(href="mailto:press@invented.test")))})
    result = collect_page(real("port-authority-news"), fetcher)
    assert len(result.items) == 1
    assert result.failures == [{"source": "Port of Rotterdam Authority news & press releases",
                                "error": f"{PA_URL}: 3 entries without a headline or link were skipped"}]


def test_the_same_link_twice_on_a_page_is_one_item_and_fragments_are_removed():
    fetcher, _ = fetcher_for({PA_URL: html(pa_page(
        pa_card(), pa_card(href="/en/news-and-press-releases/invented-quay-wall#top")))})
    result = collect_page(real("port-authority-news"), fetcher)
    assert [i.url for i in result.items] == ["https://www.portofrotterdam.com/en/news-and-press-releases/invented-quay-wall"]


@pytest.mark.parametrize(
    "answer, problem",
    [
        (html("down", status=500), "HTTP 500"),
        (html("missing", status=404), "HTTP 404"),
        (TransportError("connection refused"), "connection refused"),
    ],
)
def test_a_page_that_cannot_be_fetched_is_a_failure(answer, problem):
    fetcher, _ = fetcher_for({PA_URL: answer})
    result = collect_page(real("port-authority-news"), fetcher)
    assert result.items == []
    [failure] = result.failures
    assert failure["error"].startswith(f"{PA_URL}: ") and problem in failure["error"]


def test_a_page_blocked_by_robots_txt_is_never_requested():
    robots = "User-agent: *\nDisallow: /tags/\n"
    fetcher, net = fetcher_for({"https://nltimes.nl/robots.txt": html(robots, headers={"content-type": "text/plain"}),
                                NLT_URL: html(nlt_page(nlt_card()))})
    result = collect_page(real("nl-times"), fetcher)
    assert result.items == []
    assert NLT_URL not in net.calls
    [failure] = result.failures
    assert "robots.txt" in failure["error"]


def test_an_unexpected_error_in_our_parser_is_a_failure_not_a_crash(monkeypatch):
    def broken(soup, base_url, with_snippet):
        raise KeyError("invented bug")

    monkeypatch.setitem(pages.PARSERS, "port-authority-news", broken)
    fetcher, _ = fetcher_for({PA_URL: html(pa_page(pa_card()))})
    result = collect_page(real("port-authority-news"), fetcher)
    assert result.items == []
    [failure] = result.failures
    assert failure["error"] == f"{PA_URL}: unexpected error (KeyError: 'invented bug')"


def test_an_html_source_without_a_parser_is_a_failure_not_a_crash():
    src = Source(id="invented-html", name="Invented HTML source", verdict="use",
                 urls=("https://invented.test/news",), access="html", language="en")
    fetcher, net = fetcher_for({})
    result = collect_page(src, fetcher)
    assert result.items == []
    assert result.failures == [{"source": "Invented HTML source", "error": pages.NO_PARSER}]
    assert net.calls == []


# --- in memory only (hard rule 13) ------------------------------------------------------


def test_teasers_and_article_text_never_reach_the_stored_record_or_repr(tmp_path):
    fetcher, _ = fetcher_for({ECT_URL: html(ect_page(ect_card()))})
    [ect] = collect_page(real("ect-news"), fetcher).items
    [kn] = collect_page(real("kn-seanews"), fetcher_for(kn_routes())[0]).items
    for item in (ect, kn):
        assert SECRET not in repr(item) and ROTTERDAM not in repr(item)
        assert set(item.record()) == {"source", "headline", "url", "published", "language", "access"}
    written_to = storage.write("items", date(2026, 11, 1), [ect.record(), kn.record()], data_dir=tmp_path)
    written = written_to.read_text(encoding="utf-8")
    assert SECRET not in written and ROTTERDAM not in written and "Invented intro" not in written


def test_item_article_text_defaults_to_none_and_stays_out_of_the_record():
    item = Item(source="x", headline="h", url="https://x.test/", published=None, language="en",
                access="full", article_text="Invented article text")
    assert "article_text" not in item.record()
    assert "Invented article text" not in repr(item)


# --- config ---------------------------------------------------------------------------


def test_every_html_source_in_config_has_a_parser():
    html_sources = {s.id for s in load_sources() if s.fetched and s.access == "html"}
    assert html_sources == set(pages.PARSERS)


@pytest.mark.parametrize("source_id", ["pin-notices", "google-news"])
def test_collect_page_refuses_rss_and_dropped_sources(source_id):
    fetcher, _ = fetcher_for({})
    with pytest.raises(ValueError):
        collect_page(real(source_id), fetcher)
