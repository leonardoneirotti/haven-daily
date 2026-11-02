"""Committing the day's data to main (spec §5.1 "Writing to main", issue #26).

The daily job stages **only `data/`**, commits as github-actions[bot] with the
message `Brief YYYY-MM-DD (automatic)`, then `git pull --rebase` and push, with
one retry. Most tests use real git in a temporary folder with a local bare repo
as "origin" (no network); the retry tests use a fake git that records calls.
"""

import json
import subprocess

import pytest

from haven import publish

DAY = "2026-11-03"


@pytest.fixture(autouse=True)
def isolated_git(tmp_path, monkeypatch):
    """Git without this machine's own settings (signing, hooks, names), so the tests run the same anywhere."""
    empty = tmp_path / "empty-gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(name, raising=False)


def git(cwd, *args):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def owner_commit(cwd, message):
    git(cwd, "-c", "user.name=Owner", "-c", "user.email=owner@example.invalid", "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path):
    """A clone of a local 'origin' with one commit on main, like the job's checkout."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "switch", "-q", "-c", "main")
    (work / "README.md").write_text("Haven Daily\n", encoding="utf-8")
    (work / "haven").mkdir()
    (work / "haven" / "run.py").write_text("# code\n", encoding="utf-8")
    git(work, "add", "README.md", "haven/run.py")
    owner_commit(work, "Start")
    git(work, "push", "-q", "origin", "main")
    return work


def write_day(work, day=DAY):
    """What the runner leaves behind: today's three files."""
    for kind, ext in (("briefs", "json"), ("items", "jsonl"), ("status", "json")):
        folder = work / "data" / kind
        folder.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"date": day}) if kind == "briefs" else "[]"
        (folder / f"{day}.{ext}").write_text(content + "\n", encoding="utf-8")


def origin_files(work, ref="origin/main"):
    git(work, "fetch", "-q", "origin")
    return git(work, "show", "--name-only", "--format=", ref).splitlines()


# --- only data/ ------------------------------------------------------------------


def test_only_data_is_committed_even_when_other_files_changed(repo):
    write_day(repo)
    (repo / "README.md").write_text("changed by something else\n", encoding="utf-8")
    (repo / "haven" / "new.py").write_text("# stray\n", encoding="utf-8")

    result = publish.publish(repo)

    assert sorted(origin_files(repo)) == [
        f"data/briefs/{DAY}.json", f"data/items/{DAY}.jsonl", f"data/status/{DAY}.json"]
    assert result.day == DAY
    status = git(repo, "status", "--porcelain")
    assert " M README.md" in status and "?? haven/new.py" in status  # left alone, not committed


def test_the_commit_comes_from_the_bot_with_the_spec_message(repo):
    write_day(repo)
    publish.publish(repo)
    git(repo, "fetch", "-q", "origin")
    author = git(repo, "log", "-1", "--format=%an <%ae>|%cn|%s", "origin/main")
    assert author == (f"github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
                      f"|github-actions[bot]|Brief {DAY} (automatic)")


def test_something_already_staged_outside_data_stops_everything(repo):
    write_day(repo)
    (repo / "README.md").write_text("staged by mistake\n", encoding="utf-8")
    git(repo, "add", "README.md")
    before = git(repo, "rev-parse", "HEAD")

    with pytest.raises(publish.PublishError, match="README.md"):
        publish.publish(repo)

    assert git(repo, "rev-parse", "HEAD") == before
    assert origin_files(repo) == ["README.md", "haven/run.py"]  # origin still at "Start"


def test_refuses_to_publish_from_any_branch_but_main(repo):
    git(repo, "switch", "-q", "-c", "feature")
    write_day(repo)
    before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(publish.PublishError, match="main"):
        publish.publish(repo)
    assert git(repo, "rev-parse", "HEAD") == before


def test_no_new_brief_means_nothing_is_committed(repo):
    items = repo / "data" / "items"
    items.mkdir(parents=True)
    (items / f"{DAY}.jsonl").write_text("\n", encoding="utf-8")
    before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(publish.PublishError, match="brief"):
        publish.publish(repo)
    assert git(repo, "rev-parse", "HEAD") == before
    assert git(repo, "diff", "--cached", "--name-only") == ""  # unstaged again


def test_nothing_new_in_data_is_an_error(repo):
    with pytest.raises(publish.PublishError, match="nothing"):
        publish.publish(repo)


def test_two_new_briefs_at_once_are_refused(repo):
    write_day(repo, "2026-11-03")
    write_day(repo, "2026-11-04")
    with pytest.raises(publish.PublishError, match="2026-11-03.*2026-11-04"):
        publish.publish(repo)


def test_an_edited_old_brief_is_refused_the_job_never_changes_a_published_day(repo):
    write_day(repo, "2026-11-02")
    git(repo, "add", "data")
    owner_commit(repo, "Brief 2026-11-02")
    git(repo, "push", "-q", "origin", "main")
    write_day(repo, DAY)
    (repo / "data" / "briefs" / "2026-11-02.json").write_text('{"date": "2026-11-02", "x": 1}\n', encoding="utf-8")
    with pytest.raises(publish.PublishError, match="2026-11-02"):
        publish.publish(repo)


# --- the owner pushed at the same moment -----------------------------------------


def test_a_correction_pushed_meanwhile_is_kept_and_the_brief_goes_on_top(repo, tmp_path):
    other = tmp_path / "owner-laptop"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    (other / "README.md").write_text("fixed a typo\n", encoding="utf-8")
    git(other, "add", "README.md")
    owner_commit(other, "Correction")
    git(other, "push", "-q", "origin", "main")

    write_day(repo)
    result = publish.publish(repo)

    git(repo, "fetch", "-q", "origin")
    assert git(repo, "log", "--format=%s", "origin/main").splitlines() == [
        f"Brief {DAY} (automatic)", "Correction", "Start"]
    assert result.attempts == 1


# --- push retry (fake git) -------------------------------------------------------


class FakeGit:
    """Answers like git for a clean day; `fail` lists the commands that fail, in the order they fail."""

    def __init__(self, fail=()):
        self.calls = []
        self.fail = list(fail)

    def __call__(self, args, cwd):
        self.calls.append(args)
        if self.fail and args[0] == self.fail[0]:
            self.fail.pop(0)
            return subprocess.CompletedProcess(args, 1, "", "rejected")
        out = {"rev-parse": "main\n",
               "diff": f"A\tdata/briefs/{DAY}.json\nA\tdata/items/{DAY}.jsonl\nA\tdata/status/{DAY}.json\n"}
        return subprocess.CompletedProcess(args, 0, out.get(args[0], ""), "")


def test_stages_with_the_data_pathspec_only(tmp_path):
    fake = FakeGit()
    publish.publish(tmp_path, git=fake)
    adds = [call for call in fake.calls if call[0] == "add"]
    assert adds == [["add", "--all", "--", "data"]]


def test_a_rejected_push_is_retried_once_after_another_rebase(tmp_path):
    fake = FakeGit(fail=["push"])
    result = publish.publish(tmp_path, git=fake)
    assert result.attempts == 2
    sequence = [call[0] for call in fake.calls if call[0] in ("pull", "push")]
    assert sequence == ["pull", "push", "pull", "push"]


def test_two_rejected_pushes_fail_the_job(tmp_path):
    fake = FakeGit(fail=["push", "push"])
    with pytest.raises(publish.PublishError, match="twice"):
        publish.publish(tmp_path, git=fake)
    assert [call[0] for call in fake.calls].count("push") == 2


def test_a_failed_rebase_is_aborted_and_retried_once(tmp_path):
    fake = FakeGit(fail=["pull"])
    result = publish.publish(tmp_path, git=fake)
    assert ["rebase", "--abort"] in fake.calls
    assert result.attempts == 2


def test_the_push_goes_to_main_on_origin(tmp_path):
    fake = FakeGit()
    publish.publish(tmp_path, git=fake)
    pushes = [call for call in fake.calls if call[0] == "push"]
    assert pushes == [["push", "origin", "HEAD:main"]]
    pulls = [call for call in fake.calls if call[0] == "pull"]
    assert pulls == [["pull", "--rebase", "origin", "main"]]
