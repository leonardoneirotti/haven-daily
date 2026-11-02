"""Which briefs the site is built from (issue #26).

Both workflows run `python -m haven.render --out site` with no `--briefs`: real
briefs (`data/briefs/`) as soon as there is one, the samples until then, so the
merge of #26 doesn't break the site before the first morning run.
"""

from haven import render


def test_real_briefs_once_there_is_one(tmp_path):
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs" / "2026-11-03.json").write_text("{}", encoding="utf-8")
    assert render.default_briefs_dir(tmp_path) == tmp_path / "briefs"


def test_samples_while_there_is_no_real_brief_folder(tmp_path):
    assert render.default_briefs_dir(tmp_path) == tmp_path / "sample" / "briefs"


def test_samples_while_the_real_brief_folder_is_empty(tmp_path):
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs" / "notes.txt").write_text("not a brief", encoding="utf-8")
    assert render.default_briefs_dir(tmp_path) == tmp_path / "sample" / "briefs"


def test_samples_and_real_briefs_are_never_mixed(tmp_path):
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs" / "2026-11-03.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sample" / "briefs").mkdir(parents=True)
    (tmp_path / "sample" / "briefs" / "2026-10-29.json").write_text("{}", encoding="utf-8")
    assert render.default_briefs_dir(tmp_path) == tmp_path / "briefs"


def test_the_repo_default_today_is_the_samples():
    # No real brief is committed yet (the first comes from the morning job).
    assert render.default_briefs_dir() == render.PROJECT_DIR / "data" / "sample" / "briefs"
