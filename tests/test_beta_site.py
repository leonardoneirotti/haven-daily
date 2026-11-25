"""Beta: the sample site at /sample/, and one setting for the site's address (owner, 25 Nov 2026).

1. The sample-data site is published under /sample/ on the same GitHub Pages site, built by the
   same command as the real one (`python -m haven.render --out site --with-sample`). Every page
   carries the "Sample data" strip (hard rule 10) and `noindex`; the real archive doesn't list it,
   and the real site links it only once, with one short line in How it works.
2. The site's address is one setting, `base_url` in config/site.toml: it gives the canonical
   links, the link previews (og:url, og:image), the sitemap, robots.txt, and the README must match
   it. Moving to havendaily.nl is a change of that one line (steps in spec §11).
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

from haven import render
from haven.config import load_site

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "sample" / "briefs"
SAMPLE_DATES = {p.stem for p in SAMPLES.glob("*.json")}
BASE = load_site().base_url
NOINDEX = '<meta name="robots" content="noindex, nofollow">'


def real_brief(day):
    return {"date": day, "sample": False, "built_at": f"{day}T06:52:00+01:00", "corrections": [], "status": [],
            "items": [], "build": {"sources_checked": 9, "items_collected": 3, "items_kept": 0, "failures": []},
            "ships": None}


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    """What pages.yml publishes: the real site, with the samples at sample/."""
    tmp = tmp_path_factory.mktemp("published")
    briefs = tmp / "briefs"
    briefs.mkdir()
    for day in ("2026-11-24", "2026-11-25"):
        (briefs / f"{day}.json").write_text(json.dumps(real_brief(day)), encoding="utf-8")
    render.render_published(briefs, tmp / "site")
    return tmp / "site"


def html_pages(folder: Path, skip_sample=False):
    pages = sorted(folder.rglob("*.html"))
    return [p for p in pages if not (skip_sample and "sample" in p.relative_to(folder).parts)]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- 1. the sample site at /sample/ -----------------------------------------------------------------


def test_the_sample_site_is_built_under_sample(published):
    for page in ("index.html", "archive.html", "about.html", *(f"days/{d}.html" for d in SAMPLE_DATES)):
        assert (published / "sample" / page).is_file(), page
    assert (published / "sample" / "static" / "style.css").is_file()


def test_every_sample_page_says_sample_data_and_is_noindex(published):
    pages = html_pages(published / "sample")
    assert len(pages) >= 7
    for page in pages:
        html = read(page)
        assert NOINDEX in html, page.name
        if page.name != "404.html":
            assert "Sample data." in html, page.name


def test_no_real_page_is_noindex(published):
    for page in html_pages(published, skip_sample=True):
        assert NOINDEX not in read(page), page.name


def test_the_real_archive_lists_only_real_days(published):
    archive = read(published / "archive.html")
    assert "2026-11-25" in archive and "2026-11-24" in archive
    for day in SAMPLE_DATES:
        assert day not in archive
    assert not (published / "days" / "2026-10-29.html").exists()


def test_the_real_site_links_the_sample_site_only_once_in_how_it_works(published):
    for page in html_pages(published, skip_sample=True):
        links = re.findall(r'<a [^>]*href="([^"]*sample/[^"]*)"', read(page))
        if page.name == "about.html" and page.parent == published:
            assert links == ["sample/index.html"]
        else:
            assert links == [], page.name


def test_the_sample_line_is_short(published):
    about = read(published / "about.html")
    line = re.search(r'<p class="sample-site">(.*?)</p>', about, re.S).group(1)
    words = re.sub(r"<[^>]+>", " ", line).split()
    assert len(words) <= 12, words


def test_the_sample_site_does_not_link_itself_as_a_sample(published):
    assert 'class="sample-site"' not in read(published / "sample" / "about.html")


def test_sample_pages_have_their_own_addresses(published):
    index = read(published / "sample" / "index.html")
    day = read(published / "sample" / "days" / "2026-10-29.html")
    assert f'<meta property="og:url" content="{BASE}sample/">' in index
    assert f'<link rel="canonical" href="{BASE}sample/days/2026-10-29.html">' in day


def test_without_real_briefs_there_is_no_second_copy_of_the_samples(tmp_path):
    render.render_published(SAMPLES, tmp_path / "site")
    assert not (tmp_path / "site" / "sample").exists()
    assert 'class="sample-site"' not in read(tmp_path / "site" / "about.html")


def test_the_pages_workflow_publishes_both():
    workflow = read(ROOT / ".github" / "workflows" / "pages.yml")
    assert "python -m haven.render --out site --with-sample" in workflow


def test_a_plain_render_builds_only_the_site(tmp_path):
    render.render_site(SAMPLES, tmp_path / "site")
    assert not (tmp_path / "site" / "sample").exists()


# --- 2. the site's address: one setting ------------------------------------------------------------------


def test_every_real_page_but_the_404_has_its_canonical_address(published):
    expected = {"index.html": BASE, "archive.html": f"{BASE}archive.html", "about.html": f"{BASE}about.html",
                "days/2026-11-25.html": f"{BASE}days/2026-11-25.html"}
    for page, address in expected.items():
        assert f'<link rel="canonical" href="{address}">' in read(published / page), page
    assert 'rel="canonical"' not in read(published / "404.html")


def test_the_sitemap_lists_the_real_pages_from_the_setting(published):
    sitemap = read(published / "sitemap.xml")
    assert sitemap.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    locations = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    assert locations == [BASE, f"{BASE}archive.html", f"{BASE}about.html",
                         f"{BASE}days/2026-11-24.html", f"{BASE}days/2026-11-25.html"]
    assert not (published / "sample" / "sitemap.xml").exists()


def test_robots_txt_points_at_the_sitemap(published):
    assert read(published / "robots.txt") == f"User-agent: *\nAllow: /\nSitemap: {BASE}sitemap.xml\n"


def test_the_social_image_and_previews_use_the_setting(published):
    index = read(published / "index.html")
    assert f'<meta property="og:url" content="{BASE}">' in index
    assert f'<meta property="og:image" content="{BASE}static/social-preview.png">' in index


def test_the_address_is_written_nowhere_else_in_the_code():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    host = re.sub(r"^https://", "", BASE).split("/")[0]
    found = [path for path in tracked
             if not path.startswith(("tests/", "docs/", "data/", "design/", "graphify-out/"))
             and path not in ("config/site.toml", "README.md", "CLAUDE.md", "SOURCES.md")
             and Path(ROOT / path).suffix in {".py", ".html", ".js", ".css", ".toml", ".yml", ".mjs"}
             and host in (ROOT / path).read_text(encoding="utf-8", errors="ignore")]
    assert found == []


def test_the_readme_links_the_site_and_the_sample_site_at_the_setting():
    readme = read(ROOT / "README.md")
    assert f"Live site: {BASE}" in readme
    assert f"Sample site (invented data): {BASE}sample/" in readme


def test_the_spec_says_how_to_move_to_the_domain():
    spec = read(ROOT / "docs" / "SPEC.md")
    steps = spec[spec.index("**Moving to havendaily.nl**"):]
    for needed in ("185.199.108.153", "185.199.111.153", "2606:50c0:8000::153", "_github-pages-challenge",
                   "Enforce HTTPS", 'base_url = "https://havendaily.nl/"', "www"):
        assert needed in steps, needed


def test_the_site_lives_at_the_root_of_havendaily_nl(tmp_path):
    """Owner, 25 Nov 2026: the domain is connected (GitHub Pages custom domain, HTTPS enforced);
    github.io now redirects here. At the root, the 404 page's links start with "/"."""
    assert BASE == "https://havendaily.nl/"
    render.render_site(SAMPLES, tmp_path / "site")
    not_found = read(tmp_path / "site" / "404.html")
    assert 'href="/index.html"' in not_found and "/haven-daily/" not in not_found
