"""Say what this is and who made it (issue #86; spec §7.8, design review S1, S2, S3, L2).

The owner's texts are used exactly: the one-liner under the brand on every page, and the About
text on the Today page and as "Who makes this" on "How it works". LinkedIn and the repository
are linked in the footer of every page and on "How it works". "Method" is now "How it works",
with a contents list and "Who makes this" second; the file stays about.html so links keep working.
"""

import html as html_lib
import re
from pathlib import Path

import pytest

from haven import render

PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_BRIEFS = PROJECT_DIR / "data" / "sample" / "briefs"

ONE_LINER = ("What affects the Port of Rotterdam today, and what it means for logistics planners. "
             "Updated every morning.")
ABOUT = ("Haven Daily is an independent portfolio project by Leonardo Neirotti, an International Business "
         "student at Rotterdam University of Applied Sciences. Every morning an automated pipeline reads public "
         "sources, uses AI to filter and summarise what matters for logistics planners, and publishes this brief. "
         "It is not affiliated with the Port of Rotterdam Authority or any company named here.")
# Under the About text in "Who makes this" (owner, 3 Nov 2026, PR #93: default 3).
BUILT_BY = ("Built by Leonardo Neirotti, second-year BBA student (Supply Chain Management), "
            "with Python and GitHub Actions.")
LINKEDIN = "https://www.linkedin.com/in/leonardo-neirotti"
REPO = "https://github.com/leonardoneirotti/haven-daily"


def text_of(page: str) -> str:
    """The page as a reader sees it: no tags, entities decoded, whitespace collapsed."""
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def part(page: str, pattern: str) -> str:
    match = re.search(pattern, page, re.S)
    assert match, pattern
    return match.group(0)


def links(page: str) -> set[str]:
    return set(re.findall(r'<a [^>]*href="([^"]+)"', page))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    render.render_site(SAMPLE_BRIEFS, out)
    return out


@pytest.fixture(scope="module")
def pages(site):
    """Every page a reader can open: Today, each day page, Archive, How it works."""
    found = {"index.html": site / "index.html", "archive.html": site / "archive.html",
             "about.html": site / "about.html"}
    found.update({f"days/{p.name}": p for p in sorted((site / "days").glob("*.html"))})
    assert len(found) > 4
    return {name: path.read_text(encoding="utf-8") for name, path in found.items()}


@pytest.fixture(scope="module")
def how(pages):
    return pages["about.html"]


# ---------- S1: the one-liner under the brand ----------

def test_the_one_liner_is_exact_under_the_brand_on_every_page(pages):
    for name, page in pages.items():
        header = part(page, r'<header class="topbar">.*?</header>')
        assert ONE_LINER in text_of(header), name
        # under the brand: after the brand name in the header
        assert text_of(header).index("Haven Daily") < text_of(header).index(ONE_LINER), name


# ---------- S2: LinkedIn and the repository ----------

def test_the_links_are_set_in_the_site_settings():
    assert render.SITE["linkedin_url"] == LINKEDIN
    assert render.SITE["repo_url"] == REPO


def test_the_footer_of_every_page_links_linkedin_and_the_repository(pages):
    for name, page in pages.items():
        footer = part(page, r'<footer class="site-footer">.*?</footer>')
        assert {LINKEDIN, REPO} <= links(footer), name


# ---------- S3: "Method" becomes "How it works" ----------

def test_the_nav_says_how_it_works_and_still_opens_about_html(pages):
    for name, page in pages.items():
        nav = part(page, r'<nav class="site-nav".*?</nav>')
        assert re.search(r'<a href="(\.\./)?about\.html"[^>]*>How it works</a>', nav), name
        assert "Method" not in text_of(nav), name


def test_the_page_title_is_how_it_works(how):
    assert re.search(r"<title>How it works · Haven Daily</title>", how)
    assert re.search(r'<h1 class="page-title">How it works</h1>', how)
    assert not re.search(r"\bMethod\b", text_of(how))


def test_the_footer_link_to_the_page_says_how_it_works(pages):
    for name, page in pages.items():
        footer = part(page, r'<footer class="site-footer">.*?</footer>')
        assert re.search(r'<a href="(\.\./)?about\.html">How it works</a>', footer), name
        assert "Method" not in text_of(footer), name


def section_ids(page: str) -> list[str]:
    return re.findall(r'<section aria-labelledby="([^"]+)">', page)


def test_who_makes_this_comes_second_right_after_what_this_is(how):
    assert section_ids(how)[:2] == ["what", "maker"]


def test_a_contents_list_at_the_top_links_every_section_in_order(how):
    contents = part(how, r'<nav class="contents" aria-label="Contents">.*?</nav>')
    assert how.index(contents) < how.index('<section aria-labelledby="what">')
    targets = re.findall(r'<a href="#([^"]+)">', contents)
    assert targets == section_ids(how)
    for target in targets:  # each entry reads like its section's heading
        heading = part(how, rf'<h2 id="{target}">.*?</h2>')
        entry = part(contents, rf'<a href="#{target}">.*?</a>')
        assert text_of(entry) == text_of(heading), target


# ---------- L2: the About text ----------

def test_who_makes_this_is_the_about_text_with_both_links(how):
    maker = part(how, r'<section aria-labelledby="maker">.*?</section>')
    assert ABOUT in text_of(maker)
    assert {LINKEDIN, REPO} <= links(maker)


def test_who_makes_this_adds_the_built_by_line_right_under_the_about_text(how):
    maker = text_of(part(how, r'<section aria-labelledby="maker">.*?</section>'))
    assert ABOUT + " " + BUILT_BY in maker


def about_block(page: str) -> str | None:
    match = re.search(r'<section class="wrap about" aria-labelledby="about-title">.*?</section>', page, re.S)
    return match.group(0) if match else None


def test_the_today_page_shows_the_about_text_with_both_links_below_the_brief(pages):
    today = pages["index.html"]
    block = about_block(today)
    assert block, "no About block on the Today page"
    assert ABOUT in text_of(block)
    assert {LINKEDIN, REPO} <= links(block)
    # Claude's default (#86, for the owner to confirm): right below the brief (items and port
    # status), before the ship list and "How this brief was made".
    assert today.index('id="brief"') < today.index(block) < today.index('aria-labelledby="build-title"')
    if 'aria-labelledby="ships-title"' in today:
        assert today.index(block) < today.index('aria-labelledby="ships-title"')


def test_past_day_pages_do_not_repeat_the_about_text(pages):
    # Claude's default (#86, for the owner to confirm): only the Today page; every day page still
    # has the one-liner, the footer links and "How it works" in the nav.
    for name, page in pages.items():
        if name.startswith("days/"):
            assert about_block(page) is None, name
            assert ABOUT not in text_of(page), name


def test_the_about_text_says_nothing_official_or_reviewed(pages):
    for word in ("official", "officially", "reviewed", "approved", "verified", "endorsed", "partner"):
        assert not re.search(rf"\b{word}\b", ABOUT + " " + ONE_LINER, re.I), word
