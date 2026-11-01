"""Polite fetcher (spec §5.8, hard rules 4 and 12): the one HTTP layer every collector uses.

The network and the clock are fakes: no test touches the internet, and no test
really sleeps. The only real HTTP in this file is against a tiny server on
127.0.0.1, to check the standard-library transport itself.
"""

import http.server
import threading
import time

import pytest

from haven import fetch
from haven.config import Source
from haven.fetch import FetchError, Fetcher, RawResponse, RobotsBlocked, TransportError, parse_robots

# --- fakes --------------------------------------------------------------------


class FakeClock:
    """A monotonic clock that only moves when someone sleeps or a request 'takes time'."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeTransport:
    """Answers from a script: url -> list of responses/exceptions, used in order (last one repeats).

    Every call is logged with the fake time it started, the headers and the timeout.
    Each request 'takes' `duration` seconds of fake time.
    """

    def __init__(self, clock, routes, duration=0.5):
        self.clock = clock
        self.routes = {url: list(answers) if isinstance(answers, list) else [answers] for url, answers in routes.items()}
        self.duration = duration
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append({"url": url, "at": self.clock.now, "headers": headers, "timeout": timeout})
        answers = self.routes.get(url)
        if answers is None:
            answers = [ok(b"", status=404)] if url.endswith("/robots.txt") else [TransportError("no route in test")]
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(answer, TimeoutError):
            self.clock.now += timeout
            raise answer
        self.clock.now += self.duration
        if isinstance(answer, Exception):
            raise answer
        return answer

    def urls(self):
        return [c["url"] for c in self.calls]


def ok(body=b"<html>news</html>", status=200, headers=None):
    return RawResponse(status=status, headers=headers or {"content-type": "text/html; charset=utf-8"}, body=body)


def robots(text):
    return ok(text.encode(), headers={"content-type": "text/plain"})


def make(routes, **kwargs):
    clock = FakeClock()
    transport = FakeTransport(clock, routes, duration=kwargs.pop("duration", 0.5))
    fetcher = Fetcher(transport=transport, clock=clock.monotonic, sleep=clock.sleep, **kwargs)
    return fetcher, transport, clock


def source(verdict="use", urls=("https://news.test/list",), name="Test News"):
    return Source(id="test-news", name=name, verdict=verdict, urls=tuple(urls), access="html", language="en")


ROBOTS = "https://news.test/robots.txt"
PAGE = "https://news.test/list"


# --- robots.txt parsing (RFC 9309) ----------------------------------------------


def allowed(text, path, agent="HavenDaily"):
    return parse_robots(text).allowed(agent, path)


def test_longest_rule_wins_not_the_first_one():
    # urllib.robotparser takes the first match and would allow /feed/ here.
    text = "User-agent: *\nAllow: /\nDisallow: /feed/\n"
    assert not allowed(text, "/feed/")
    assert allowed(text, "/news")


def test_specific_allow_inside_a_disallowed_site():
    text = "User-agent: *\nDisallow: /\nAllow: /news\n"
    assert allowed(text, "/news/2026/strike")
    assert not allowed(text, "/shop")


def test_tie_between_allow_and_disallow_goes_to_allow():
    assert allowed("User-agent: *\nDisallow: /news\nAllow: /news\n", "/news")


def test_star_wildcard_and_end_anchor():
    text = "User-agent: *\nDisallow: /user/*/edit\nDisallow: /*.pdf$\n"
    assert not allowed(text, "/user/42/edit")
    assert allowed(text, "/user/42")
    assert not allowed(text, "/files/report.pdf")
    assert allowed(text, "/files/report.pdf?download=1")


def test_query_string_is_part_of_the_path():
    text = "User-agent: *\nDisallow: /?rest_route=\n"
    assert not allowed(text, "/?rest_route=/wp/v2")
    assert allowed(text, "/havens/feed/")


def test_empty_disallow_allows_everything():
    assert allowed("User-agent: *\nDisallow:\n", "/anything")


def test_no_rules_or_empty_file_allows_everything():
    assert allowed("", "/x")
    assert allowed("# only a comment\n", "/x")


def test_our_own_group_replaces_the_star_group():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: HavenDaily\nAllow: /\n"
    assert allowed(text, "/news")


def test_agent_names_match_case_insensitively_and_exactly():
    text = "User-agent: havendaily\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    assert not allowed(text, "/news")
    # A longer, different name is a different crawler (urllib.robotparser matches substrings).
    text = "User-agent: HavenDailyArchiver\nDisallow: /\n"
    assert allowed(text, "/news")


def test_several_user_agent_lines_share_one_group():
    text = "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    rules = parse_robots(text)
    assert not rules.allowed("ClaudeBot", "/news")
    assert not rules.allowed("GPTBot", "/news")
    assert rules.allowed("HavenDaily", "/news")


def test_groups_for_the_same_agent_are_combined():
    text = "User-agent: *\nDisallow: /a\n\nUser-agent: *\nDisallow: /b\n"
    assert not allowed(text, "/a")
    assert not allowed(text, "/b")


def test_comments_crlf_and_odd_spacing():
    text = "User-Agent : *   # everyone\r\nDISALLOW:/private # keep out\r\n"
    assert not allowed(text, "/private/x")
    assert allowed(text, "/public")


def test_robots_txt_itself_is_always_allowed():
    assert allowed("User-agent: *\nDisallow: /\n", "/robots.txt")


def test_crawl_delay_for_our_group_or_the_star_group():
    assert parse_robots("User-agent: *\nCrawl-delay: 10\n").crawl_delay("HavenDaily") == 10
    text = "User-agent: *\nCrawl-delay: 10\n\nUser-agent: HavenDaily\nCrawl-delay: 2\n"
    assert parse_robots(text).crawl_delay("HavenDaily") == 2
    assert parse_robots("User-agent: GPTBot\nCrawl-delay: 99\n").crawl_delay("HavenDaily") is None
    assert parse_robots("User-agent: *\nCrawl-delay: soon\n").crawl_delay("HavenDaily") is None


def test_content_signal_line_is_read():
    rules = parse_robots("User-agent: *\nContent-Signal: search=yes, ai-train=no, use=reference\nAllow: /\n")
    assert rules.content_signals == {"search": "yes", "ai-train": "no", "use": "reference"}


# --- robots.txt in the fetcher -------------------------------------------------


def test_blocked_path_makes_no_request_and_fails():
    fetcher, transport, _ = make({ROBOTS: robots("User-agent: *\nDisallow: /list\n")})
    with pytest.raises(RobotsBlocked) as e:
        fetcher.fetch(PAGE)
    assert transport.urls() == [ROBOTS]  # the page itself was never requested
    assert "robots.txt" in str(e.value) and "/list" in str(e.value)


def test_blocked_is_a_fetch_error_so_collectors_catch_one_type():
    assert issubclass(RobotsBlocked, FetchError)


def test_allowed_path_is_fetched():
    fetcher, transport, _ = make({ROBOTS: robots("User-agent: *\nDisallow: /admin\n"), PAGE: ok(b"<p>hi</p>")})
    response = fetcher.fetch(PAGE)
    assert response.status == 200
    assert response.body == b"<p>hi</p>"
    assert response.url == PAGE
    assert transport.urls() == [ROBOTS, PAGE]


def test_missing_robots_txt_means_everything_is_allowed():
    fetcher, transport, _ = make({ROBOTS: ok(b"not found", status=404), PAGE: ok()})
    assert fetcher.fetch(PAGE).status == 200


def test_robots_txt_server_error_means_nothing_is_fetched():
    fetcher, transport, _ = make({ROBOTS: ok(b"", status=503)})
    with pytest.raises(RobotsBlocked) as e:
        fetcher.fetch(PAGE)
    assert PAGE not in transport.urls()
    assert "robots.txt" in str(e.value) and "503" in str(e.value)


def test_robots_txt_unreachable_means_nothing_is_fetched():
    fetcher, transport, _ = make({ROBOTS: TransportError("connection refused")})
    with pytest.raises(RobotsBlocked):
        fetcher.fetch(PAGE)
    assert PAGE not in transport.urls()


def test_robots_txt_is_read_once_per_host_per_run():
    other = "https://news.test/article/1"
    fetcher, transport, _ = make({ROBOTS: robots("User-agent: *\nAllow: /\n"), PAGE: ok(), other: ok()})
    fetcher.fetch(PAGE)
    fetcher.fetch(other)
    assert transport.urls().count(ROBOTS) == 1


def test_a_new_fetcher_reads_robots_txt_again():
    # One Fetcher per run, so a block added overnight is seen the next morning.
    routes = {ROBOTS: robots("User-agent: *\nAllow: /\n"), PAGE: ok()}
    first, t1, _ = make(routes)
    first.fetch(PAGE)
    second, t2, _ = make(routes)
    second.fetch(PAGE)
    assert t1.urls().count(ROBOTS) == 1 and t2.urls().count(ROBOTS) == 1


def test_every_request_sends_our_user_agent_and_a_timeout():
    fetcher, transport, _ = make({PAGE: ok()}, timeout=15)
    fetcher.fetch(PAGE)
    for call in transport.calls:
        assert call["headers"]["User-Agent"] == fetch.USER_AGENT
        assert call["timeout"] == 15


def test_user_agent_names_us_and_links_the_method_page():
    assert fetch.USER_AGENT.startswith("HavenDaily/1.0 (+https://")
    assert fetch.USER_AGENT.endswith("/about.html)")


# --- AI opt-out (hard rule 12) ---------------------------------------------------


def test_ai_bot_block_turns_a_use_source_headline_only_with_a_note():
    fetcher, _, _ = make({ROBOTS: robots("User-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")})
    access = fetcher.source_access(source("use", name="ECT news"))
    assert access.verdict == "headline-only"
    assert "ECT news" in access.note and "ClaudeBot" in access.note and "SOURCES.md" in access.note


@pytest.mark.parametrize("signal", ["ai-train=no", "search=yes, ai-input=no", "ai-train = no"])
def test_content_signal_opt_out_turns_a_use_source_headline_only(signal):
    fetcher, _, _ = make({ROBOTS: robots(f"User-agent: *\nContent-Signal: {signal}\nAllow: /\n")})
    access = fetcher.source_access(source("use"))
    assert access.verdict == "headline-only"
    assert "Content-Signal" in access.note


def test_content_signal_yes_is_not_an_opt_out():
    fetcher, _, _ = make({ROBOTS: robots("User-agent: *\nContent-Signal: search=yes, ai-train=yes\nAllow: /\n")})
    assert fetcher.source_access(source("use")).verdict == "use"


def test_clean_use_source_stays_use_without_a_note():
    fetcher, _, _ = make({ROBOTS: robots("User-agent: *\nDisallow: /admin\n")})
    access = fetcher.source_access(source("use"))
    assert access.verdict == "use" and access.note is None


def test_headline_only_source_with_ai_block_needs_no_note():
    # Already headline-only in SOURCES.md, so there is nothing for the owner to update.
    fetcher, _, _ = make({ROBOTS: robots("User-agent: GPTBot\nDisallow: /\n")})
    access = fetcher.source_access(source("headline-only"))
    assert access.verdict == "headline-only" and access.note is None


def test_ai_bot_blocked_only_elsewhere_on_the_site_is_not_an_opt_out():
    fetcher, _, _ = make({ROBOTS: robots("User-agent: ClaudeBot\nDisallow: /members/\n")})
    assert fetcher.source_access(source("use")).verdict == "use"


def test_ai_bots_only_caught_by_the_star_group_are_not_an_opt_out():
    # The site blocks everyone except us by name: that is a permission, not an AI opt-out.
    text = "User-agent: *\nDisallow: /\n\nUser-agent: HavenDaily\nAllow: /\n"
    fetcher, _, _ = make({ROBOTS: robots(text)})
    assert fetcher.source_access(source("use")).verdict == "use"


def test_any_listed_url_with_an_opt_out_counts():
    urls = ("https://a.test/feed", "https://b.test/feed")
    routes = {"https://a.test/robots.txt": robots(""), "https://b.test/robots.txt": robots("User-agent: anthropic-ai\nDisallow: /\n")}
    fetcher, _, _ = make(routes)
    access = fetcher.source_access(source("use", urls=urls))
    assert access.verdict == "headline-only" and "anthropic-ai" in access.note


def test_unreadable_robots_txt_gives_no_opt_out_note():
    # The fetch itself fails and is reported; "update SOURCES.md" would be the wrong advice.
    fetcher, _, _ = make({ROBOTS: ok(b"", status=500)})
    access = fetcher.source_access(source("use"))
    assert access.verdict == "use" and access.note is None


def test_ai_agent_list_covers_the_crawlers_named_in_the_spec():
    for name in ("ClaudeBot", "anthropic-ai", "Claude-Web", "Claude-User", "GPTBot", "CCBot", "Google-Extended"):
        assert name in fetch.AI_AGENTS


# --- delays between requests (fake clock) ----------------------------------------


def test_first_request_to_a_host_does_not_wait():
    fetcher, transport, clock = make({PAGE: ok()})
    fetcher.fetch(PAGE)
    assert transport.calls[0]["at"] == 1000.0


def test_requests_to_the_same_host_are_spaced_by_the_minimum_delay():
    other = "https://news.test/article/1"
    fetcher, transport, _ = make({PAGE: ok(), other: ok()}, min_delay=3, duration=0.5)
    fetcher.fetch(PAGE)
    fetcher.fetch(other)
    starts = [c["at"] for c in transport.calls]  # robots, page, article
    ends = [s + 0.5 for s in starts]
    assert starts[1] - ends[0] >= 3
    assert starts[2] - ends[1] >= 3


def test_different_hosts_do_not_wait_for_each_other():
    a, b = "https://a.test/x", "https://b.test/x"
    fetcher, transport, clock = make({a: ok(), b: ok()}, min_delay=3)
    fetcher.fetch(a)
    before = clock.now
    fetcher.fetch(b)
    assert transport.calls[2]["at"] == before  # b's robots.txt starts right away


def test_crawl_delay_longer_than_the_minimum_is_respected():
    fetcher, transport, _ = make({ROBOTS: robots("User-agent: *\nCrawl-delay: 10\n"), PAGE: ok()}, min_delay=3, duration=0.5)
    fetcher.fetch(PAGE)
    robots_end = transport.calls[0]["at"] + 0.5
    assert transport.calls[1]["at"] - robots_end >= 10


def test_crawl_delay_shorter_than_the_minimum_keeps_the_minimum():
    fetcher, transport, _ = make({ROBOTS: robots("User-agent: *\nCrawl-delay: 1\n"), PAGE: ok()}, min_delay=3, duration=0.5)
    fetcher.fetch(PAGE)
    assert transport.calls[1]["at"] - (transport.calls[0]["at"] + 0.5) >= 3


def test_crawl_delay_we_cannot_wait_for_fails_without_a_request():
    fetcher, transport, _ = make({ROBOTS: robots("User-agent: *\nCrawl-delay: 3600\n"), PAGE: ok()}, max_crawl_delay=60)
    with pytest.raises(FetchError) as e:
        fetcher.fetch(PAGE)
    assert PAGE not in transport.urls()
    assert "3600" in str(e.value)


def test_no_real_sleeping_happens():
    fetcher, _, clock = make({PAGE: ok(), PAGE + "?2": ok()}, min_delay=3)
    started = time.monotonic()
    fetcher.fetch(PAGE)
    fetcher.fetch(PAGE + "?2")
    assert time.monotonic() - started < 1
    assert clock.sleeps  # the fake clock did the waiting


# --- timeout and one retry ---------------------------------------------------------


def test_timeout_then_success_retries_once():
    fetcher, transport, _ = make({PAGE: [TimeoutError(), ok(b"second try")]})
    assert fetcher.fetch(PAGE).body == b"second try"
    assert transport.urls().count(PAGE) == 2


def test_timeout_twice_fails_after_exactly_one_retry():
    fetcher, transport, _ = make({PAGE: TimeoutError()}, timeout=20)
    with pytest.raises(FetchError) as e:
        fetcher.fetch(PAGE)
    assert transport.urls().count(PAGE) == 2
    assert "timed out" in str(e.value) and "20" in str(e.value)


def test_the_retry_waits_the_host_delay_too():
    fetcher, transport, _ = make({PAGE: [TimeoutError(), ok()]}, min_delay=3, timeout=20)
    fetcher.fetch(PAGE)
    first, second = [c for c in transport.calls if c["url"] == PAGE]
    assert second["at"] - (first["at"] + 20) >= 3


def test_network_error_is_retried_once():
    fetcher, transport, _ = make({PAGE: [TransportError("connection reset"), ok()]})
    assert fetcher.fetch(PAGE).status == 200
    assert transport.urls().count(PAGE) == 2


@pytest.mark.parametrize("status", [500, 502, 503, 429])
def test_server_errors_and_too_many_requests_are_retried_once(status):
    fetcher, transport, _ = make({PAGE: ok(b"", status=status)})
    with pytest.raises(FetchError) as e:
        fetcher.fetch(PAGE)
    assert transport.urls().count(PAGE) == 2
    assert str(status) in str(e.value)


@pytest.mark.parametrize("status", [403, 404, 410])
def test_client_errors_are_not_retried(status):
    fetcher, transport, _ = make({PAGE: ok(b"", status=status)})
    with pytest.raises(FetchError) as e:
        fetcher.fetch(PAGE)
    assert transport.urls().count(PAGE) == 1
    assert str(status) in str(e.value)


def test_error_message_is_one_line_naming_the_url():
    fetcher, _, _ = make({PAGE: TransportError("connection refused")})
    with pytest.raises(FetchError) as e:
        fetcher.fetch(PAGE)
    message = str(e.value)
    assert "\n" not in message and PAGE in message


# --- redirects ------------------------------------------------------------------


def test_redirect_on_the_same_host_is_followed():
    new = "https://news.test/list-new"
    fetcher, transport, _ = make({PAGE: ok(b"", status=301, headers={"location": "/list-new"}), new: ok(b"moved")})
    response = fetcher.fetch(PAGE)
    assert response.body == b"moved" and response.url == new


def test_redirect_to_another_host_checks_that_hosts_robots_txt():
    target = "https://other.test/list"
    routes = {
        PAGE: ok(b"", status=302, headers={"location": target}),
        "https://other.test/robots.txt": robots("User-agent: *\nDisallow: /\n"),
    }
    fetcher, transport, _ = make(routes)
    with pytest.raises(RobotsBlocked):
        fetcher.fetch(PAGE)
    assert "https://other.test/robots.txt" in transport.urls()
    assert target not in transport.urls()


def test_redirect_loop_stops():
    fetcher, transport, _ = make({PAGE: ok(b"", status=302, headers={"location": PAGE})})
    with pytest.raises(FetchError) as e:
        fetcher.fetch(PAGE)
    assert "redirect" in str(e.value)
    assert transport.urls().count(PAGE) <= 6


# --- response text ------------------------------------------------------------------


def test_text_uses_the_declared_charset():
    response = fetch.Response(url=PAGE, status=200, headers={"content-type": "text/html; charset=iso-8859-1"}, body="café".encode("latin-1"))
    assert response.text() == "café"


def test_text_falls_back_to_utf8():
    response = fetch.Response(url=PAGE, status=200, headers={}, body="Kaub ↓".encode())
    assert response.text() == "Kaub ↓"


# --- the real standard-library transport, against a local test server ---------------


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/ok":
            body = self.headers["User-Agent"].encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/missing":
            self.send_response(404)
            self.end_headers()
        elif self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif self.path == "/slow":
            time.sleep(1)
            self.send_response(200)
            self.end_headers()


@pytest.fixture
def local_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_urllib_transport_sends_headers_and_returns_the_body(local_server):
    raw = fetch.urllib_transport(local_server + "/ok", {"User-Agent": "HavenDaily/test"}, timeout=5)
    assert raw.status == 200
    assert raw.body == b"HavenDaily/test"
    assert raw.headers["content-type"].startswith("text/plain")


def test_urllib_transport_returns_error_statuses_instead_of_raising(local_server):
    assert fetch.urllib_transport(local_server + "/missing", {}, timeout=5).status == 404


def test_urllib_transport_does_not_follow_redirects_itself(local_server):
    # The Fetcher follows them, so every hop goes through robots.txt and the delay.
    raw = fetch.urllib_transport(local_server + "/moved", {}, timeout=5)
    assert raw.status == 302 and raw.headers["location"] == "/ok"


def test_urllib_transport_raises_timeout(local_server):
    with pytest.raises(TimeoutError):
        fetch.urllib_transport(local_server + "/slow", {}, timeout=0.2)


def test_urllib_transport_raises_transport_error_when_nothing_listens():
    with pytest.raises(TransportError):
        fetch.urllib_transport("http://127.0.0.1:9/", {}, timeout=5)
