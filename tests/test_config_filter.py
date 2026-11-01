"""Loading config/filter.toml: the off-topic word lists of the rule stage (spec §5.4)."""

import pytest

from haven.config import ConfigError, load_filter


def write(tmp_path, text):
    path = tmp_path / "filter.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_empty_lists_are_valid(tmp_path):
    config = load_filter(write(tmp_path, "[off_topic]\nen = []\nnl = []\n"))
    assert config.off_topic == {"en": (), "nl": ()}


def test_words_are_loaded_per_language(tmp_path):
    config = load_filter(write(tmp_path, '[off_topic]\nen = ["football", "housing"]\nnl = ["voetbal"]\n'))
    assert config.off_topic == {"en": ("football", "housing"), "nl": ("voetbal",)}


def test_word_list_must_be_a_list_of_words(tmp_path):
    with pytest.raises(ConfigError, match="off_topic.en.*list of words"):
        load_filter(write(tmp_path, '[off_topic]\nen = "football"\n'))


def test_empty_word_is_rejected(tmp_path):
    # An empty string would match every headline and drop everything.
    with pytest.raises(ConfigError, match="off_topic.nl.*empty word"):
        load_filter(write(tmp_path, '[off_topic]\nnl = ["voetbal", " "]\n'))


def test_language_key_must_be_a_two_letter_code(tmp_path):
    with pytest.raises(ConfigError, match="'english'.*two-letter"):
        load_filter(write(tmp_path, '[off_topic]\nenglish = ["football"]\n'))


def test_misspelt_section_is_not_silently_ignored(tmp_path):
    with pytest.raises(ConfigError, match="unknown section 'off_topics'"):
        load_filter(write(tmp_path, '[off_topics]\nen = ["football"]\n'))


def test_missing_off_topic_section(tmp_path):
    with pytest.raises(ConfigError, match="missing \\[off_topic\\]"):
        load_filter(write(tmp_path, "# nothing\n"))
