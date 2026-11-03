"""Social preview tags and the site's own addresses (spec §2.3, §7.7; issue #28).

Every page has og:title, og:description, og:url (absolute), og:type, og:site_name and
twitter:card. Day pages get their own title and description (the date and the top headline);
sample day pages say they are sample data (hard rule 10). og:image, an absolute URL to a
1200 × 630 PNG, appears only once that image exists. The addresses come from config/site.toml:
no template has the site's own URLs written in.
"""

import html as html_lib
import json
import re
import shutil
from pathlib import Path

import pytest

from haven import fetch, render
from haven.config import load_site
from test_config_site import png
from test_render_real import make_brief, news

PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_BRIEFS = PROJECT_DIR / "data" / "sample" / "briefs"
BASE = "https://leonardoneirotti.github.io/haven-daily/"
DESCRIPTION = ("What affects the Port of Rotterdam today, and what it means for logistics planners. "
               "Independent, unofficial portfolio project.")
SAMPLE_NOTE = "Sample data. The ships, news and readings on this page are invented to preview the design."
TAGS = ("og:site_name", "og:type", "og:url", "og:title", "og:description", "twitter:card")


def tags(page: str) -> dict[str, list[str]]:
    """Every og:/twitter: meta tag of a page: name → its contents, in page order."""
    found: dict[str, list[str]] = {}
    for attr, name, content in re.findall(r'<meta (property|name)="((?:og|twitter):[^"]+)" content="([^"]*)">', page):
        found.setdefault(name, []).append(html_lib.unescape(content))
    return found


def tag(page: str, name: str) -> str:
    values = tags(page).get(name, [])
    assert len(values) == 1, (name, values)
    return values[0]


def render_briefs(tmp_path, *briefs):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)
    for brief in briefs:
        (briefs_dir / f"{brief['date']}.json").write_text(json.dumps(brief), encoding="utf-8")
    out = tmp_path / "site"
    render.render_site(briefs_dir, out)
    return out


@pytest.fixture(scope="module")
def sample_site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    render.render_site(SAMPLE_BRIEFS, out)
    return out


def all_pages(site: Path) -> dict[str, str]:
    paths = {"": site / "index.html", "archive.html": site / "archive.html", "about.html": site / "about.html"}
    paths.update({f"days/{p.name}": p for p in sorted((site / "days").glob("*.html"))})
    return {url_path: path.read_text(encoding="utf-8") for url_path, path in paths.items()}


# ---------- every page ----------

def test_every_page_has_each_tag_once_and_its_own_absolute_address(sample_site):
    for url_path, page in all_pages(sample_site).items():
        for name in TAGS:
            tag(page, name)
        assert tag(page, "og:url") == BASE + url_path, url_path
        assert tag(page, "og:site_name") == "Haven Daily"
        assert tag(page, "og:type") == "website"


def test_today_archive_and_how_it_works_use_the_site_description(sample_site):
    pages = all_pages(sample_site)
    assert tag(pages[""], "og:title") == "Haven Daily"
    assert tag(pages["archive.html"], "og:title") == "Archive · Haven Daily"
    assert tag(pages["about.html"], "og:title") == "How it works · Haven Daily"
    for url_path in ("", "archive.html", "about.html"):
        assert tag(pages[url_path], "og:description") == DESCRIPTION, url_path


# ---------- day pages: the date and the top headline ----------

def day_page(tmp_path, brief):
    return (render_briefs(tmp_path, brief) / "days" / f"{brief['date']}.html").read_text(encoding="utf-8")


def test_a_day_page_is_titled_with_its_date_and_described_by_its_top_headline(tmp_path):
    brief = make_brief(items=[news("medium", "Invented second headline"), news("high", "Invented top headline"),
                              news("low", "Invented third headline")])
    page = day_page(tmp_path, brief)
    assert tag(page, "og:title") == "Friday 20 November 2026 · Haven Daily"
    assert tag(page, "og:description") == "Invented top headline (and 2 more)"  # most severe first


def test_a_day_with_one_item_is_described_by_that_headline_alone(tmp_path):
    page = day_page(tmp_path, make_brief(items=[news("low", "Invented only headline")]))
    assert tag(page, "og:description") == "Invented only headline"


def test_a_quiet_day_says_so(tmp_path):
    page = day_page(tmp_path, make_brief(items=[]))
    assert tag(page, "og:description") == "Nothing significant on this day. The port status still applies."


def test_a_headline_with_quotes_and_ampersands_is_escaped_in_the_tag(tmp_path):
    page = day_page(tmp_path, make_brief(items=[news("high", 'Strike at "Delta" & Euromax')]))
    assert 'content="Strike at &#34;Delta&#34; &amp; Euromax"' in page or \
           'content="Strike at &quot;Delta&quot; &amp; Euromax"' in page
    assert tag(page, "og:description") == 'Strike at "Delta" & Euromax'


def test_sample_day_pages_say_they_are_sample_data(sample_site):
    # Hard rule 10: a shared link to a sample day must not preview invented news as real.
    for url_path, page in all_pages(sample_site).items():
        if url_path.startswith("days/"):
            assert tag(page, "og:title").endswith("· Haven Daily (sample data)"), url_path
            assert tag(page, "og:description") == SAMPLE_NOTE, url_path


# ---------- og:image only once the image exists ----------

def test_no_og_image_while_the_preview_image_does_not_exist(sample_site):
    assert not (PROJECT_DIR / "static" / load_site().social_image).exists()  # not made yet (#43)
    for url_path, page in all_pages(sample_site).items():
        assert not [name for name in tags(page) if name.startswith("og:image")], url_path
        assert tag(page, "twitter:card") == "summary", url_path


@pytest.fixture
def static_with_image(tmp_path, monkeypatch):
    """A copy of static/ holding a preview image of the given size."""
    def make(width, height):
        static = tmp_path / "static"
        shutil.copytree(PROJECT_DIR / "static", static)
        png(static / load_site().social_image, width, height)
        monkeypatch.setattr(render, "STATIC_DIR", static)
        return static
    return make


def test_once_the_image_exists_every_page_shows_it_as_an_absolute_url(tmp_path, static_with_image):
    static_with_image(1200, 630)
    site = tmp_path / "out"
    render.render_site(SAMPLE_BRIEFS, site)
    assert (site / "static" / "social-preview.png").exists()  # published with the site
    for url_path, page in all_pages(site).items():
        assert tag(page, "og:image") == BASE + "static/social-preview.png", url_path
        assert tag(page, "og:image:width") == "1200"
        assert tag(page, "og:image:height") == "630"
        assert tag(page, "og:image:alt")
        assert tag(page, "twitter:card") == "summary_large_image"


def test_an_image_of_the_wrong_size_is_left_out(tmp_path, static_with_image):
    # LinkedIn crops or rejects other sizes; the page still builds (hard rule 9), without it.
    static_with_image(800, 800)
    site = tmp_path / "out"
    render.render_site(SAMPLE_BRIEFS, site)
    for url_path, page in all_pages(site).items():
        assert "og:image" not in tags(page), url_path
        assert tag(page, "twitter:card") == "summary"


# ---------- the addresses come from config/site.toml ----------

def test_footer_and_how_it_works_link_the_configured_addresses(sample_site):
    site = load_site()
    for url_path, page in all_pages(sample_site).items():
        footer = page[page.index('<footer class="site-footer">'):]
        assert f'href="{site.linkedin_url}"' in footer and f'href="{site.repo_url}"' in footer, url_path
    maker = all_pages(sample_site)["about.html"]
    maker = maker[maker.index('<section aria-labelledby="maker">'):]
    assert f'href="{site.linkedin_url}"' in maker[:maker.index("</section>")]
    assert f'href="{site.repo_url}"' in maker[:maker.index("</section>")]


def test_no_template_has_the_sites_own_addresses_written_in():
    site = load_site()
    own = (site.base_url, site.linkedin_url, site.repo_url, "github.io", "linkedin.com", "leonardoneirotti")
    for template in sorted((PROJECT_DIR / "templates").glob("*.html")):
        text = template.read_text(encoding="utf-8")
        for address in own:
            assert address not in text, (template.name, address)


def test_the_renderer_has_no_addresses_of_its_own():
    # They used to be in SITE (#86); now config/site.toml is the one place.
    assert not {"linkedin_url", "repo_url", "base_url"} & set(render.SITE)


def test_the_user_agent_links_how_it_works_at_the_configured_base_url():
    assert fetch.USER_AGENT == f"HavenDaily/1.0 (+{load_site().base_url}about.html)"
