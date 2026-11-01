"""The real config files load, and config/sources.toml says the same as SOURCES.md.

SOURCES.md is the human-readable list; config/sources.toml is what the code
reads. This test fails as soon as one is changed without the other.
"""

import re
from pathlib import Path

from haven.config import load_filter, load_sources

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = {"Use": "use", "Headline-only": "headline-only", "Dropped": "drop"}


def sources_md() -> dict[str, tuple[str, tuple[str, ...]]]:
    """name -> (verdict, urls) from the tables under ## Use / ## Headline-only / ## Dropped."""
    found = {}
    verdict = None
    for line in (ROOT / "SOURCES.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            verdict = SECTIONS.get(line[3:].strip())
            continue
        if verdict is None or not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == "Source":  # table header
            continue
        urls = tuple(re.findall(r"https?://[^\s·|]+", cells[1])) if verdict != "drop" else ()
        found[cells[0]] = (verdict, urls)
    return found


def test_sources_md_was_parsed():
    listed = sources_md()
    assert sum(v == "use" for v, _ in listed.values()) == 5
    assert sum(v == "headline-only" for v, _ in listed.values()) == 5


def test_config_and_sources_md_list_the_same_sources_with_the_same_verdicts():
    in_md = {name: verdict for name, (verdict, _) in sources_md().items()}
    in_config = {s.name: s.verdict for s in load_sources()}
    assert in_config == in_md


def test_config_uses_the_same_urls_as_sources_md():
    in_md = {name: urls for name, (verdict, urls) in sources_md().items() if verdict != "drop"}
    in_config = {s.name: s.urls for s in load_sources() if s.fetched}
    assert in_config == in_md


def test_only_port_authority_news_and_ect_are_auto_keep():
    # Spec §4: "Auto-keep (skips the AI relevance check): Port Authority news and ECT only."
    assert {s.name for s in load_sources() if s.auto_keep} == {
        "Port of Rotterdam Authority news & press releases",
        "ECT news",
    }


def test_filter_config_loads_and_starts_empty():
    assert load_filter().off_topic == {"en": (), "nl": ()}
