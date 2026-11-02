"""The workflow files and the ruleset stay in step with the code (issue #26).

Plain-text checks (no YAML library needed): the logic itself lives in tested
Python (`haven.guard`, `haven.publish`); these checks make sure the workflows
call it and don't grow their own copy of it.
"""

import json
import re
from pathlib import Path

from haven import guard

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
DAILY = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
PAGES = (WORKFLOWS / "pages.yml").read_text(encoding="utf-8")
TESTS = (WORKFLOWS / "tests.yml").read_text(encoding="utf-8")


def code_lines(text):
    """The file without its comment lines, so explanations can mention commands freely."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_daily_crons_are_the_guards_three_triggers_in_order():
    assert tuple(re.findall(r'cron:\s*"([^"]+)"', DAILY)) == guard.SCHEDULE_CRONS


def test_daily_can_be_started_by_hand():
    assert "workflow_dispatch:" in DAILY


def test_daily_publishes_only_through_haven_publish():
    code = code_lines(DAILY)
    assert "python -m haven.publish" in code
    assert not re.search(r"\bgit\s+(add|commit|push)\b", code)


def test_daily_guards_first_and_passes_the_last_trigger_to_the_runner():
    code = code_lines(DAILY)
    assert code.index("python -m haven.guard") < code.index("python -m haven.run")
    assert "--last-trigger" in code


def test_daily_runs_only_on_main_and_checks_out_main():
    code = code_lines(DAILY)
    assert "github.ref == 'refs/heads/main'" in code
    assert "ref: main" in code


def test_the_only_secret_anywhere_is_the_claude_key_in_the_daily_runner_step():
    for text in (PAGES, TESTS):
        assert "secrets." not in code_lines(text)
    assert re.findall(r"secrets\.\w+", code_lines(DAILY)) == ["secrets.ANTHROPIC_API_KEY"]
    assert not re.search(r"echo[^\n]*secrets", DAILY)


def test_pages_renders_real_briefs_or_samples_never_samples_by_name():
    code = code_lines(PAGES)
    assert "python -m haven.render --out site" in code
    assert "sample" not in code


def test_pages_is_reused_by_the_daily_job_and_deploys_from_the_latest_main():
    assert "workflow_call:" in PAGES
    assert "uses: ./.github/workflows/pages.yml" in DAILY
    assert "ref: main" in code_lines(PAGES)


def test_one_pages_deployment_at_a_time_never_cancelled():
    code = code_lines(PAGES)
    assert re.search(r"concurrency:\s*\n\s*group: pages\s*\n\s*cancel-in-progress: false", code)


def test_the_daily_job_never_cancels_a_running_daily_job():
    assert re.search(r"concurrency:\s*\n\s*group: daily\s*\n\s*cancel-in-progress: false", code_lines(DAILY))


def test_the_ruleset_only_blocks_force_pushes_and_deletion_of_the_default_branch():
    ruleset = json.loads((ROOT / ".github" / "rulesets" / "main.json").read_text(encoding="utf-8"))
    assert ruleset["target"] == "branch"
    assert ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    assert sorted(rule["type"] for rule in ruleset["rules"]) == ["deletion", "non_fast_forward"]
    assert ruleset.get("bypass_actors", []) == []
