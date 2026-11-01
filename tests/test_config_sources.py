"""Loading config/sources.toml: a valid file gives Source objects, every kind of
bad file gives a ConfigError that says what is wrong and where."""

import textwrap

import pytest

from haven.config import ConfigError, Source, load_sources

GOOD = """
[[source]]
id = "ect-news"
name = "ECT news"
verdict = "use"
urls = ["https://www.ect.nl/en/news-feed"]
access = "html"
language = "en"
auto_keep = true

[[source]]
id = "nieuwsblad-transport"
name = "Nieuwsblad Transport"
verdict = "headline-only"
urls = ["https://www.nt.nl/havens/feed/", "https://www.nt.nl/tag/rotterdam/feed/"]
access = "rss"
language = "nl"
note = "Paywalled, blocks AI crawlers."

[[source]]
id = "nos"
name = "NOS"
verdict = "drop"
note = "Terms forbid automated access by bots."
"""


def write(tmp_path, text):
    path = tmp_path / "sources.toml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def entry(**fields):
    """One [[source]] table; starts from a valid 'use' source, then overrides/removes fields."""
    base = {
        "id": "ect-news",
        "name": "ECT news",
        "verdict": "use",
        "urls": ["https://www.ect.nl/en/news-feed"],
        "access": "html",
        "language": "en",
    }
    base.update(fields)
    lines = ["[[source]]"]
    for key, value in base.items():
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, list):
            lines.append(f"{key} = [{', '.join(f'\"{v}\"' for v in value)}]")
        else:
            lines.append(f'{key} = "{value}"')
    return "\n".join(lines) + "\n\n"


def bad(tmp_path, text, match):
    with pytest.raises(ConfigError, match=match) as caught:
        load_sources(write(tmp_path, text))
    return str(caught.value)


# --- valid file -----------------------------------------------------------------


def test_valid_file_gives_sources_in_file_order(tmp_path):
    sources = load_sources(write(tmp_path, GOOD))

    assert [s.id for s in sources] == ["ect-news", "nieuwsblad-transport", "nos"]
    assert sources[0] == Source(
        id="ect-news",
        name="ECT news",
        verdict="use",
        urls=("https://www.ect.nl/en/news-feed",),
        access="html",
        language="en",
        auto_keep=True,
        note=None,
    )


def test_source_with_two_feeds_keeps_both_urls(tmp_path):
    nt = load_sources(write(tmp_path, GOOD))[1]
    assert nt.urls == ("https://www.nt.nl/havens/feed/", "https://www.nt.nl/tag/rotterdam/feed/")
    assert nt.verdict == "headline-only"
    assert nt.auto_keep is False  # default when not given


def test_dropped_source_needs_no_url_and_is_never_fetched(tmp_path):
    sources = load_sources(write(tmp_path, GOOD))
    nos = sources[2]
    assert nos.urls == () and nos.access is None and nos.language is None
    assert [s.id for s in sources if s.fetched] == ["ect-news", "nieuwsblad-transport"]


# --- bad files: one specific error each ----------------------------------------------


def test_unknown_verdict(tmp_path):
    message = bad(tmp_path, entry(verdict="maybe"), "unknown verdict 'maybe'")
    assert "use, headline-only, drop" in message
    assert "ect-news" in message


def test_missing_url_on_a_fetched_source(tmp_path):
    bad(tmp_path, entry(urls=None), "ect-news.*no URL")


def test_empty_url_list_on_a_fetched_source(tmp_path):
    bad(tmp_path, entry(urls=[]), "ect-news.*no URL")


def test_url_that_is_not_a_web_address(tmp_path):
    bad(tmp_path, entry(urls=["www.ect.nl/en/news-feed"]), "must start with https://")


def test_duplicate_id(tmp_path):
    bad(tmp_path, entry() + entry(name="ECT news again"), "duplicate id 'ect-news'")


def test_unknown_access_type(tmp_path):
    bad(tmp_path, entry(access="api"), "unknown access 'api'.*rss, html")


@pytest.mark.parametrize("field", ["id", "name", "verdict"])
def test_missing_required_field_on_any_source(tmp_path, field):
    bad(tmp_path, entry(**{field: None}), f"missing '{field}'")


@pytest.mark.parametrize("field", ["access", "language"])
def test_missing_field_needed_for_fetching(tmp_path, field):
    bad(tmp_path, entry(**{field: None}), f"ect-news.*missing '{field}'")


def test_misspelt_field_is_not_silently_ignored(tmp_path):
    bad(tmp_path, entry(auto_kep=True), "unknown field 'auto_kep'")


def test_auto_keep_must_be_true_or_false(tmp_path):
    bad(tmp_path, entry(auto_keep="yes"), "auto_keep.*true or false")


def test_language_must_be_a_two_letter_code(tmp_path):
    bad(tmp_path, entry(language="English"), "language 'English'.*two-letter")


def test_file_with_no_sources(tmp_path):
    bad(tmp_path, "# nothing here\n", "no \\[\\[source\\]\\] entries")


def test_broken_toml_names_the_file(tmp_path):
    bad(tmp_path, '[[source]]\nid = "ect-news\n', "sources.toml.*not valid TOML")


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_sources(tmp_path / "nope.toml")
