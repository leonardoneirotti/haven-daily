"""Polite fetcher: the one HTTP layer every collector uses (spec §5.8, hard rules 4 and 12).

What it does on every request:
- sends our own user agent, `HavenDaily/1.0 (+<Method page URL>)`, so a site can see who we are;
- reads the host's robots.txt once per run (one Fetcher = one run) and never requests a path
  it disallows for us; if robots.txt can't be read because of a server error, nothing on that
  host is fetched (RFC 9309);
- waits a few seconds between requests to the same host, longer if robots.txt asks for it
  with `Crawl-delay`;
- gives every request a timeout and retries a failed one at most once;
- follows redirects itself, so every hop is checked against robots.txt too.

It also tells a collector whether a source opts out of AI use (hard rule 12): robots.txt
blocks a named AI crawler for the source's pages, or a `Content-Signal` line says
`ai-train=no` / `ai-input=no`. A `use` source is then treated as headline-only for the run,
with a note for the owner to update SOURCES.md.

robots.txt is parsed here, not with `urllib.robotparser`: the standard-library parser takes
the *first* matching rule instead of the *longest* (RFC 9309), and ignores `*` and `$`. With
`Allow: /` before `Disallow: /feed/` it would let us fetch /feed/, breaking hard rule 4.

Failures are raised as `FetchError` (one line, `"<url>: <problem>"`), so a collector catches
one type and adds `{"source": <id>, "error": str(error)}` to `build.failures`.

HTTP itself goes through the standard library (`urllib.request`), so there is no extra
dependency. The network, the clock and `sleep` are passed in, so tests never touch the
internet or really wait.
"""

from __future__ import annotations

import http.client
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlsplit

from haven.config import Source

PRODUCT_TOKEN = "HavenDaily"
METHOD_PAGE_URL = "https://leonardoneirotti.github.io/haven-daily/about.html"
USER_AGENT = f"{PRODUCT_TOKEN}/1.0 (+{METHOD_PAGE_URL})"

MIN_DELAY = 3.0  # seconds between two requests to the same host
TIMEOUT = 20.0  # seconds per request
MAX_CRAWL_DELAY = 60.0  # a longer Crawl-delay than this: we don't fetch the host at all
MAX_REDIRECTS = 5

# Crawlers whose block in robots.txt means "this site opts out of AI use" (hard rule 12).
# Only a group that names the crawler counts, not the `*` group (see ai_opt_out).
AI_AGENTS = (
    "ClaudeBot",
    "Claude-User",
    "Claude-SearchBot",
    "Claude-Web",
    "anthropic-ai",
    "GPTBot",
    "ChatGPT-User",
    "CCBot",
    "Google-Extended",
    "Applebot-Extended",
    "PerplexityBot",
    "cohere-ai",
    "Bytespider",
    "meta-externalagent",
)
# Content Signals (contentsignals.org, used by Cloudflare-managed robots.txt files).
AI_SIGNALS = ("ai-train", "ai-input")

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


# --- errors and responses --------------------------------------------------------


class TransportError(Exception):
    """The network failed (connection refused, reset, DNS…). Timeouts raise TimeoutError."""


class FetchError(Exception):
    """A page could not be fetched. `str(error)` is one line for build.failures."""

    def __init__(self, url: str, problem: str):
        self.url = url
        self.problem = problem
        super().__init__(f"{url}: {problem}")


class RobotsBlocked(FetchError):
    """robots.txt disallows the page (or couldn't be read), so no request was made."""


@dataclass(frozen=True)
class RawResponse:
    """What a transport returns: status, headers with lower-case names, body bytes."""

    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class Response:
    """A successful (2xx) page. `url` is the final address after redirects."""

    url: str
    status: int
    headers: dict[str, str]
    body: bytes

    def text(self) -> str:
        """The body decoded with the charset the server declared, else UTF-8."""
        match = re.search(r"charset=[\"']?([\w.:-]+)", self.headers.get("content-type", ""), re.I)
        if match:
            try:
                return self.body.decode(match.group(1), errors="replace")
            except LookupError:
                pass
        return self.body.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class SourceAccess:
    """How a source may be used this run. `note` is set when the owner should update SOURCES.md."""

    verdict: str  # "use" / "headline-only"
    note: str | None = None


Transport = Callable[[str, dict, float], RawResponse]


# --- robots.txt (RFC 9309) -----------------------------------------------------------


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)  # lower case
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow?, pattern)
    crawl_delay: float | None = None


@dataclass(frozen=True)
class RobotsTxt:
    """A parsed robots.txt file."""

    groups: tuple[_Group, ...]
    content_signals: dict[str, str]

    def _groups_for(self, agent: str) -> list[_Group]:
        name = agent.lower()
        own = [g for g in self.groups if name in g.agents]
        return own or [g for g in self.groups if "*" in g.agents]

    def has_group(self, agent: str) -> bool:
        """True if a group names this crawler itself (not just `*`)."""
        return any(agent.lower() in g.agents for g in self.groups)

    def allowed(self, agent: str, path: str) -> bool:
        """May `agent` fetch `path` (path plus query string)? Longest rule wins; a tie goes to Allow."""
        if path == "/robots.txt":
            return True
        best_length, best_allow = -1, True
        for group in self._groups_for(agent):
            for allow, pattern in group.rules:
                if pattern and _matches(pattern, path):
                    if len(pattern) > best_length or (len(pattern) == best_length and allow):
                        best_length, best_allow = len(pattern), allow
        return best_allow

    def crawl_delay(self, agent: str) -> float | None:
        delays = [g.crawl_delay for g in self._groups_for(agent) if g.crawl_delay is not None]
        return delays[0] if delays else None


def _matches(pattern: str, path: str) -> bool:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.match(regex + ("$" if anchored else ""), path) is not None


def parse_robots(text: str) -> RobotsTxt:
    """Parse robots.txt text. Unknown lines are ignored, as the standard says."""
    groups: list[_Group] = []
    current: _Group | None = None
    signals: dict[str, str] = {}
    last_was_agent = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or not last_was_agent:
                current = _Group()
                groups.append(current)
            current.agents.append(value.lower())
            last_was_agent = True
            continue
        last_was_agent = False
        if key == "content-signal":
            for pair in value.split(","):
                if "=" in pair:
                    name, setting = (p.strip().lower() for p in pair.split("=", 1))
                    if signals.get(name) != "no":  # a "no" anywhere in the file stays a "no"
                        signals[name] = setting
        elif current is None:
            continue  # rules before any User-agent line belong to no group
        elif key in ("allow", "disallow"):
            current.rules.append((key == "allow", value))
        elif key == "crawl-delay":
            try:
                delay = float(value)
            except ValueError:
                continue
            if delay >= 0 and current.crawl_delay is None:
                current.crawl_delay = delay
    return RobotsTxt(groups=tuple(groups), content_signals=signals)


# --- the real transport (standard library) --------------------------------------------


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Hand 3xx answers back to the Fetcher instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirects)


def urllib_transport(url: str, headers: dict, timeout: float) -> RawResponse:
    """One GET request with `urllib.request`. Error statuses are returned, not raised."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return RawResponse(response.status, _lower(response.headers), response.read())
    except urllib.error.HTTPError as error:
        with error:
            body = error.read()
        return RawResponse(error.code, _lower(error.headers), body)
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise TimeoutError(f"no answer within {timeout:g} s") from None
        raise TransportError(str(error.reason)) from None
    except TimeoutError:
        raise
    except (OSError, http.client.HTTPException) as error:
        raise TransportError(f"{type(error).__name__}: {error}") from None


def _lower(headers) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


# --- the fetcher -------------------------------------------------------------------------


@dataclass
class _HostRobots:
    rules: RobotsTxt | None  # None = robots.txt could not be read: fetch nothing
    problem: str | None = None


def _path(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


class Fetcher:
    """Fetches pages politely. Make one per run: robots.txt is cached for its lifetime only."""

    def __init__(
        self,
        transport: Transport = urllib_transport,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        user_agent: str = USER_AGENT,
        min_delay: float = MIN_DELAY,
        timeout: float = TIMEOUT,
        max_crawl_delay: float = MAX_CRAWL_DELAY,
    ):
        self.transport = transport
        self.clock = clock
        self.sleep = sleep
        self.user_agent = user_agent
        self.token = user_agent.split("/", 1)[0]
        self.min_delay = min_delay
        self.timeout = timeout
        self.max_crawl_delay = max_crawl_delay
        self._robots: dict[str, _HostRobots] = {}  # origin -> robots.txt
        self._last_request: dict[str, float] = {}  # host -> when its last request ended
        self._delay: dict[str, float] = {}  # host -> seconds to wait between requests

    # public

    def fetch(self, url: str) -> Response:
        """GET a page. Raises RobotsBlocked (no request made) or FetchError."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            self._check_allowed(current)
            raw = self._request(current)
            if raw.status in _REDIRECT_STATUSES and raw.headers.get("location"):
                current = urljoin(current, raw.headers["location"])
                continue
            if 200 <= raw.status < 300:
                return Response(url=current, status=raw.status, headers=raw.headers, body=raw.body)
            raise FetchError(current, f"HTTP {raw.status}")
        raise FetchError(url, f"more than {MAX_REDIRECTS} redirects")

    def ai_opt_out(self, url: str) -> str | None:
        """Why this page's site opts out of AI use, or None. None too if robots.txt can't be read."""
        robots = self._robots_for(url)
        if robots.rules is None:
            return None
        for signal in AI_SIGNALS:
            if robots.rules.content_signals.get(signal) == "no":
                return f"robots.txt has Content-Signal {signal}=no"
        path = _path(url)
        for agent in AI_AGENTS:
            if robots.rules.has_group(agent) and not robots.rules.allowed(agent, path):
                return f"robots.txt blocks {agent}"
        return None

    def source_access(self, source: Source) -> SourceAccess:
        """A `use` source that opts out of AI use is headline-only for this run, with a note."""
        if source.verdict != "use":
            return SourceAccess(verdict=source.verdict)
        for url in source.urls:
            reason = self.ai_opt_out(url)
            if reason:
                note = (
                    f"{source.name}: {reason}, so it is treated as headline-only for this run "
                    "(hard rule 12). Update SOURCES.md and config/sources.toml."
                )
                return SourceAccess(verdict="headline-only", note=note)
        return SourceAccess(verdict="use")

    # robots.txt

    def _robots_for(self, url: str) -> _HostRobots:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}".lower()
        if origin not in self._robots:
            self._robots[origin] = self._read_robots(origin)
        return self._robots[origin]

    def _read_robots(self, origin: str) -> _HostRobots:
        target = origin + "/robots.txt"
        try:
            for _ in range(MAX_REDIRECTS + 1):
                raw = self._request(target)
                if raw.status in _REDIRECT_STATUSES and raw.headers.get("location"):
                    target = urljoin(target, raw.headers["location"])
                    continue
                break
            else:
                return _HostRobots(None, f"more than {MAX_REDIRECTS} redirects")
        except FetchError as error:
            return _HostRobots(None, error.problem)
        if 200 <= raw.status < 300:
            rules = parse_robots(raw.body.decode("utf-8", errors="replace"))
        elif 400 <= raw.status < 500:
            rules = parse_robots("")  # no robots.txt: everything allowed (RFC 9309)
        else:
            return _HostRobots(None, f"HTTP {raw.status}")
        host = urlsplit(origin).netloc
        self._delay[host] = max(self.min_delay, rules.crawl_delay(self.token) or 0)
        return _HostRobots(rules)

    def _check_allowed(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise FetchError(url, "only http and https addresses are fetched")
        robots = self._robots_for(url)
        if robots.rules is None:
            raise RobotsBlocked(url, f"robots.txt could not be read ({robots.problem}), so nothing is fetched from {parts.netloc}")
        path = _path(url)
        if not robots.rules.allowed(self.token, path):
            raise RobotsBlocked(url, f"robots.txt disallows {path} for {self.token}; not fetched")
        delay = robots.rules.crawl_delay(self.token)
        if delay is not None and delay > self.max_crawl_delay:
            raise FetchError(
                url, f"robots.txt asks for {delay:g} s between requests, more than the {self.max_crawl_delay:g} s we wait; not fetched"
            )

    # one request: delay, timeout, at most one retry

    def _request(self, url: str) -> RawResponse:
        host = urlsplit(url).netloc.lower()
        headers = {"User-Agent": self.user_agent}
        problem = "not tried"
        for _ in range(2):
            self._wait_for(host)
            try:
                raw = self.transport(url, headers, self.timeout)
            except TimeoutError:
                problem = f"timed out after {self.timeout:g} s"
            except TransportError as error:
                problem = str(error) or "network error"
            else:
                if raw.status != 429 and raw.status < 500:
                    return raw
                problem = f"HTTP {raw.status}"
            finally:
                self._last_request[host] = self.clock()
        raise FetchError(url, f"{problem} (tried twice)")

    def _wait_for(self, host: str) -> None:
        if host not in self._last_request:
            return
        gap = self._delay.get(host, self.min_delay)
        wait = self._last_request[host] + gap - self.clock()
        if wait > 0:
            self.sleep(wait)
