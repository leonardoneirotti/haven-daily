"""Relevance filter, stage 1: rules (spec §5.4; issue #12).

Every item leaves the rules as **kept**, **dropped** or **to the AI check** (stage 2, #13),
always with a reason. Rule order, first match wins:

1. older than 48 h            -> dropped  (exactly 48 h is kept; a date-only item is aged
                                           from the end of its day; a timestamp without a
                                           timezone is Amsterdam time; no readable date = not
                                           dropped for age)
2. auto-keep source           -> kept     (Port Authority news, ECT: skip the word lists and
                                           stage 2; owner's decision, 1 Nov 2026)
3. off-topic word in headline -> dropped  (word lists from config/filter.toml, per language)
4. anything else              -> to the AI check

Headlines are invented (hard rule 13). No test touches the network.
"""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from haven import storage
from haven.clock import AMSTERDAM
from haven.collect import run_collect
from haven.config import FilterConfig, Source, load_filter
from haven.feeds import FeedResult, Item
from haven.filter import (
    DROP,
    KEEP,
    TO_AI,
    apply_rules,
    decide,
    off_topic_word,
)

RUN = datetime(2026, 11, 1, 6, 45, tzinfo=AMSTERDAM)  # a morning run, winter time (+01:00)

PORT = Source(id="port-authority-news", name="Port of Rotterdam Authority news", verdict="use",
              urls=("https://port.test/news",), access="html", language="en", auto_keep=True)
CONTARGO = Source(id="contargo-news", name="Contargo business news", verdict="use",
                  urls=("https://contargo.test/news",), access="html", language="en")
RIJNMOND = Source(id="rtv-rijnmond", name="RTV Rijnmond", verdict="headline-only",
                  urls=("https://rijnmond.test/rss",), access="rss", language="nl")
SOURCES = (PORT, CONTARGO, RIJNMOND)
BY_ID = {s.id: s for s in SOURCES}

WORDS = FilterConfig(off_topic={
    "en": ("football", "Champions League", "housing"),
    "nl": ("voetbal*", "woningbouw"),
})


def item(headline="Invented: crane outage at a container terminal", published="2026-11-01T05:00:00+01:00",
         source="contargo-news", language="en", url=None, snippet=None):
    return Item(source=source, headline=headline, url=url or f"https://{source}.test/{abs(hash(headline))}",
                published=published, language=language,
                access="headline-only" if source == "rtv-rijnmond" else "full", snippet=snippet)


def decision_for(it, now=RUN, config=WORDS):
    source = BY_ID.get(it.source)
    return decide(it, source, config.off_topic.get(it.language, ()), now)


# --- the decision table ------------------------------------------------------------------

TABLE = [
    # (what, item, expected outcome, expected reason)
    ("recent, not Rotterdam-specific",
     item(), TO_AI, "not decided by the rules: goes to the AI check"),
    ("recent, auto-keep source",
     item(source="port-authority-news"), KEEP, "Rotterdam-specific source (auto-keep)"),
    ("three days old",
     item(published="2026-10-29T06:00:00+01:00"), DROP, "older than 48 h"),
    ("three days old, auto-keep source: age comes first",
     item(source="port-authority-news", published="2026-10-29T06:00:00+01:00"), DROP, "older than 48 h"),
    ("off-topic word",
     item(headline="Invented football club opens new stadium"), DROP, 'off-topic word "football"'),
    ("off-topic word, auto-keep source: auto-keep skips the word lists",
     item(source="port-authority-news", headline="Invented housing plan near the old harbour"),
     KEEP, "Rotterdam-specific source (auto-keep)"),
    ("old and off-topic: the first rule gives the reason",
     item(headline="Invented football result", published="2026-10-20T12:00:00+01:00"), DROP, "older than 48 h"),
    ("no date: not dropped for age",
     item(published=None), TO_AI, "not decided by the rules: goes to the AI check"),
    ("no date, auto-keep source",
     item(source="port-authority-news", published=None), KEEP, "Rotterdam-specific source (auto-keep)"),
    ("no date, off-topic word: the word lists still apply",
     item(published=None, headline="Invented Champions League draw"), DROP, 'off-topic word "Champions League"'),
    ("unreadable date counts as no date",
     item(published="yesterday evening"), TO_AI, "not decided by the rules: goes to the AI check"),
    ("timestamp without a timezone is read as Amsterdam time, so the age rule applies",
     item(published="2026-10-01T06:00:00"), DROP, "older than 48 h"),
    ("date in the future (clock or feed error): not dropped",
     item(published="2026-11-03T09:00:00+01:00"), TO_AI, "not decided by the rules: goes to the AI check"),
    ("Dutch word list for a Dutch item",
     item(source="rtv-rijnmond", language="nl", headline="Verzonnen voetbalclub wint derby"),
     DROP, 'off-topic word "voetbal*"'),
    ("source not in the config: never auto-kept",
     item(source="unknown-source"), TO_AI, "not decided by the rules: goes to the AI check"),
]


@pytest.mark.parametrize("what, it, outcome, reason", TABLE, ids=[row[0] for row in TABLE])
def test_decision_table(what, it, outcome, reason):
    decision = decision_for(it)
    assert (decision.outcome, decision.reason) == (outcome, reason)


# --- the 48 h boundary (owner's decision, 1 Nov 2026) ------------------------------------


def test_exactly_48_hours_old_is_kept_and_one_second_older_is_dropped():
    exactly = item(published="2026-10-30T06:45:00+01:00")
    older = item(published="2026-10-30T06:44:59+01:00")
    assert decision_for(exactly).outcome == TO_AI
    assert decision_for(older).outcome == DROP


def test_age_is_compared_as_real_time_whatever_the_offset_is_written_in():
    # 05:45 UTC on 30 Oct is 06:45 Amsterdam: exactly 48 h before the run.
    assert decision_for(item(published="2026-10-30T05:45:00+00:00")).outcome == TO_AI
    assert decision_for(item(published="2026-10-30T05:44:59Z")).outcome == DROP


# --- date-only items are aged from the end of their day (owner's decision, 1 Nov 2026) ---


@pytest.mark.parametrize("now, outcome", [
    (datetime(2026, 11, 1, 6, 45, tzinfo=AMSTERDAM), TO_AI),     # ~31 h after the end of 30 Oct
    (datetime(2026, 11, 2, 0, 0, tzinfo=AMSTERDAM), TO_AI),      # exactly 48 h: still kept
    (datetime(2026, 11, 2, 0, 0, 1, tzinfo=AMSTERDAM), DROP),    # a second later: dropped
])
def test_a_date_only_item_is_aged_from_the_end_of_its_day(now, outcome):
    assert decision_for(item(published="2026-10-30"), now=now).outcome == outcome


def test_a_date_only_item_from_two_days_before_the_run_is_dropped():
    # 29 Oct ended at 30 Oct 00:00, 54 h 45 min before the run.
    assert decision_for(item(published="2026-10-29")).outcome == DROP


def test_the_end_of_day_counts_real_hours_across_the_clock_change():
    # 24 Oct 2026 ended at 25 Oct 00:00 summer time (+02:00) = 24 Oct 22:00 UTC. Clocks went
    # back that night, so 48 real hours later is 26 Oct 23:00 winter time, not midnight.
    it = item(published="2026-10-24")
    assert decision_for(it, now=datetime(2026, 10, 26, 23, 0, tzinfo=AMSTERDAM)).outcome == TO_AI
    assert decision_for(it, now=datetime(2026, 10, 26, 23, 0, 1, tzinfo=AMSTERDAM)).outcome == DROP


def test_a_timestamp_without_a_timezone_is_read_as_amsterdam_time():
    # Owner's decision, 1 Nov 2026: 06:45 without a zone = 06:45 Amsterdam = exactly 48 h.
    assert decision_for(item(published="2026-10-30T06:45:00")).outcome == TO_AI
    assert decision_for(item(published="2026-10-30T06:44:59")).outcome == DROP
    # Amsterdam, not UTC: read as UTC, 06:00 would be 07:00 Amsterdam and still be kept.
    assert decision_for(item(published="2026-10-30T06:00:00")).outcome == DROP


def test_a_timestamp_without_a_timezone_uses_summer_time_on_a_summer_date():
    # 30 Jul 08:00 without a zone = 08:00 CEST (+02:00) = 06:00 UTC; the run is 1 Aug 08:00 CEST.
    run = datetime(2026, 8, 1, 8, 0, tzinfo=AMSTERDAM)
    assert decision_for(item(published="2026-07-30T08:00:00"), now=run).outcome == TO_AI
    assert decision_for(item(published="2026-07-30T07:59:59"), now=run).outcome == DROP


def test_an_auto_keep_source_skips_the_word_lists_but_not_the_age_rule():
    # Owner's decision, 1 Nov 2026.
    words = FilterConfig(off_topic={"en": ("football",)})
    recent = item(source="port-authority-news", headline="Invented football pitch on the Maasvlakte")
    old = replace(recent, published="2026-10-29T06:00:00+01:00")
    other_source = replace(recent, source="contargo-news")
    assert decision_for(recent, config=words).outcome == KEEP
    assert decision_for(old, config=words) == decision_for(old, config=FilterConfig(off_topic={}))
    assert decision_for(old, config=words).reason == "older than 48 h"
    assert decision_for(other_source, config=words).reason == 'off-topic word "football"'


def test_a_run_time_without_a_timezone_is_refused():
    with pytest.raises(ValueError, match="timezone"):
        decide(item(), CONTARGO, (), datetime(2026, 11, 1, 6, 45))


# --- off-topic words ---------------------------------------------------------------------


@pytest.mark.parametrize("headline, words, found", [
    ("Invented FOOTBALL news", ("football",), "football"),                      # any case
    ("Invented transport news", ("sport",), None),                             # whole words only
    ("Invented sports news", ("sport",), None),                                # no plural by itself
    ("Invented sports news", ("sport*",), "sport*"),                           # * = any ending
    ("Verzonnen Voetbalclub-nieuws", ("voetbal*",), "voetbal*"),               # Dutch compound
    ("Invented Feyenoord-supporters march", ("Feyenoord",), "Feyenoord"),      # hyphen ends a word
    ("Invented Champions   League draw", ("champions league",), "champions league"),  # phrases
    ("Invented league of champions", ("champions league",), None),
    ("Invented crane outage", (), None),                                       # empty list
    ("Invented café housing", ("café",), "café"),                              # accented letters
])
def test_off_topic_word_matching(headline, words, found):
    assert off_topic_word(headline, words) == found


def test_the_word_list_of_the_items_language_is_used():
    english_item = item(headline="Invented voetbal headline in English", language="en")
    assert decision_for(english_item).outcome == TO_AI  # "voetbal*" is only on the Dutch list


def test_word_lists_come_from_the_config_not_the_code():
    football = item(headline="Invented football club news")
    assert decision_for(football, config=FilterConfig(off_topic={})).outcome == TO_AI
    assert decision_for(football, config=FilterConfig(off_topic={"en": ("football",)})).outcome == DROP


# --- the whole stage ---------------------------------------------------------------------


def test_every_item_leaves_the_rules_with_an_outcome_and_a_reason_in_input_order():
    items = [
        item(headline="Invented crane outage"),
        item(headline="Invented football news"),
        item(source="port-authority-news", headline="Invented new quay wall"),
    ]
    ruled = apply_rules(items, SOURCES, WORDS, RUN)
    assert [r.item.headline for r in ruled] == [i.headline for i in items]
    assert [r.decision.outcome for r in ruled] == [TO_AI, DROP, KEEP]
    assert all(r.decision.reason for r in ruled)


def test_kept_and_dropped_items_carry_the_filter_record_and_items_for_the_ai_check_do_not_yet():
    ruled = apply_rules(
        [item(headline="Invented football news", published="2026-10-20T08:00:00+01:00"),
         item(source="port-authority-news"),
         item()],
        SOURCES, WORDS, RUN)
    dropped, kept, to_ai = (r.item for r in ruled)
    assert dropped.filter == {"kept": False, "stage": "rules", "reason": "older than 48 h"}
    assert kept.filter == {"kept": True, "stage": "rules", "reason": "Rotterdam-specific source (auto-keep)"}
    assert to_ai.filter is None  # stage 2 (#13) writes it


def test_the_filter_record_goes_into_the_stored_line_and_the_snippet_never_does():
    secret = "Invented teaser sentence that must never reach a file"
    [ruled] = apply_rules([item(source="port-authority-news", snippet=secret)], SOURCES, WORDS, RUN)
    record = ruled.item.record()
    assert record["filter"] == {"kept": True, "stage": "rules", "reason": "Rotterdam-specific source (auto-keep)"}
    assert ruled.item.snippet == secret  # still in memory for stage 2 / the summariser
    assert secret not in repr(record)
    assert set(record) == {"source", "headline", "url", "published", "language", "access", "filter"}


def test_an_item_with_no_filter_decision_yet_has_no_filter_field_in_its_record():
    assert "filter" not in item().record()


def test_a_ruled_items_file_can_be_written_by_storage(tmp_path):
    ruled = apply_rules([item(), item(source="port-authority-news")], SOURCES, WORDS, RUN)
    storage.write("items", date(2026, 11, 1), [r.item.record() for r in ruled], data_dir=tmp_path)
    lines = storage.read("items", date(2026, 11, 1), data_dir=tmp_path)
    assert [line.get("filter", {}).get("kept") for line in lines] == [None, True]


# --- undated items: the 14-day link check is the collect step's duplicate check ----------


def test_an_undated_item_whose_link_was_seen_in_the_last_14_days_never_reaches_the_rules(tmp_path):
    seen = "https://contargo.test/news/invented-old-story"
    storage.write("items", date(2026, 10, 25), [
        {"source": "contargo-news", "headline": "Invented old story", "url": seen,
         "published": None, "language": "en", "access": "full"},
    ], data_dir=tmp_path)
    fresh = "https://contargo.test/news/invented-new-story"

    def collector(source, fetcher, previous_run):
        return FeedResult(items=[item(url=seen, published=None), item(url=fresh, published=None)], failures=[])

    result = run_collect([CONTARGO], fetcher=None, today=date(2026, 11, 1), data_dir=tmp_path,
                         now=lambda: RUN, collector=collector)
    ruled = apply_rules(result.items, SOURCES, WORDS, RUN)
    assert [r.item.url for r in ruled] == [fresh]  # the seen link was dropped as a duplicate
    assert ruled[0].decision.outcome == TO_AI      # the new undated link is not dropped for age


# --- config: the word lists ----------------------------------------------------------------


def test_the_repo_word_lists_load():
    config = load_filter()
    assert set(config.off_topic) >= {"en", "nl"}


@pytest.mark.parametrize("word", ["*", "voet*bal", "*bal", "voetbal**"])
def test_a_star_is_only_allowed_at_the_end_of_a_word(tmp_path, word):
    path = tmp_path / "filter.toml"
    path.write_text(f'[off_topic]\nnl = ["{word}"]\n', encoding="utf-8")
    from haven.config import ConfigError
    with pytest.raises(ConfigError, match=r"off_topic\.nl.*\*"):
        load_filter(path)


def test_a_star_at_the_end_of_a_word_is_allowed(tmp_path):
    path = tmp_path / "filter.toml"
    path.write_text('[off_topic]\nnl = ["voetbal*"]\n', encoding="utf-8")
    assert load_filter(path).off_topic == {"nl": ("voetbal*",)}
