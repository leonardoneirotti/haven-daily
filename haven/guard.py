"""The guard: first step of the daily job, decides whether this run builds (spec §5.1.1, issue #26).

GitHub cron runs in UTC only, often starts late and sometimes drops a run, so the daily workflow
has three scheduled triggers (04:45, 05:45, 06:45 UTC) and a manual one. This decides, for one
run:

1. **Scheduled runs only:** before 06:30 in Amsterdam → stop (in winter the 04:45 UTC trigger is
   05:45 Amsterdam, too early).
2. **Every run, manual too:** `data/briefs/<today>.json` already exists → stop (the brief is the
   file that says "today is done", §5.13 point 7).
3. Otherwise → build.

"Today" is the Amsterdam date (`haven.clock`), so the summer/winter time change needs no code.
A stop is **not** an error: the run ends green, so GitHub sends no failure notification.

**The last trigger** (§5.6): the 06:45 UTC cron is the day's last scheduled run, so the runner
gets `--last-trigger` and publishes a reduced brief instead of failing if the AI is down. A manual
run counts as the last trigger only when the owner ticks the box when starting it.

`python -m haven.guard --event <schedule|workflow_dispatch> [--schedule CRON]
[--manual-last-trigger true|false] [--data-dir DIR]` prints the decision and writes `build`,
`last_trigger` and `day` to `$GITHUB_OUTPUT` for the next steps. Refused input (an unknown event
or cron) exits 1, so a typo in the workflow fails loudly instead of quietly skipping the reduced
brief.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

from haven import clock, storage

__all__ = ["EARLIEST", "LAST_TRIGGER_CRON", "SCHEDULE_CRONS", "Decision", "GuardError", "decide", "main"]

# The three scheduled triggers, in order; the workflow's cron lines must be exactly these (tested).
SCHEDULE_CRONS = ("45 4 * * *", "45 5 * * *", "45 6 * * *")
LAST_TRIGGER_CRON = SCHEDULE_CRONS[-1]
EARLIEST = time(6, 30)  # Amsterdam time; a scheduled run before it stops

SCHEDULE = "schedule"
MANUAL = "workflow_dispatch"


class GuardError(ValueError):
    """The workflow gave the guard something it doesn't know (a changed cron, another event)."""


@dataclass(frozen=True)
class Decision:
    build: bool
    last_trigger: bool  # only meaningful when build is True
    day: date  # today in Amsterdam: the brief this run would write
    reason: str


def decide(event: str, *, schedule: str | None = None, manual_last_trigger: bool = False,
           data_dir: Path = storage.DATA_DIR, utc_now: clock.Clock = clock.system_clock) -> Decision:
    """Whether this run builds today's brief, and whether it is the day's last trigger."""
    if event == SCHEDULE:
        if schedule not in SCHEDULE_CRONS:
            raise GuardError(f"scheduled run with cron {schedule!r}, expected one of {', '.join(SCHEDULE_CRONS)} "
                             "(haven/guard.py and .github/workflows/daily.yml must list the same triggers)")
        last_trigger = schedule == LAST_TRIGGER_CRON
    elif event == MANUAL:
        last_trigger = bool(manual_last_trigger)
    else:
        raise GuardError(f"unknown event {event!r}: the daily job runs on {SCHEDULE} or {MANUAL} only")

    now = clock.now(utc_now)
    today = now.date()
    if event == SCHEDULE and now.time() < EARLIEST:
        return Decision(False, False, today,
                        f"it is {now:%H:%M} in Amsterdam, before {EARLIEST:%H:%M}: too early for a scheduled run")
    brief = storage.path("briefs", today, data_dir)
    if brief.exists():
        return Decision(False, False, today, f"the brief for {today.isoformat()} is already there")
    which = "the last trigger" if last_trigger else "not the last trigger"
    return Decision(True, last_trigger, today,
                    f"no brief for {today.isoformat()} yet, {now:%H:%M} in Amsterdam ({which})")


def _flag(text: str) -> bool:
    """A workflow input as text: 'true' (any case) is true, anything else (incl. empty) is false."""
    return text.strip().lower() == "true"


def main(argv=None, utc_now: clock.Clock = clock.system_clock) -> int:
    parser = argparse.ArgumentParser(prog="python -m haven.guard", description=__doc__.splitlines()[0])
    parser.add_argument("--event", required=True, help="github.event_name: schedule or workflow_dispatch")
    parser.add_argument("--schedule", default="", help="github.event.schedule: the cron of a scheduled run")
    parser.add_argument("--manual-last-trigger", default="false",
                        help="the manual run's tick box: 'true' = reduced brief if the AI is down")
    parser.add_argument("--data-dir", type=Path, default=storage.DATA_DIR)
    args = parser.parse_args(argv)
    try:
        decision = decide(args.event, schedule=args.schedule or None,
                          manual_last_trigger=_flag(args.manual_last_trigger), data_dir=args.data_dir,
                          utc_now=utc_now)
    except GuardError as error:
        print(f"Guard: {error}", file=sys.stderr)
        return 1
    print(f"{'Build' if decision.build else 'Stop'}: {decision.reason}")
    outputs = os.environ.get("GITHUB_OUTPUT")
    if outputs:
        with open(outputs, "a", encoding="utf-8", newline="\n") as file:
            file.write(f"build={str(decision.build).lower()}\n")
            file.write(f"last_trigger={str(decision.last_trigger).lower()}\n")
            file.write(f"day={decision.day.isoformat()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
