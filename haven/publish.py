"""Commit the day's data straight to main (spec §5.1 "Writing to main", issue #26).

`python -m haven.publish` runs in the daily job right after `python -m haven.run` wrote today's
three files. It:

1. checks the checkout is on `main` (a manual run started on another branch must never push that
   branch's code to `main`);
2. stages **only `data/`** (`git add --all -- data`), so the job can never commit code;
3. checks what is staged: **only new files under `data/`** (the runner writes each day once and
   never edits an earlier one, §6.1) and **exactly one new brief**, whose date names the commit.
   Anything else, even something staged by an earlier step, stops it before committing;
4. commits as `github-actions[bot]`, message `Brief YYYY-MM-DD (automatic)`;
5. `git pull --rebase --autostash origin main` (the owner may have pushed a correction at the
   same moment; `--autostash` so a stray change outside `data/` can't block it), then
   `git push origin HEAD:main`; if either fails, once more. A second failure fails the job:
   the brief is then not on `main`, so the next trigger builds the day again.

Git's own messages go to the job log only; nothing here reaches the public page.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

__all__ = ["BOT_EMAIL", "BOT_NAME", "PublishError", "Published", "main", "publish"]

PROJECT_DIR = Path(__file__).resolve().parent.parent
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"  # GitHub's own address for the bot
BRANCH = "main"
ATTEMPTS = 2  # the push, plus one retry
# Who the commit is from. Also given to the rebase, which rewrites our commit and so needs a
# committer too (the job's checkout has no git user set up).
AS_BOT = ("-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}")

Git = Callable[[list[str], Path], subprocess.CompletedProcess]


class PublishError(RuntimeError):
    """Nothing (more) was pushed; the message says why."""


@dataclass(frozen=True)
class Published:
    day: str
    files: tuple[str, ...]
    attempts: int


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def _git(git: Git, repo: Path, *args: str) -> str:
    done = git(list(args), repo)
    if done.returncode != 0:
        raise PublishError(f"git {args[0]} failed: {_last_line(done.stderr)}")
    return done.stdout


def _last_line(text: str) -> str:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return lines[-1].strip() if lines else "no message"


def publish(repo: Path = PROJECT_DIR, git: Git = run_git) -> Published:
    """Commit today's new data files as the bot and push them to main. Raises PublishError."""
    repo = Path(repo)
    branch = _git(git, repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != BRANCH:
        raise PublishError(f"the checkout is on {branch!r}, not {BRANCH!r}: the brief is only ever pushed from main")

    if not (repo / "data").is_dir():
        raise PublishError("nothing new in data/ to commit (no data/ folder)")
    _git(git, repo, "add", "--all", "--", "data")
    try:
        day, files = _check_staged(_git(git, repo, "diff", "--cached", "--name-status", "--no-renames"))
    except PublishError:
        git(["reset", "-q", "--", "data"], repo)  # unstage again; the files stay on disk for the log
        raise

    _git(git, repo, *AS_BOT, "commit", "-q", "-m", f"Brief {day} (automatic)")

    problem = ""
    for attempt in range(1, ATTEMPTS + 1):
        pulled = git([*AS_BOT, "pull", "--rebase", "--autostash", "origin", BRANCH], repo)
        if pulled.returncode != 0:
            git(["rebase", "--abort"], repo)
            problem = f"git pull --rebase failed: {_last_line(pulled.stderr)}"
            continue
        pushed = git(["push", "origin", f"HEAD:{BRANCH}"], repo)
        if pushed.returncode == 0:
            return Published(day=day, files=files, attempts=attempt)
        problem = f"git push failed: {_last_line(pushed.stderr)}"
    raise PublishError(f"tried twice, the brief is not on {BRANCH}: {problem}")


def _check_staged(name_status: str) -> tuple[str, tuple[str, ...]]:
    """(the brief's date, the staged paths) if only new data/ files with one new brief are staged."""
    staged = [line.split("\t", 1) for line in name_status.splitlines() if line.strip()]
    if not staged:
        raise PublishError("nothing new in data/ to commit")
    outside = [path for _, path in staged if PurePosixPath(path).parts[:1] != ("data",)]
    if outside:
        raise PublishError(f"staged files outside data/, nothing committed: {', '.join(outside)}")
    changed = [f"{status} {path}" for status, path in staged if status != "A"]
    if changed:
        raise PublishError("the morning job only adds new files, but these were changed or removed, "
                           f"nothing committed: {', '.join(changed)}")
    briefs = sorted(path for _, path in staged
                    if PurePosixPath(path).parent == PurePosixPath("data/briefs") and path.endswith(".json"))
    if len(briefs) != 1:
        found = ", ".join(PurePosixPath(path).stem for path in briefs) or "none"
        raise PublishError(f"expected exactly one new brief in data/briefs/, found {found}; nothing committed")
    return PurePosixPath(briefs[0]).stem, tuple(path for _, path in staged)


def main() -> int:
    try:
        result = publish()
    except PublishError as error:
        print(f"Publish: {error}", file=sys.stderr)
        return 1
    tries = "" if result.attempts == 1 else f" (after {result.attempts} tries)"
    print(f"Pushed the brief for {result.day} to {BRANCH}{tries}: {', '.join(result.files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
