"""Loading a local .env file for runs on the owner's laptop (CLAUDE.md, Secrets).

The tests use a plain dict as the environment, so no real variables are touched.
The values below are fake.
"""

import pytest

from haven.env import load_env

FAKE = "sk-fake-0000"


def write(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_sets_variables_and_returns_only_their_names(tmp_path):
    environ = {}
    loaded = load_env(write(tmp_path, f"ANTHROPIC_API_KEY={FAKE}\n"), environ)
    assert environ == {"ANTHROPIC_API_KEY": FAKE}
    assert loaded == ["ANTHROPIC_API_KEY"]


def test_skips_comments_blank_lines_and_strips_quotes_and_spaces(tmp_path):
    environ = {}
    load_env(write(tmp_path, f'# local keys\n\n  ANTHROPIC_API_KEY = "{FAKE}"  \nAISSTREAM_API_KEY=\'abc\'\n'), environ)
    assert environ == {"ANTHROPIC_API_KEY": FAKE, "AISSTREAM_API_KEY": "abc"}


def test_existing_environment_wins(tmp_path):
    # On GitHub Actions the secrets are already in the environment; a stray .env must not replace them.
    environ = {"ANTHROPIC_API_KEY": "from-actions"}
    loaded = load_env(write(tmp_path, f"ANTHROPIC_API_KEY={FAKE}\n"), environ)
    assert environ == {"ANTHROPIC_API_KEY": "from-actions"}
    assert loaded == []


def test_empty_values_are_not_set(tmp_path):
    # A copy of .env.example ("ANTHROPIC_API_KEY=") must look like "no key", not like an empty key.
    environ = {}
    assert load_env(write(tmp_path, "ANTHROPIC_API_KEY=\n"), environ) == []
    assert environ == {}


def test_no_env_file_is_fine(tmp_path):
    environ = {}
    assert load_env(tmp_path / ".env", environ) == []
    assert environ == {}


def test_bad_line_error_names_the_line_but_never_shows_its_content(tmp_path):
    with pytest.raises(ValueError, match="line 2") as caught:
        load_env(write(tmp_path, f"# keys\n{FAKE}\n"), {})
    assert FAKE not in str(caught.value)


def test_bad_variable_name_is_rejected_without_showing_the_value(tmp_path):
    with pytest.raises(ValueError, match="line 1") as caught:
        load_env(write(tmp_path, f"ANTHROPIC API KEY={FAKE}\n"), {})
    assert FAKE not in str(caught.value)
