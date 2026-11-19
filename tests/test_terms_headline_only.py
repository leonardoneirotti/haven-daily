"""RTV Rijnmond and Kuehne+Nagel SeaNews are headline-only because of their terms (issue #98).

The owner read both sources' terms on 15 Nov 2026 (spec §4, §11):
- RTV Rijnmond (rijnmond.nl/aansprakelijkheid): all rights reserved, any use needs prior permission;
- K+N SeaNews (seaexplorer.com/legal-notice): a limited, non-transferable right to use the content as-is.
Decision: both headline-only, with a link to the original and no summaries, until each gives
written permission. These tests read the real config, so the decision can't be undone by accident.

RTV Rijnmond gave that permission on 19 Nov 2026 (#107): its own verdict stays headline-only and a
`permission` line lifts it to summaries (tests/test_publisher_permission.py).
"""

import re
from datetime import date, datetime

import pytest

from haven import summarise
from haven.clock import AMSTERDAM
from haven.config import load_sources
from haven.pages import collect_page
from tests.test_method_page import render_method
from tests.test_pages import KN_WEEKLY, WEEKLY_TITLE, fetcher_for, kn_routes, real

TERMS_SOURCES = ("rtv-rijnmond", "kn-seanews")


@pytest.mark.parametrize("source_id", TERMS_SOURCES)
def test_the_source_is_headline_only_in_the_real_config(source_id):
    assert real(source_id).verdict == "headline-only"


@pytest.mark.parametrize("source_id", TERMS_SOURCES)
def test_the_public_reason_names_the_terms(source_id):
    """The Method page shows `why`: it must say that the terms are the reason."""
    assert "terms" in real(source_id).why.lower()


def test_rijnmond_still_names_its_ai_opt_out_too():
    """Two reasons now: its terms and its robots.txt block on AI crawlers (hard rule 12)."""
    why = real("rtv-rijnmond").why.lower()
    assert "ai crawlers" in why


@pytest.mark.parametrize("source_id", TERMS_SOURCES)
def test_no_stale_terms_to_check_note_is_left(source_id):
    assert "terms not found" not in (real(source_id).note or "").lower()


def test_kn_with_the_real_config_opens_no_article_and_keeps_only_headline_and_link():
    fetcher, net = fetcher_for(kn_routes())
    result = collect_page(real("kn-seanews"), fetcher)
    assert result.failures == []
    [item] = result.items
    assert (item.headline, item.url, item.access) == (WEEKLY_TITLE, KN_WEEKLY, "headline-only")
    assert item.snippet is None and item.article_text is None
    assert KN_WEEKLY not in net.calls  # the Rotterdam paragraph is never read


def test_kn_item_from_the_real_config_gets_no_summary_or_impact_from_the_ai():
    [item] = collect_page(real("kn-seanews"), fetcher_for(kn_routes())[0]).items
    read_at = datetime(2026, 11, 16, 6, 47, tzinfo=AMSTERDAM)
    request = summarise._request(item, summarise.SUMMARY_MODEL, "invented system prompt", [],
                                 date(2026, 11, 16), read_at)
    schema = request["output_config"]["format"]["schema"]
    assert "summary" not in schema["properties"] and "impact" not in schema["properties"]
    content = request["messages"][0]["content"]
    assert "<article>" not in content
    assert content.startswith("Rate this item from its headline only.")


def test_the_method_page_lists_kn_under_headline_only_and_rijnmond_under_use_by_permission():
    page = render_method(sources=load_sources())
    groups = dict(re.findall(r'<div class="source-group" id="sources-([\w-]+)">(.*?)</div>', page, re.S))
    assert "Kuehne+Nagel SeaNews" in groups["headline-only"] and "Kuehne+Nagel SeaNews" not in groups["use"]
    assert "RTV Rijnmond" in groups["use"] and "RTV Rijnmond" not in groups["headline-only"]  # #107
