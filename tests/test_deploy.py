"""A reliable Pages deploy (issue #146).

pages.yml was one job: upload the site, then deploy it straight away. Four deploys in two days
(24–25 Nov 2026) failed after a good build: three found no upload yet ("Found 0 artifact(s)"),
one got "Deployment failed, try again later". "Re-run failed jobs" re-ran the whole job, so it
uploaded a second copy and the deploy then refused two.

Now, as in GitHub's own Pages workflow:
- two jobs: `build` (render + upload) and `deploy` (needs build), so the deploy only starts once
  the upload has finished, and re-running the deploy job alone uploads nothing new;
- the deploy is tried once more after a short wait, in the same job (same upload);
- the README says what the owner does if a deploy still fails.
"""

import re
from pathlib import Path

from test_security import job
from test_workflows import code_lines

ROOT = Path(__file__).resolve().parent.parent
PAGES = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
DEPLOY_ACTION = "uses: actions/deploy-pages@"
UPLOAD_ACTION = "uses: actions/upload-pages-artifact@"


def test_pages_has_a_build_job_and_a_deploy_job():
    jobs = re.findall(r"(?m)^  ([A-Za-z_-]+):$", PAGES[PAGES.index("\njobs:\n"):])
    assert jobs == ["build", "deploy"]


def test_the_build_job_renders_and_uploads_and_never_deploys():
    build = code_lines(job(PAGES, "build"))
    assert "python -m haven.render --out site --with-sample" in build
    assert build.count(UPLOAD_ACTION) == 1
    assert DEPLOY_ACTION not in build
    assert "ref: main" in build  # the latest main, as before


def test_the_deploy_job_waits_for_the_build_and_never_uploads():
    deploy = code_lines(job(PAGES, "deploy"))
    assert re.search(r"(?m)^    needs: build$", deploy)
    assert UPLOAD_ACTION not in deploy and "actions/checkout" not in deploy and "haven.render" not in deploy


def test_the_deploy_is_tried_once_more_after_a_wait_with_the_same_upload():
    deploy = code_lines(job(PAGES, "deploy"))
    assert deploy.count(DEPLOY_ACTION) == 2
    first = deploy[deploy.index("id: deployment"):]
    assert re.search(r"id: deployment\s*\n\s*continue-on-error: true", deploy)
    assert re.search(r"if: steps\.deployment\.outcome == 'failure'\s*\n\s*run: sleep \d+", deploy)
    assert re.search(r"id: retry\s*\n\s*if: steps\.deployment\.outcome == 'failure'", deploy)
    assert first.index("id: deployment") < first.index("id: retry")


def test_the_environment_shows_the_address_of_whichever_try_worked():
    deploy = code_lines(job(PAGES, "deploy"))
    assert "url: ${{ steps.deployment.outputs.page_url || steps.retry.outputs.page_url }}" in deploy


def test_each_job_has_only_the_permissions_it_needs():
    build, deploy = code_lines(job(PAGES, "build")), code_lines(job(PAGES, "deploy"))
    assert re.search(r"permissions:\s*\n\s*contents: read\s*\n", build)
    assert "pages: write" not in build and "id-token" not in build
    assert re.search(r"permissions:\s*\n\s*pages: write\s*\n\s*id-token: write", deploy)
    assert "contents:" not in deploy


def test_one_deploy_at_a_time_never_cancelled():
    deploy = code_lines(job(PAGES, "deploy"))
    assert re.search(r"concurrency:\s*\n\s*group: pages\s*\n\s*cancel-in-progress: false", deploy)


def test_the_readme_says_what_to_do_when_the_morning_deploy_fails():
    section = README[README.index("## If the morning deploy fails"):]
    section = section[: section.find("\n## ", 1) if "\n## " in section[1:] else len(section)]
    for words in ("Re-run failed jobs", "deploy", "Build and deploy site", "Run workflow",
                  "Daily brief", "githubstatus.com", "https://havendaily.nl/"):
        assert words in section, words
    assert "never" in section.lower()  # never re-run the whole Daily brief for a deploy problem
