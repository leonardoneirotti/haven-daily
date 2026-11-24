"""The map pin check (tools/check_map_pins.py, #85) in the speed run (owner, PR #136, 24 Nov 2026).

The tool used to need Edge on Windows. It now takes the browser from HAVEN_BROWSER (as the Node
tools do), so speed.yml runs it in GitHub Actions on main ("before") and on the branch ("after"),
at both laptop sizes, and writes which pin pairs no longer fit at the opening view to the run's
summary. The comparison is a pure function, tested here.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL_PATH = ROOT / "tools" / "check_map_pins.py"
TOOL = TOOL_PATH.read_text(encoding="utf-8")
SPEED_YML = (ROOT / ".github" / "workflows" / "speed.yml").read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location("check_map_pins", TOOL_PATH)
pins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pins)


def result(name, *kinds):
    return {"name": name, "problems": [{"kind": kind} for kind in kinds]}


def test_the_tool_takes_the_browser_from_the_environment_and_stops_it_on_any_system():
    assert 'os.environ.get("HAVEN_BROWSER")' in TOOL and 'os.environ.get("HAVEN_BROWSER_ARGS"' in TOOL
    assert "taskkill" in TOOL and "os.killpg" in TOOL  # Windows, and Linux on the runner
    assert "Not run in CI" not in TOOL


def test_the_tool_checks_both_laptop_sizes():
    assert pins.SIZES["laptop"] == (1440, 900) and pins.SIZES["laptop-1280"] == (1280, 800)
    assert pins.SIZES["phone"] == (390, 844)


def test_the_comparison_names_the_pairs_that_no_longer_fit():
    before = [result("a + b"), result("a + c"), result("b + c", "hidden"), result("c + d", "overlap")]
    after = [result("a + b", "hidden"), result("a + c", "lost"), result("b + c"), result("c + d", "overlap")]
    text = pins.compare("laptop", before, after)
    assert "| hidden | 1 | 1 |" in text and "| overlap | 1 | 1 |" in text
    assert "No longer fit (2): a + b, a + c" in text   # hidden or lost after, fine before
    assert "Fit now (1): b + c" in text
    assert "c + d" not in text.split("| Problem")[0]  # the same before and after: not listed as a change


def test_the_comparison_counts_checks_not_problems():
    before = [result("a + b")]
    after = [result("a + b", "hidden", "hidden", "label-cut")]
    text = pins.compare("laptop", before, after)
    assert "| hidden | 0 | 1 |" in text and "| label-cut | 0 | 1 |" in text


def test_the_speed_run_checks_the_pins_before_and_after_at_both_laptop_sizes():
    job = SPEED_YML[SPEED_YML.index("\n  pins:"):]
    assert re.search(r"size: \[laptop, laptop-1280\]", job)
    assert 'tools/check_map_pins.py "$RUNNER_TEMP/main/tools/check_map_pins.py"' in job  # the same tool on main
    assert job.count("--only ${{ matrix.size }}") == 2
    assert "--compare" in job and "GITHUB_STEP_SUMMARY" in job
    assert "tools/check_map_pins.py" in SPEED_YML.split("paths:")[1].split("permissions")[0]
