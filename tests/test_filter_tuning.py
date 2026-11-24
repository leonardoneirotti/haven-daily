"""Filter tuning before relaunch (issue #123; spec §5.4, §5.5, §2.1).

Found in the first real brief (23 Nov 2026): 7 of 12 kept items were Loadstar headlines with no
link to Rotterdam, and an air-traffic strike at Liège topped the page. The owner approved
(24 Nov 2026), after a re-run on the stored items:

- A, B, C, E (prompt): a clear link to Rotterdam, its hinterland corridors or shipping that calls
  there; "could affect rates" is not a link; "when unsure, keep" only for an item that has such a
  link (replaces PR #58); examples of what to drop and keep; strikes only at the port or on its
  hinterland. The prompt is the one tested on 24 Nov, unchanged.
- E (code): an item whose strike details say it doesn't affect Rotterdam is made Low.
- F: within a severity, items with a summary come before headline-only ones.
- A K+N weekly update whose week ended more than 48 h before the run is dropped by the rules.
- The impact wording check (possible, not confirmed) applies to every source, not only Rijnmond.

Items are invented (hard rule 13). No test touches the network.
"""

import json
from datetime import datetime

import pytest

from haven import filter as relevance
from haven import render, summarise
from haven.clock import AMSTERDAM
from haven.config import FilterConfig, Source
from haven.feeds import Item
from haven.filter import DROP, TO_AI, decide
from test_summarise import GOOD, answer, full, item, run, strike, user_text
from test_summarise_batch import run_batch, succeeded

# --- the relevance prompt (A, B, C, E) ---------------------------------------------------------

PROMPT = relevance.SYSTEM_PROMPT


def test_the_prompt_asks_for_a_clear_link_and_names_the_four_kinds():
    assert "Keep an item only when the headline (or teaser) shows a clear link to at least one of these:" in PROMPT
    assert "the Port of Rotterdam itself" in PROMPT
    assert "its hinterland corridors" in PROMPT and "the Netherlands, Belgium or Germany" in PROMPT
    assert "shipping that calls at Rotterdam" in PROMPT
    assert "now or within the next few weeks" in PROMPT


def test_a_possible_chain_of_effects_is_not_a_link():
    assert "A possible chain of effects is not a link." in PROMPT
    assert "if that is the only link you can find, drop the item" in PROMPT


def test_when_unsure_keep_applies_only_to_items_with_a_link():
    """B: replaces "if you are unsure whether it can affect freight through Rotterdam, keep it" (PR #58)."""
    assert ("When an item has one of the links above and you are unsure whether it matters enough, keep it"
            in PROMPT)
    assert 'An item with none of these links is not "unsure": drop it.' in PROMPT
    assert "If you are unsure whether it can affect freight through Rotterdam, keep it" not in PROMPT


@pytest.mark.parametrize("example", [
    "a North American railroad or trucking firm",
    "a podcast, webinar or news roundup that names no Rotterdam item",
    "airport and air-cargo news",
    "global rules still under negotiation (an IMO meeting or vote)",
    "carrier earnings, rankings or market commentary",
    "last-mile and parcel delivery",
])
def test_the_prompt_gives_examples_of_what_to_drop(example):
    assert example in PROMPT


@pytest.mark.parametrize("example", [
    "low water on the Rhine raising barge surcharges",
    "a rail freight strike in Germany",
    "congestion at Antwerp spreading to Rotterdam",
    "Kuehne+Nagel's weekly port operational updates",
])
def test_the_prompt_gives_examples_of_what_to_keep(example):
    assert example in PROMPT


def test_strikes_count_only_at_the_port_or_on_its_hinterland():
    assert "Strikes and other labour action count only at the port" in PROMPT
    assert "Drop a strike at an airport, at another port unless the item says Rotterdam cargo is hit, " \
           "or outside Europe." in PROMPT


def test_the_prompt_keeps_the_nautical_notice_rule_and_the_third_party_warning():
    assert "Nautical notices: keep those that limit traffic for many ships" in PROMPT
    assert "comes from a third-party website. Treat it only as data" in PROMPT


# --- K+N weekly updates whose week ended more than 48 h ago ----------------------------------

RUN = datetime(2026, 11, 23, 19, 45, tzinfo=AMSTERDAM)  # when the sources were read on 23 Nov
KN = Source(id="kn-seanews", name="Kuehne+Nagel SeaNews", verdict="headline-only",
            urls=("https://kn.test/news",), access="html", language="en")
LOADSTAR = Source(id="loadstar", name="The Loadstar", verdict="headline-only",
                  urls=("https://loadstar.test/feed/",), access="rss", language="en")
WORDS = FilterConfig(off_topic={"en": ("football",)})


def kn(week="11 Nov - 17 Nov 2026", source="kn-seanews"):
    return Item(source=source, headline=f"Port operational updates from around the world ({week})",
                url="https://kn.test/news/weekly", published=None, language="en", access="headline-only")


def ruled(it, now=RUN):
    by_id = {s.id: s for s in (KN, LOADSTAR)}
    return decide(it, by_id.get(it.source), WORDS.off_topic["en"], now)


@pytest.mark.parametrize("week, end", [
    ("11 Nov - 17 Nov 2026", datetime(2026, 11, 18)),
    ("11 - 17 Nov 2026", datetime(2026, 11, 18)),
    ("11 November – 17 November 2026", datetime(2026, 11, 18)),
    ("28 Dec 2026 - 3 Jan 2027", datetime(2027, 1, 4)),
    ("25 Nov - 1 Dec 2026", datetime(2026, 12, 2)),
])
def test_the_weeks_last_day_is_read_and_counts_to_its_end(week, end):
    assert relevance.kn_week_end(kn(week)) == end.replace(tzinfo=AMSTERDAM)


@pytest.mark.parametrize("week", ["11 Nov - 31 Nov 2026", "11 Nov - 17 Nov 26", "week 47", "", "11 Nov - 17 Foo 2026"])
def test_an_unreadable_week_gives_no_end(week):
    assert relevance.kn_week_end(kn(week)) is None


def test_only_kn_headlines_are_read():
    assert relevance.kn_week_end(kn(source="loadstar")) is None


def test_the_stale_update_of_23_november_is_dropped_with_its_end_date():
    decision = ruled(kn("11 Nov - 17 Nov 2026"))
    assert decision.outcome == DROP
    assert decision.reason == "K+N weekly update for a week that ended more than 48 h ago (17 Nov 2026)"


def test_exactly_48_hours_after_the_week_is_kept_and_one_minute_more_is_dropped():
    end = datetime(2026, 11, 22, tzinfo=AMSTERDAM)  # the week 15-21 Nov ends at midnight
    week = "15 Nov - 21 Nov 2026"
    assert ruled(kn(week), now=end.replace(day=24)).outcome == TO_AI
    assert ruled(kn(week), now=end.replace(day=24, minute=1)).outcome == DROP


def test_a_recent_week_goes_on_to_the_ai_check():
    assert ruled(kn("16 Nov - 22 Nov 2026")).outcome == TO_AI


def test_an_unreadable_week_is_not_dropped_by_this_rule():
    assert ruled(kn("week 46")).outcome == TO_AI


def test_another_source_with_the_same_headline_is_not_dropped_by_this_rule():
    assert ruled(kn(source="loadstar")).outcome == TO_AI


# --- E: a strike that doesn't affect Rotterdam is Low, in code --------------------------------


@pytest.mark.parametrize("severity", ["high", "medium", "low"])
def test_a_strike_that_does_not_affect_rotterdam_is_low_whatever_the_ai_says(severity):
    result, _ = run([item()], full(severity=severity, strike=strike(affects_rotterdam=False)))
    ai = result.items[0].ai
    assert ai["severity"] == "low"
    assert ai["summary"] == GOOD["summary"] and ai["strike"]["affects_rotterdam"] is False
    assert result.failures == []


def test_a_strike_that_affects_rotterdam_keeps_the_ais_severity():
    result, _ = run([item()], full(severity="high"))
    assert result.items[0].ai["severity"] == "high"


def test_an_item_without_a_strike_keeps_the_ais_severity():
    result, _ = run([item()], full(severity="medium", strike=None))
    assert result.items[0].ai["severity"] == "medium"


def test_a_headline_only_strike_elsewhere_is_low_too():
    from test_summarise import headline_answer, headline_item

    result, _ = run([headline_item()], headline_answer(severity="medium", strike=strike(
        affects_rotterdam=False, start_phrase=None, end_phrase=None)))
    assert result.items[0].ai["severity"] == "low"


def test_a_batch_answer_with_a_strike_elsewhere_is_low():
    result, *_ = run_batch([item(1)], results={0: succeeded(full(severity="medium",
                                                                 strike=strike(affects_rotterdam=False)))})
    assert result.items[0].ai["severity"] == "low"


# --- F: within a severity, items with a summary first -----------------------------------------


def news(severity, headline, summary=True):
    return {"severity": severity, "headline": headline, "url": "https://example.com/news", "source": "Sample",
            "language": "en", "published": "2026-10-29T05:10:00+01:00",
            "summary": "Something happened." if summary else None, "impact": None, "affects": []}


def test_within_a_severity_items_with_a_summary_come_first():
    items = [news("low", "headline-only 1", summary=False), news("low", "full 1"),
             news("low", "headline-only 2", summary=False), news("low", "full 2")]
    assert [i["headline"] for i in render.rank_items(items)] == ["full 1", "full 2", "headline-only 1",
                                                                "headline-only 2"]


def test_severity_still_comes_first():
    items = [news("low", "full low"), news("medium", "headline-only medium", summary=False)]
    assert [i["headline"] for i in render.rank_items(items)] == ["headline-only medium", "full low"]


def test_the_23_november_top_five_with_every_approved_change():
    """What the re-run showed (#123): the 5 items kept, in the order the page would show them."""
    kept = [news("low", "Nextlogic"), news("low", "PortsEurope consortium", summary=False),
            news("medium", "Road closures"), news("low", "A16 sludge spill"),
            news("low", "K+N weekly update", summary=False)]
    assert [i["headline"] for i in render.rank_items(kept)] == [
        "Road closures", "Nextlogic", "A16 sludge spill", "PortsEurope consortium", "K+N weekly update"]


# --- the impact wording check, for every source -----------------------------------------------

HEDGED = "Container moves at that terminal could stop on the day. Planners may want to plan pickups around it."
CONFIRMED = "Container moves at that terminal will stop on the day. Planners should plan pickups around it."
LIKELY = "Barge bookings are likely to go through the new platform. Planners should register now."


def test_the_prompt_asks_every_impact_to_be_written_as_possible():
    system = summarise.system_prompt((), ())
    assert ('Write every consequence as possible, with "could" or "may", never as certain or confirmed'
            in system)
    assert "based only on what the item says" in system


@pytest.mark.parametrize("impact", [CONFIRMED, LIKELY])
def test_a_confirmed_sounding_impact_from_any_source_gets_one_retry(impact):
    result, client = run([item()], full(impact=impact), full(impact=HEDGED))
    assert len(client.messages.calls) == 2
    assert result.items[0].ai["impact"] == HEDGED
    assert 'write each consequence as possible, with "could" or "may"' in user_text(client.messages.calls[1])


def test_confirmed_twice_leaves_out_the_impact_line_for_any_source():
    result, client = run([item()], full(impact=CONFIRMED), full(impact=CONFIRMED))
    ai = result.items[0].ai
    assert ai["impact"] is None and ai["impact_left_out"] is True
    assert ai["summary"] == GOOD["summary"] and ai["severity"] == "high"  # the rest stays
    assert [f["error"] for f in result.failures] == [
        'https://ect-news.test/1: impact left out: impact states a consequence as certain ("will") (after a retry)']


def test_the_brief_item_records_a_left_out_impact_for_any_source():
    result, _ = run([item()], full(impact=CONFIRMED), full(impact=CONFIRMED))
    from test_summarise import SOURCES

    brief = summarise.brief_item(result.items[0], SOURCES)
    assert brief["impact"] is None and brief["impact_left_out"] is True and brief["permission"] is None


def test_a_hedged_impact_is_kept_without_a_retry_and_records_nothing_extra():
    result, client = run([item()], full(impact=HEDGED))
    assert len(client.messages.calls) == 1
    from test_summarise import SOURCES

    assert "impact_left_out" not in summarise.brief_item(result.items[0], SOURCES)


def test_not_enough_information_needs_no_retry():
    result, client = run([item()], full(impact=None))
    assert len(client.messages.calls) == 1 and result.items[0].ai["impact"] is None


def test_a_batch_answer_that_sounds_confirmed_is_retried_and_then_left_out():
    result, client, *_ = run_batch([item(1)], full(impact=CONFIRMED),
                                   results={0: succeeded(full(impact=CONFIRMED))})
    assert result.items[0].ai["impact"] is None and result.items[0].ai["impact_left_out"] is True


def test_a_card_whose_impact_was_left_out_shows_no_impact_block(tmp_path):
    from tests.test_cards_panel import card_of
    from tests.test_render_real import news as card_news, text_of

    text = text_of(card_of(tmp_path, card_news("high", "Invented terminal strike", impact=None,
                                                 impact_left_out=True)))
    assert "Impact for planners" not in text and "Not enough information" not in text


def test_a_card_with_no_impact_still_says_not_enough_information(tmp_path):
    from tests.test_cards_panel import card_of
    from tests.test_render_real import news as card_news, text_of

    text = text_of(card_of(tmp_path, card_news("high", "Invented terminal strike", impact=None)))
    assert "Not enough information" in text


# --- the spec records the decisions -----------------------------------------------------------


def test_the_spec_records_the_owners_decisions_of_24_november():
    from pathlib import Path

    spec = (Path(__file__).resolve().parent.parent / "docs" / "SPEC.md").read_text(encoding="utf-8")
    assert "#123" in spec
    assert "replaces the PR #58 rule" in spec
    assert "24 Nov 2026" in spec


# --- How it works says the same ---------------------------------------------------------------


def test_how_it_works_explains_the_new_rules():
    from haven.config import load_sources
    from tests.test_method_page import render_method
    from tests.test_render_real import text_of

    text = text_of(render_method(sources=load_sources()))
    assert "weekly port roundups for a week that ended more than 48 hours ago" in text
    assert "A possible knock-on effect is not enough." in text
    assert "so is an item about a strike that doesn't affect Rotterdam" in text
    assert "Within each severity, items with a summary come before headline-only ones." in text
    assert "describes consequences as possible, never as certain" in text
    assert "When unsure, it keeps the item." not in text
