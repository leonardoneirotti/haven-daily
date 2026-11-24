"""A dry run of the daily job (owner, 24 Nov 2026, before the launch on Monday 30 Nov).

A manual run of "Daily brief" with the input `dry_run` ticked runs the whole job split: the
read-only build (guard, the real pipeline, today's files as an artifact) and the publish job, but
the publish job commits to a throwaway branch `dry-run/<run id>` instead of main, and the site is
not deployed. A dry run may be started from any branch, and then runs that branch's code, so a
change to the pipeline can be tried before it is merged; a real run still only runs from main.

`haven.publish --dry-run-branch dry-run/<id>`: the same checks of what is staged (only new data/
files, exactly one brief), then a commit "Brief <day> (dry run, not published)" pushed to that
branch only: no rebase on main, never a push to main.
"""

import re
import subprocess

import pytest

from haven import publish
from tests.test_publish import DAY, git, origin_files, repo, write_day  # noqa: F401 (fixtures)
from tests.test_security import job
from tests.test_workflows import DAILY, code_lines

BRANCH = "dry-run/123456"


def test_a_dry_run_commits_todays_files_to_the_throwaway_branch_only(repo):  # noqa: F811
    main_before = git(repo, "rev-parse", "origin/main")
    write_day(repo)

    result = publish.publish(repo, dry_run_branch=BRANCH)

    assert result.day == DAY
    assert sorted(origin_files(repo, f"origin/{BRANCH}")) == [
        f"data/briefs/{DAY}.json", f"data/items/{DAY}.jsonl", f"data/status/{DAY}.json"]
    assert git(repo, "rev-parse", "origin/main") == main_before  # main untouched
    assert git(repo, "log", "-1", "--format=%s", f"origin/{BRANCH}") == f"Brief {DAY} (dry run, not published)"
    assert git(repo, "log", "-1", "--format=%an", f"origin/{BRANCH}") == publish.BOT_NAME


def test_a_dry_run_works_from_a_detached_checkout_of_another_commit(repo):  # noqa: F811
    """A dry run from a branch checks out that branch's commit (detached HEAD), not main."""
    git(repo, "checkout", "-q", "--detach")
    write_day(repo)
    publish.publish(repo, dry_run_branch=BRANCH)
    assert f"data/briefs/{DAY}.json" in origin_files(repo, f"origin/{BRANCH}")


def test_a_dry_run_makes_the_same_checks_of_what_is_staged(repo):  # noqa: F811
    write_day(repo)
    write_day(repo, "2026-11-04")
    with pytest.raises(publish.PublishError, match="exactly one new brief"):
        publish.publish(repo, dry_run_branch=BRANCH)
    remote = git(repo, "ls-remote", "--heads", "origin")
    assert BRANCH not in remote


@pytest.mark.parametrize("name", ["main", "dry-run/", "dry-run/../main", "feature/x", "dry-run/a b",
                                  "refs/heads/main", "dry-run/x:main"])
def test_only_a_dry_run_branch_name_is_accepted(repo, name):  # noqa: F811
    write_day(repo)
    with pytest.raises(publish.PublishError, match="dry-run"):
        publish.publish(repo, dry_run_branch=name)


def test_the_command_line_takes_the_branch(monkeypatch):
    seen = {}

    def fake_publish(dry_run_branch=None):
        seen["branch"] = dry_run_branch
        return publish.Published(day=DAY, files=("data/briefs/x.json",), attempts=1)

    monkeypatch.setattr(publish, "publish", fake_publish)
    assert publish.main(["--dry-run-branch", BRANCH]) == 0
    assert seen["branch"] == BRANCH
    assert publish.main([]) == 0 and seen["branch"] is None


# --- the workflow -------------------------------------------------------------------------------


def test_dry_run_is_a_manual_input_off_by_default():
    assert re.search(r"dry_run:\s*\n\s*description: [^\n]+\n\s*type: boolean\s*\n\s*default: false", DAILY)


def test_a_real_run_still_only_runs_from_main_and_a_dry_run_from_any_branch():
    brief = code_lines(job(DAILY, "brief"))
    assert "if: github.ref == 'refs/heads/main' || inputs.dry_run" in brief


def test_a_dry_run_checks_out_the_branch_it_was_started_from_and_a_real_run_main():
    for name in ("brief", "publish"):
        assert "ref: ${{ inputs.dry_run && github.sha || 'main' }}" in code_lines(job(DAILY, name))


def test_the_publish_job_passes_the_throwaway_branch_only_on_a_dry_run():
    publish_job = code_lines(job(DAILY, "publish"))
    assert "DRY_RUN: ${{ inputs.dry_run }}" in publish_job
    assert 'python -m haven.publish --dry-run-branch "dry-run/$RUN_ID"' in publish_job
    assert "RUN_ID: ${{ github.run_id }}" in publish_job


def test_a_dry_run_never_deploys_the_site():
    site = code_lines(job(DAILY, "site"))
    assert "if: needs.brief.outputs.built == 'true' && !inputs.dry_run" in site


def test_the_spec_describes_the_dry_run():
    from pathlib import Path

    spec = (Path(__file__).resolve().parent.parent / "docs" / "SPEC.md").read_text(encoding="utf-8")
    assert "dry run" in spec and "dry-run/<run id>" in spec
