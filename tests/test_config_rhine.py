"""Loading config/rhine.toml: the Kaub thresholds of the Rhine status (spec §2.2, issue #20)."""

import pytest

from haven.config import ConfigError, RhineThresholds, load_rhine

GOOD = """
[kaub]
alert_at_or_below = 80
watch_at_or_below = 150
watch_above = 460
alert_above = 640
"""


def write(tmp_path, text):
    path = tmp_path / "rhine.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_repo_file_has_the_owners_thresholds():
    # Low side: owner's decision 2 Nov 2026 (PR #71). High side: WSV Marke I and Marke II.
    assert load_rhine() == RhineThresholds(
        alert_at_or_below=80, watch_at_or_below=150, watch_above=460, alert_above=640
    )


def test_a_good_file_loads(tmp_path):
    assert load_rhine(write(tmp_path, GOOD)).watch_at_or_below == 150


def test_missing_kaub_section_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match=r"rhine.toml: missing \[kaub\]"):
        load_rhine(write(tmp_path, "# nothing\n"))


def test_unknown_section_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="unknown section 'lobith'"):
        load_rhine(write(tmp_path, GOOD + "\n[lobith]\nwatch_above = 1\n"))


def test_misspelt_threshold_is_not_silently_ignored(tmp_path):
    text = GOOD.replace("watch_above", "watch_abov")
    with pytest.raises(ConfigError, match="unknown field 'watch_abov'"):
        load_rhine(write(tmp_path, text))


def test_missing_threshold_is_an_error(tmp_path):
    text = GOOD.replace("alert_above = 640\n", "")
    with pytest.raises(ConfigError, match="missing 'alert_above'"):
        load_rhine(write(tmp_path, text))


@pytest.mark.parametrize("value", ['"150"', "150.5", "true"])
def test_thresholds_must_be_whole_centimetres(tmp_path, value):
    text = GOOD.replace("watch_at_or_below = 150", f"watch_at_or_below = {value}")
    with pytest.raises(ConfigError, match="watch_at_or_below.*whole number of centimetres"):
        load_rhine(write(tmp_path, text))


@pytest.mark.parametrize(
    "old, new",
    [
        ("alert_at_or_below = 80", "alert_at_or_below = 150"),  # equal to the Watch edge
        ("watch_at_or_below = 150", "watch_at_or_below = 500"),  # above the high Watch edge
        ("alert_above = 640", "alert_above = 400"),  # below the high Watch edge
    ],
)
def test_thresholds_must_be_in_order(tmp_path, old, new):
    # A swapped pair would turn every reading Normal or every reading Alert without a word.
    with pytest.raises(ConfigError, match="must be in order"):
        load_rhine(write(tmp_path, GOOD.replace(old, new)))
