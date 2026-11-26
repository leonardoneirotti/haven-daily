"""Security hardening (issue #125; the audit of 24 Nov 2026, fixes approved by the owner).

1. The daily job's write token is only where it's needed: a read-only build job runs the outside
   code and holds the Claude key; a small publish job with write access commits only today's files
   and installs nothing.
2. Python packages are locked to exact versions with hashes, and installed with --require-hashes.
3. Every action is pinned to a full commit SHA (GitHub's own actions only), kept current by
   Dependabot.
4. Outside links are http(s) only, checked again when the page is built; a Content-Security-Policy
   makes the browser enforce hard rule 14.
5. Pillow 13 (12.3.0 had 62 advisories).
7. No referrer is sent to other sites.

Plain-text checks of the workflow files (no YAML library), like tests/test_workflows.py.
"""

import re
from pathlib import Path

import pytest

from haven import render
from tests.test_render_real import kaub, link, make_brief, news, render_day, strike, text_of, weather
from tests.test_workflows import code_lines

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
DAILY = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")


def job(text: str, name: str) -> str:
    """One job's lines from a workflow: from `  <name>:` to the next job (two-space indent)."""
    body = text[text.index("\njobs:\n"):]
    start = body.index(f"\n  {name}:\n")
    rest = body[start + 1:]
    nxt = re.search(r"\n  [A-Za-z_-]+:\n", rest[1:])
    return rest if nxt is None else rest[: nxt.start() + 1]


# --- 1. the daily job: the write token only where it's needed ----------------------------------


def test_the_daily_workflow_has_a_build_a_publish_and_a_site_job():
    for name in ("brief", "publish", "site"):
        assert f"\n  {name}:\n" in DAILY


def test_the_build_job_can_only_read_the_code():
    brief = code_lines(job(DAILY, "brief"))
    assert re.search(r"permissions:\s*\n\s*contents: read\s*\n", brief)
    assert "write" not in brief


def test_the_build_job_keeps_no_git_credentials():
    brief = code_lines(job(DAILY, "brief"))
    assert "persist-credentials: false" in brief


def test_the_build_job_holds_the_key_and_passes_only_todays_files_on():
    brief = code_lines(job(DAILY, "brief"))
    assert "secrets.ANTHROPIC_API_KEY" in brief and "python -m haven.run" in brief
    assert "actions/upload-artifact@" in brief
    assert "data/*/${{ steps.guard.outputs.day }}.*" in brief
    assert "if-no-files-found: error" in brief


def test_the_publish_job_writes_and_installs_nothing():
    publish = code_lines(job(DAILY, "publish"))
    assert re.search(r"permissions:\s*\n\s*contents: write\s*\n", publish)
    assert "needs: brief" in publish and "needs.brief.outputs.built == 'true'" in publish
    assert "actions/download-artifact@" in publish and "path: data" in publish
    assert "python -m haven.publish" in publish
    assert "pip install" not in publish and "secrets." not in publish


def test_only_the_publish_job_runs_haven_publish_and_only_the_build_job_runs_the_pipeline():
    assert "haven.publish" not in code_lines(job(DAILY, "brief"))
    assert "haven.run" not in code_lines(job(DAILY, "publish"))


def test_the_site_is_deployed_after_the_publish_job():
    site = code_lines(job(DAILY, "site"))
    assert "needs: [brief, publish]" in site
    assert "uses: ./.github/workflows/pages.yml" in site


def test_publish_reads_only_the_standard_library():
    """The publish job installs no packages, so haven.publish must not need any."""
    allowed = {"__future__", "argparse", "re", "subprocess", "sys", "dataclasses", "pathlib", "typing"}
    source = (ROOT / "haven" / "publish.py").read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:from|import)\s+([\w.]+)", source, re.MULTILINE))
    assert {name.split(".")[0] for name in imported} <= allowed


# --- 2. and 5. locked packages ------------------------------------------------------------------

LOCKS = ("requirements.txt", "requirements-dev.txt")


def requirements(name: str) -> dict[str, str]:
    """{package: version} of a lock file; every entry must be name==version with hashes."""
    text = (ROOT / name).read_text(encoding="utf-8")
    entries = re.split(r"\n(?=[A-Za-z0-9])", "\n" + text)
    found = {}
    for entry in entries:
        entry = entry.strip()
        if not entry or entry.startswith("#"):
            continue
        first = entry.splitlines()[0]
        match = re.match(r"([A-Za-z0-9_.-]+)==([^\s;\\]+)", first)
        assert match, f"{name}: not pinned to one version: {first}"
        assert "--hash=sha256:" in entry, f"{name}: no hash for {match.group(1)}"
        found[match.group(1).lower()] = match.group(2)
    return found


@pytest.mark.parametrize("name", LOCKS)
def test_every_package_is_pinned_with_a_hash(name):
    assert requirements(name)


def test_the_lock_files_come_from_the_human_readable_lists():
    for name in ("requirements.in", "requirements-dev.in"):
        assert (ROOT / name).is_file()
    assert "uv pip compile" in (ROOT / "requirements.txt").read_text(encoding="utf-8")


def test_the_daily_build_needs_only_its_own_packages():
    daily = requirements("requirements.txt")
    assert {"anthropic", "jinja2", "beautifulsoup4", "tzdata"} <= set(daily)
    assert "pytest" not in daily and "pillow" not in daily


def test_the_test_lock_has_the_same_versions_as_the_daily_lock():
    daily, dev = requirements("requirements.txt"), requirements("requirements-dev.txt")
    assert {name: dev.get(name) for name in daily} == daily


def test_pillow_is_13_or_newer():
    assert int(requirements("requirements-dev.txt")["pillow"].split(".")[0]) >= 13


def test_every_workflow_installs_with_require_hashes():
    for path in WORKFLOWS.glob("*.yml"):
        for line in code_lines(path.read_text(encoding="utf-8")).splitlines():
            if "pip install" in line:
                assert "--require-hashes" in line, f"{path.name}: {line.strip()}"


# --- 3. actions pinned to commits ---------------------------------------------------------------


def uses_lines():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"\s*(-\s+)?uses:", line):
                yield path.name, line.strip()


def test_every_action_is_githubs_own_and_pinned_to_a_full_commit_with_its_version():
    remote = [(name, line) for name, line in uses_lines() if "./" not in line]
    assert remote
    for name, line in remote:
        assert re.search(r"uses: actions/[\w-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line), f"{name}: {line}"


def test_dependabot_keeps_the_actions_current():
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert 'package-ecosystem: "github-actions"' in config


# --- 4. links are http(s) only, checked again when the page is built ----------------------------

BAD_URLS = ["javascript:alert(1)", "JavaScript:alert(1)", " javascript:alert(1)", "data:text/html,hi",
            "vbscript:x", "//evil.test/x", "ftp://evil.test/x", "", None]


@pytest.mark.parametrize("url", ["https://news.test/a", "http://news.test/a", "HTTPS://News.test/a"])
def test_an_http_link_is_kept(url):
    assert render.outside_url(url) == url


@pytest.mark.parametrize("url", BAD_URLS)
def test_any_other_link_is_refused(url):
    assert render.outside_url(url) is None


def test_an_item_with_a_bad_link_shows_its_headline_without_a_link(tmp_path):
    item = news("medium", "Invented Dutch headline", url="javascript:alert(1)", language="nl",
                headline_en="Invented headline")  # a Dutch item is shown with its English title (#153)
    html = render_day(tmp_path, make_brief(items=[item]))
    assert "javascript:" not in html
    assert "Invented headline" in text_of(html)
    assert "Read original" not in text_of(html) and "Read in English" not in text_of(html)


def test_a_status_source_with_a_bad_link_is_shown_as_text(tmp_path):
    brief = make_brief(status=[weather(source_url="javascript:alert(2)"),
                               kaub(120, level="amber") | {"source_url": "javascript:alert(2)"}])
    html = render_day(tmp_path, brief)
    assert "javascript:" not in html
    assert "KNMI via MeteoAlarm" in text_of(html) and "WSV via PEGELONLINE" in text_of(html)


def test_a_strike_item_with_a_bad_link_is_shown_as_text(tmp_path):
    bad = link() | {"url": "javascript:alert(3)"}
    brief = make_brief(status=[strike("Strike announced for 5 Nov", "amber", links=[bad])])
    html = render_day(tmp_path, brief)
    assert "javascript:" not in html and "Invented strike headline 1" in text_of(html)


# --- 4. and 7. the Content-Security-Policy and the referrer policy -----------------------------

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'")


def built_pages(tmp_path):
    out = tmp_path / "site"
    render.render_site(briefs_dir=ROOT / "data" / "sample" / "briefs", out_dir=out)
    return sorted(out.rglob("*.html"))


def test_every_page_has_the_csp_and_no_referrer_right_after_the_charset(tmp_path):
    pages = built_pages(tmp_path)
    assert len(pages) >= 4
    for page in pages:
        head = page.read_text(encoding="utf-8").split("</head>")[0]
        metas = re.findall(r"<meta [^>]+>", head)
        assert metas[0] == '<meta charset="utf-8">', page.name
        assert metas[1] == f'<meta http-equiv="Content-Security-Policy" content="{CSP}">', page.name
        assert metas[2] == '<meta name="referrer" content="no-referrer">', page.name


def test_the_csp_allows_no_inline_or_evaluated_script():
    script = CSP.split("script-src ")[1].split(";")[0]
    assert script == "'self'"
    assert "unsafe-eval" not in CSP


def test_no_page_has_an_inline_script_or_event_handler_the_csp_would_block(tmp_path):
    for page in built_pages(tmp_path):
        html = page.read_text(encoding="utf-8")
        for tag in re.findall(r"<script\b[^>]*>", html):
            assert "src=" in tag or 'type="application/json"' in tag, (page.name, tag)
        assert not re.search(r"\son[a-z]+=", html), page.name
        assert "javascript:" not in html, page.name
