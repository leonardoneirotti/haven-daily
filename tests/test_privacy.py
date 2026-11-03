"""Privacy check, EU/GDPR (spec §2.3, §3 hard rule 14; issue #68).

A page sets no cookies, stores nothing in the browser, tracks no one and makes the
visitor's browser contact no other server: fonts, scripts, styles, images, map tiles,
iframes all come from the site itself. Links are not loads: an ordinary <a href> to a
source, OpenStreetMap, MeteoAlarm or Google Translate only contacts that site when the
visitor clicks it, so those stay.

The checker below reads every rendered page (sample briefs and a brief written by the
runner), every CSS/JS/SVG file the site ships, and the templates and static files
themselves (which also covers a template the test sites don't render). The checker is
tested on its own first, so a check that silently finds nothing would fail here.
JavaScript can't be fully checked by reading it: the test bans the network and storage
APIs and any hard-coded outside address that isn't a link, and the browser check in the
PR covers the rest.
"""

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import test_run
from haven import render

PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_BRIEFS = PROJECT_DIR / "data" / "sample" / "briefs"
TEMPLATES_DIR = PROJECT_DIR / "templates"
STATIC_DIR = PROJECT_DIR / "static"

GITHUB_PRIVACY = "https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement"
GITHUB_PAGES_DATA = ("https://docs.github.com/en/pages/getting-started-with-github-pages/"
                     "what-is-github-pages#data-collection")
PRIVACY_NOTE = (
    "Privacy: no cookies, no tracking, nothing loaded from other sites. The site is hosted on "
    "GitHub Pages, which logs visitors' IP addresses for security (GitHub Privacy Statement)."
)

# --- the checker -------------------------------------------------------------------------

# "Another server": any address with a host part (http://, https://, ws://, //host, ...).
# data: URIs and relative paths stay on the page / the site.
OUTSIDE = re.compile(r"^\s*(?:[a-z][a-z0-9+.-]*:)?//", re.I)

# Attributes that make the browser fetch something (or, for ping/action, send something).
LOAD_ATTRIBUTES = {"src", "srcset", "imagesrcset", "poster", "data", "action", "formaction",
                   "background", "ping", "manifest", "xlink:href"}
# href is a load on every element except an ordinary link (<link>, <base>, SVG <image>/<use>).
LINK_ELEMENTS = {"a", "area"}
# Embedded content from anywhere is not wanted on these pages.
EMBED_ELEMENTS = {"iframe", "frame", "embed", "object", "portal", "applet"}

JS_APIS = {
    "network request (fetch)": r"\bfetch\s*\(",
    "network request (XMLHttpRequest)": r"\bXMLHttpRequest\b",
    "network request (sendBeacon)": r"\bsendBeacon\b",
    "network request (WebSocket)": r"\bWebSocket\b",
    "network request (EventSource)": r"\bEventSource\b",
    "script loading (importScripts)": r"\bimportScripts\b",
    "script loading (import())": r"(?<![\w.])import\s*\(",
    "browser storage (localStorage)": r"\blocalStorage\b",
    "browser storage (sessionStorage)": r"\bsessionStorage\b",
    "browser storage (indexedDB)": r"\bindexedDB\b",
    "cookie (document.cookie)": r"\bdocument\s*\.\s*cookie\b",
    "cookie (cookieStore)": r"\bcookieStore\b",
    "browser storage (Cache API)": r"\bcaches\s*\.\s*open\b",
    "service worker": r"\bserviceWorker\b",
}
JS_ADDRESS = re.compile(r"""(?:https?:|wss?:)//[^\s"'<>)\\]+|(?<=["'])//[\w-]+\.[\w.-]+[^\s"'<>)\\]*""")
NAMESPACE = "http://www.w3.org/"  # XML namespace names (inline SVG): identifiers, never fetched

ANALYTICS = ["google-analytics", "googletagmanager", "gtag(", "plausible.io", "matomo", "_paq",
             "statcounter", "fbq(", "connect.facebook", "hotjar", "clarity.ms",
             "cloudflareinsights", "umami", "goatcounter", "mixpanel", "segment.com"]


def css_problems(css: str) -> list[str]:
    """Outside addresses in url(...) and @import."""
    found = re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", css, re.S)
    addresses = [address for _, address in found]
    addresses += re.findall(r"@import\s+['\"]([^'\"]+)['\"]", css)
    return [f"CSS loads {a}" for a in addresses if OUTSIDE.match(a)]


def js_problems(js: str) -> list[str]:
    """Network and storage APIs, and hard-coded outside addresses that aren't link targets."""
    problems = [f"JS uses {name}" for name, pattern in JS_APIS.items() if re.search(pattern, js)]
    for match in JS_ADDRESS.finditer(js):
        before = js[max(0, match.start() - 7):match.start()]
        is_link = re.search(r"href=\\?[\"']$", before)
        if not is_link and not match.group().startswith(NAMESPACE):
            problems.append(f"JS mentions {match.group()} outside a link")
    return problems


def page_problems(html: str) -> list[str]:
    """Everything on an HTML (or SVG) page that would contact another server, store or track."""
    soup = BeautifulSoup(html, "html.parser")
    problems = []
    for tag in soup.find_all(True):
        name = tag.name.lower()
        if name in EMBED_ELEMENTS:
            problems.append(f"<{name}> embeds content")
        for attribute, value in tag.attrs.items():
            attribute = attribute.lower()
            values = value if isinstance(value, list) else [value]
            if attribute in {"srcset", "imagesrcset"}:
                values = [candidate.split()[0] for v in values for candidate in v.split(",") if candidate.strip()]
            elif attribute == "ping":
                values = [v for joined in values for v in joined.split()]
            is_load = attribute in LOAD_ATTRIBUTES or (attribute == "href" and name not in LINK_ELEMENTS)
            if is_load:
                problems += [f"<{name} {attribute}> loads {v}" for v in values if OUTSIDE.match(v)]
            if attribute == "style":
                problems += css_problems(" ".join(values))
        if name == "meta" and str(tag.get("http-equiv", "")).lower() == "refresh":
            address = re.search(r"url\s*=\s*['\"]?([^'\";]+)", str(tag.get("content", "")), re.I)
            if address and OUTSIDE.match(address.group(1)):
                problems.append(f"<meta refresh> goes to {address.group(1)}")
        if name == "meta" and str(tag.get("http-equiv", "")).lower() == "set-cookie":
            problems.append("<meta http-equiv=set-cookie> sets a cookie")
        if name == "style":
            problems += css_problems(tag.get_text())
        if name == "script" and not tag.get("src") and tag.get("type", "text/javascript") in {
                "text/javascript", "module", "application/javascript"}:
            problems += js_problems(tag.get_text())
    return problems


def file_problems(path: Path) -> list[str]:
    if path.suffix not in {".html", ".svg", ".css", ".js"}:
        return []  # fonts, licence text: nothing a browser runs
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".html", ".svg"}:
        problems = page_problems(text)
    elif path.suffix == ".css":
        problems = css_problems(text)
    else:
        problems = js_problems(text)
    lowered = text.lower()
    problems += [f"mentions analytics/tracking ({name})" for name in ANALYTICS if name in lowered]
    return problems


# --- the checker catches what it should, and only that ------------------------------------


@pytest.mark.parametrize("snippet", [
    '<img src="https://x.example/p.gif" alt="">',
    '<img src="a.png" srcset="a.png 1x, https://x.example/b.png 2x" alt="">',
    '<script src="//cdn.example/x.js"></script>',
    '<link rel="stylesheet" href="https://x.example/s.css">',
    '<link rel="preconnect" href="https://fonts.gstatic.com">',
    '<link rel="preload" as="font" href="https://x.example/f.woff2">',
    '<base href="https://x.example/">',
    '<iframe src="local.html"></iframe>',
    '<object data="local.svg"></object>',
    '<video poster="https://x.example/p.jpg"></video>',
    '<svg><image href="https://x.example/i.png"/></svg>',
    '<svg><use xlink:href="https://x.example/s.svg#a"/></svg>',
    '<div style="background:url(https://x.example/i.png)"></div>',
    '<style>@import url("https://x.example/s.css");</style>',
    "<style>@import 'https://x.example/s.css';</style>",
    '<form action="https://x.example/f"><button>Go</button></form>',
    '<a href="https://x.example/" ping="https://t.example/p">x</a>',
    '<meta http-equiv="refresh" content="0; url=https://x.example/">',
    '<meta http-equiv="Set-Cookie" content="a=b">',
    '<script>fetch("/x")</script>',
    '<script>var r = new XMLHttpRequest();</script>',
    '<script>navigator.sendBeacon("/b")</script>',
    '<script>localStorage.setItem("a", "b")</script>',
    '<script>sessionStorage.a = 1</script>',
    '<script>indexedDB.open("a")</script>',
    '<script>document.cookie = "a=b"</script>',
    '<script>var u = "https://t.example/p.js";</script>',
    "<script>gtag('config', 'G-1');</script>",
])
def test_the_checker_finds(snippet):
    assert page_problems(snippet) or any(name in snippet.lower() for name in ANALYTICS)


@pytest.mark.parametrize("snippet", [
    '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    '<a href="https://translate.google.com/translate?u=x">Read in English</a>',
    '<link rel="stylesheet" href="static/style.css">',
    '<link rel="icon" href="../static/favicon.svg" type="image/svg+xml">',
    '<script src="static/site.js"></script>',
    '<img src="data:image/png;base64,AAAA" alt="">',
    '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
    "<script>x.innerHTML = '<a href=\"https://leafletjs.com\">Leaflet</a>';</script>",
    '<script type="application/json" id="map-data">{"url": "https://example.com/a"}</script>',
    '<div style="background:url(img/a.png)"></div>',
])
def test_the_checker_allows(snippet):
    assert page_problems(snippet) == []


def test_the_checker_reads_css_and_js_files():
    assert css_problems('@font-face { src: url("https://x.example/f.woff2") }')
    assert css_problems("@import 'https://x.example/s.css';")
    assert css_problems("a { background: url(//x.example/i.png) }")
    assert not css_problems('@font-face { src: url("fonts/a.woff2") } .x { behavior: url(#default#VML) }')
    assert js_problems("fetch('/api')")
    assert js_problems("var s = document.createElement('script'); s.src = 'https://x.example/a.js';")
    assert not js_problems("var ns = 'http://www.w3.org/2000/svg'; // see https-free comment")
    assert not js_problems("attribution('<a href=\"https://www.openstreetmap.org/copyright\">OSM</a>')")


# --- the site as built ---------------------------------------------------------------------


@pytest.fixture(scope="module", params=["sample briefs", "runner brief"])
def site(request, tmp_path_factory):
    base = tmp_path_factory.mktemp("privacy")
    if request.param == "sample briefs":
        briefs = SAMPLE_BRIEFS
    else:
        outcome, _ = test_run.go(base / "data")
        assert outcome.exit_code == 0
        briefs = base / "data" / "briefs"
    render.render_site(briefs, base / "site")
    return base / "site"


def pages(site: Path) -> list[Path]:
    return sorted(site.rglob("*.html"))


def test_every_kind_of_page_is_checked(site):
    names = {p.relative_to(site).as_posix() for p in pages(site)}
    assert {"index.html", "archive.html", "about.html"} <= names
    assert any(name.startswith("days/") for name in names)


def test_no_built_page_or_file_loads_anything_from_another_server(site):
    problems = {}
    for path in site.rglob("*"):
        if path.is_file() and (found := file_problems(path)):
            problems[path.relative_to(site).as_posix()] = found
    assert problems == {}


def test_no_template_or_static_file_loads_anything_from_another_server():
    # Also covers a template or asset the test sites don't use.
    problems = {}
    for folder in (TEMPLATES_DIR, STATIC_DIR):
        for path in folder.rglob("*"):
            if path.is_file() and (found := file_problems(path)):
                problems[path.relative_to(PROJECT_DIR).as_posix()] = found
    assert problems == {}


def social_tag_with_own_address(tag, attribute, value) -> bool:
    """A social preview tag (#28) holding this site's own address (og:url, og:image). A <meta>
    makes the browser fetch nothing: only link-preview services (LinkedIn) read it."""
    from haven.config import load_site
    kind = str(tag.get("property") or tag.get("name") or "")
    return (tag.name == "meta" and attribute == "content" and kind.startswith(("og:", "twitter:"))
            and value.startswith(load_site().base_url))


def test_outside_addresses_on_the_pages_are_only_ordinary_links(site):
    # Positive side of the same rule: the outside addresses that are on the pages
    # (sources, OpenStreetMap, MeteoAlarm, Google Translate, GitHub) are all <a href>,
    # apart from the social preview tags' own addresses.
    for path in pages(site):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for tag in soup.find_all(True):
            for attribute, value in tag.attrs.items():
                for v in (value if isinstance(value, list) else [value]):
                    if OUTSIDE.match(v) and not v.startswith(NAMESPACE):
                        if social_tag_with_own_address(tag, attribute, v):
                            continue
                        assert (tag.name, attribute) in {("a", "href")}, (path.name, tag.name, attribute, v)


def test_only_this_sites_own_address_may_sit_in_a_social_tag():
    soup = BeautifulSoup('<meta property="og:image" content="https://tracker.example/x.png">'
                         '<meta name="description" content="https://leonardoneirotti.github.io/haven-daily/">',
                         "html.parser")
    og, description = soup.find_all("meta")
    assert not social_tag_with_own_address(og, "content", og["content"])
    assert not social_tag_with_own_address(description, "content", description["content"])


# --- the privacy note ------------------------------------------------------------------------


def footer_note(html: str):
    footer = BeautifulSoup(html, "html.parser").find("footer", class_="site-footer")
    return footer.find("p", class_="privacy") if footer else None


def test_every_page_has_the_privacy_note_in_its_footer(site):
    for path in pages(site):
        note = footer_note(path.read_text(encoding="utf-8"))
        assert note is not None, f"{path.name} has no privacy note"
        assert " ".join(note.get_text().split()) == PRIVACY_NOTE, path.name
        links = {a.get_text(): a["href"] for a in note.find_all("a")}
        assert links == {"GitHub Privacy Statement": GITHUB_PRIVACY}, path.name


def test_privacy_note_comes_right_after_the_disclaimer(site):
    footer = BeautifulSoup((site / "index.html").read_text(encoding="utf-8"), "html.parser").find("footer")
    disclaimer = footer.find("p", class_="disclaimer")
    assert disclaimer.find_next_sibling("p") == footer.find("p", class_="privacy")


def test_method_page_has_a_privacy_section(site):
    soup = BeautifulSoup((site / "about.html").read_text(encoding="utf-8"), "html.parser")
    heading = soup.find("h2", id="privacy")
    assert heading is not None and heading.get_text() == "Privacy"
    section = heading.find_parent("section")
    text = " ".join(section.get_text().split())
    for words in ["no cookies", "local storage", "No analytics or tracking", "served from this site",
                  "Links are not loads", "Read in English", "Google Translate",
                  "logs the IP address of every visitor", "collects no personal data"]:
        assert words in text, words
    hrefs = {a["href"] for a in section.find_all("a")}
    assert {GITHUB_PRIVACY, GITHUB_PAGES_DATA} <= hrefs

