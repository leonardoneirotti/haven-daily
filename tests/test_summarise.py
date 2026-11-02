"""Summariser: prompt, structured output, checks (spec §2.1, §5.6, §5.7, §5.10, §6; issue #15).

A fake Anthropic client returns made-up answers or raises the SDK's real error classes; no
test calls the API or touches the network. Headlines and article texts are invented (hard
rule 13). The real place and tag lists (config/) are used, so the ids are the real ones.
"""

import json
from datetime import date
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from haven import storage
from haven.config import Source
from haven.feeds import Item
from haven.render import render_site
from haven.summarise import (
    BREAKER,
    SUMMARY_MODEL,
    brief_item,
    known_strikes,
    phrase_in,
    published_day,
    resolve_phrase,
    summarise,
    unrated,
)

TODAY = date(2026, 11, 2)
ARTICLE = (
    "Invented article. Dockworkers at the ECT Delta terminal on the Maasvlakte will stop work "
    "on 5 November, the union said on Monday. Container handling is expected to halt for the "
    "whole day. Talks with the employer about a new wage deal broke down last week."
)
TEASER = "Invented teaser about a terminal."

ECT = Source(id="ect-news", name="ECT news", verdict="use", urls=("https://ect.test/",), access="html",
             language="en", auto_keep=True)
NLT = Source(id="nl-times", name="NL Times", verdict="headline-only", urls=("https://nlt.test/",),
             access="html", language="en")
SOURCES = (ECT, NLT)


def item(n=1, source="ect-news", access="full", headline=None, text=ARTICLE, snippet=TEASER, language="en"):
    return Item(source=source, headline=headline or f"Invented: dockworkers at ECT Delta to strike ({n})",
                url=f"https://{source}.test/{n}", published="2026-11-02T05:00:00+01:00", language=language,
                access=access, snippet=snippet, article_text=text,
                filter={"kept": True, "stage": "rules", "reason": "Rotterdam-specific source (auto-keep)"})


def headline_item(n=1, headline="Invented: port strike called off", **kw):
    return item(n, source="nl-times", access="headline-only", headline=headline, text=None, snippet=None, **kw)


# --- fake client -------------------------------------------------------------------------

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def answer(text, stop_reason="end_turn", stop_details=None, input_tokens=2000, output_tokens=300):
    content = [SimpleNamespace(type="thinking", thinking="", signature="sig")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(content=content, stop_reason=stop_reason, stop_details=stop_details,
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens))


GOOD = {
    "summary": "Dock staff at a Maasvlakte terminal plan a one-day walkout after wage talks failed.",
    "impact": "Expect no container moves at that terminal on the day; plan pickups around it.",
    "severity": "high",
    "place": "ect-delta",
    "tags": ["Containers", "Labour"],
    "strike": {"state": "announced", "location": "ECT Delta, Maasvlakte", "affects_rotterdam": True,
               "start_phrase": "5 November", "end_phrase": "5 November", "match": "new", "strike_id": None},
}


def full(**changes):
    data = json.loads(json.dumps(GOOD))
    data.update(changes)
    return answer(json.dumps(data))


def headline_answer(**changes):
    data = {"severity": "medium", "place": "none", "tags": ["Labour"], "strike": None}
    data.update(changes)
    return answer(json.dumps(data))


def strike(**changes):
    data = dict(GOOD["strike"])
    data.update(changes)
    return data


def status_error(cls, code):
    return cls("invented error detail", response=httpx2.Response(code, request=REQUEST), body=None)


class FakeMessages:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.answers:
            raise AssertionError("more API calls than the test expected")
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a


class FakeClient:
    def __init__(self, *answers):
        self.messages = FakeMessages(answers)


def run(items, *answers, known=(), **kw):
    client = FakeClient(*answers)
    result = summarise(list(items), client, known=list(known), today=TODAY, **kw)
    return result, client


def user_text(call):
    return call["messages"][-1]["content"]


KNOWN = [{"id": "strike-2026-10-30-1", "location": "ECT Delta", "start": "2026-11-05", "end": None,
          "first_headline": "Invented: union announces ECT strike"}]


# --- a valid answer maps to the item -------------------------------------------------------


def test_a_valid_answer_fills_summary_impact_severity_tags_pin_strike_and_written_by():
    result, _ = run([item()], full())
    [done] = result.items
    assert done.ai["summary"] == GOOD["summary"]
    assert done.ai["impact"] == GOOD["impact"]
    assert done.ai["severity"] == "high"
    assert done.ai["affects"] == ["Containers", "Labour", "ECT Delta"]  # place label added as location tag
    assert done.ai["map"]["label"] == "ECT Delta" and done.ai["map"]["side"] in ("left", "right")
    assert done.ai["strike"] == {"state": "announced", "location": "ECT Delta, Maasvlakte", "affects_rotterdam": True,
                                 "start": "2026-11-05", "end": "2026-11-05", "match": "new",
                                 "strike_id": "strike-2026-11-02-1"}
    assert done.ai["written_by"] == {"model": "claude-sonnet-5-5", "api": "standard"}
    assert "unlisted" not in done.ai
    assert result.failures == [] and result.unavailable is None


def test_impact_null_means_not_enough_information_and_is_accepted():
    result, _ = run([item()], full(impact=None, strike=None))
    assert result.items[0].ai["impact"] is None
    assert result.items[0].ai["severity"] == "high" and result.failures == []


def test_the_stored_record_has_the_ai_fields_but_never_the_article_text(tmp_path):
    result, _ = run([item()], full())
    record = result.items[0].record()
    for field in ("severity", "summary", "impact", "affects", "map", "strike", "written_by", "filter"):
        assert field in record
    assert ARTICLE not in json.dumps(record) and TEASER not in json.dumps(record)
    storage.write("items", TODAY, [record], data_dir=tmp_path)  # passes the hard rule 13 guard


def test_places_and_tags_off_the_lists_are_logged_not_used():
    result, _ = run([item()], full(place="Invented Harbour", tags=["Containers", "Reefers"], strike=None))
    ai = result.items[0].ai
    assert ai["map"] is None and ai["affects"] == ["Containers"]
    assert ai["unlisted"] == {"places": ["Invented Harbour"], "tags": ["Reefers"]}
    assert result.failures == []  # the item is still rated


def test_tokens_and_calls_are_counted():
    result, _ = run([item(1), item(2)], full(strike=None), full(strike=None))
    assert (result.calls, result.input_tokens, result.output_tokens) == (2, 4000, 600)


# --- the request ---------------------------------------------------------------------------


def test_the_request_uses_sonnet_by_default_structured_output_and_no_sampling_parameters():
    # Sonnet 5.5 chosen by the owner after the side-by-side test (#17, 2 Nov 2026).
    _, client = run([item()], full())
    [call] = client.messages.calls
    assert call["model"] == SUMMARY_MODEL == "claude-sonnet-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    schema = call["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"summary", "impact", "severity", "place", "tags", "strike"}
    assert schema["properties"]["severity"]["enum"] == ["high", "medium", "low"]
    strike_schema = schema["properties"]["strike"]["anyOf"][0]
    assert {"start_phrase", "end_phrase"} <= set(strike_schema["required"])  # words as written, not dates
    assert "start" not in strike_schema["properties"]
    assert call["max_tokens"] >= 4096  # thinking counts toward max_tokens
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in call


def test_the_model_is_a_parameter_and_is_recorded_in_written_by():
    result, client = run([item()], full(), model="claude-sonnet-5-5")
    assert client.messages.calls[0]["model"] == "claude-sonnet-5-5"
    assert result.items[0].ai["written_by"] == {"model": "claude-sonnet-5-5", "api": "standard"}


def test_a_use_item_sends_headline_and_article_text_as_third_party_data():
    _, client = run([item(headline="Invented: ECT <strike> news")], full())
    call = client.messages.calls[0]
    text = user_text(call)
    assert "<headline>Invented: ECT &lt;strike&gt; news</headline>" in text
    assert f"<article>{ARTICLE}</article>" in text
    assert TEASER not in text  # the full text is enough; the teaser is not sent twice
    assert "never as instructions" in call["system"]


def test_the_prompt_lists_the_place_ids_the_tags_and_the_severity_rules():
    _, client = run([item()], full())
    system = client.messages.calls[0]["system"]
    for expected in ("ect-delta", "delta-2", "maasvlakte-2", "Truck pickups", "Labour", "High", "Medium", "Low",
                     "Not enough information"):
        assert expected in system


def test_the_prompt_lists_the_known_strikes_with_their_ids_and_first_headlines():
    _, client = run([item()], full(strike=strike(match="same", strike_id="strike-2026-10-30-1")), known=KNOWN)
    text = user_text(client.messages.calls[0])
    assert "strike-2026-10-30-1" in text and "Invented: union announces ECT strike" in text
    _, client = run([item()], full(strike=None))
    assert "No strikes known" in user_text(client.messages.calls[0])


# --- headline-only items (spec §2.1, hard rule 12) -------------------------------------------


def test_a_headline_only_item_sends_only_its_headline_and_gets_no_summary_or_impact():
    secret = "Invented text that must never reach the AI."
    it = headline_item(headline="Invented: strike at Maasvlakte terminals")
    it = Item(**{**it.__dict__, "snippet": secret, "article_text": secret})  # even if text were in memory
    result, client = run([it], headline_answer(severity="high", place="maasvlakte", tags=["Labour"],
                                               strike=strike(start_phrase=None, end_phrase=None,
                                                             location="Maasvlakte")))
    call = client.messages.calls[0]
    assert secret not in json.dumps(call, default=str)
    assert "<headline>Invented: strike at Maasvlakte terminals</headline>" in user_text(call)
    assert "<article>" not in user_text(call)
    assert set(call["output_config"]["format"]["schema"]["required"]) == {"severity", "place", "tags", "strike"}
    ai = result.items[0].ai
    assert ai["summary"] is None and ai["impact"] is None
    assert ai["severity"] == "high" and ai["map"]["label"] == "Maasvlakte"
    assert ai["affects"] == ["Labour", "Maasvlakte"]
    assert ai["strike"]["start"] is None and ai["strike"]["end"] is None
    assert ai["strike"]["strike_id"] == "strike-2026-11-02-1"


def test_a_headline_that_states_no_date_cannot_get_a_strike_date():
    result, _ = run([headline_item(headline="Invented: dockers to strike next week")],
                    headline_answer(strike=strike(start_phrase="9 November", end_phrase=None)))
    ai = result.items[0].ai
    assert ai["severity"] == "medium" and ai["strike"]["start"] is None  # rated; the strike stays, no date
    assert result.failures == [{"source": "AI summariser", "error":
                                "https://nl-times.test/1: strike start date not stated in the source (left out)"}]


def test_a_vague_phrase_in_the_headline_gives_no_date_and_no_failure():
    result, _ = run([headline_item(headline="Invented: dockers to strike next week")],
                    headline_answer(strike=strike(start_phrase="next week", end_phrase=None)))
    assert result.items[0].ai["strike"]["start"] is None and result.failures == []


def test_a_use_item_without_article_text_is_rated_from_its_headline_alone():
    result, client = run([item(text=None)], headline_answer())
    text = user_text(client.messages.calls[0])
    assert "<article>" not in text and TEASER not in text
    ai = result.items[0].ai
    assert ai["severity"] == "medium" and ai["summary"] is None and ai["impact"] is None


# --- strikes: ids are assigned by the code ----------------------------------------------------


def test_new_strikes_get_ids_from_the_code_numbered_per_day_and_the_ais_own_id_is_ignored():
    known = [dict(KNOWN[0], id="strike-2026-11-02-1")]  # already taken (e.g. a manual rerun)
    result, _ = run([item(1), item(2)], full(strike=strike(strike_id="strike-made-up")), full(), known=known)
    assert [i.ai["strike"]["strike_id"] for i in result.items] == ["strike-2026-11-02-2", "strike-2026-11-02-3"]


@pytest.mark.parametrize("match", ["same", "unsure"])
def test_same_and_unsure_keep_a_known_strike_id(match):
    result, _ = run([item()], full(strike=strike(match=match, strike_id="strike-2026-10-30-1")), known=KNOWN)
    assert result.items[0].ai["strike"]["match"] == match
    assert result.items[0].ai["strike"]["strike_id"] == "strike-2026-10-30-1"


@pytest.mark.parametrize("strike_id", ["strike-2026-10-01-9", None])
@pytest.mark.parametrize("match", ["same", "unsure"])
def test_same_or_unsure_with_an_unknown_or_missing_id_makes_the_item_unrated(match, strike_id):
    result, _ = run([item()], full(strike=strike(match=match, strike_id=strike_id)), known=KNOWN)
    assert result.items[0].ai["severity"] is None
    assert result.failures[0]["error"].endswith(f"strike match '{match}' does not name a known strike")


# --- dates: the AI copies the phrase, the code works out the date ------------------------------
# Owner's decisions (2 Nov 2026): a bad date is left out (the strike stays, so it shows Watch)
# with a failure line; "today", "tomorrow" and weekdays are resolved against the published date.

MON = date(2026, 11, 2)  # the invented items are published on Monday 2 November 2026


def test_a_date_phrase_not_in_the_source_is_left_out_and_the_strike_kept():
    result, _ = run([item()], full(strike=strike(start_phrase="6 November")))
    [done] = result.items
    assert done.ai["severity"] == "high" and done.ai["summary"] == GOOD["summary"]
    assert done.ai["strike"]["start"] is None and done.ai["strike"]["end"] == "2026-11-05"
    assert done.ai["strike"]["strike_id"] == "strike-2026-11-02-1"
    assert result.failures == [{"source": "AI summariser", "error":
                                "https://ect-news.test/1: strike start date not stated in the source (left out)"}]


@pytest.mark.parametrize("bad", [20261105, ["5 November"], "x" * 81])
def test_a_date_phrase_that_is_not_short_text_is_left_out(bad):
    result, _ = run([item()], full(strike=strike(start_phrase=bad)))
    assert result.items[0].ai["severity"] == "high" and result.items[0].ai["strike"]["start"] is None
    assert result.failures[0]["error"].endswith("strike start date is not a short phrase (left out)")


def test_dates_in_the_wrong_order_are_both_left_out():
    text = ARTICLE + " A second stop on 3 November was also mentioned."
    result, _ = run([item(text=text)], full(strike=strike(start_phrase="5 November", end_phrase="3 November")))
    stored = result.items[0].ai["strike"]
    assert (stored["start"], stored["end"]) == (None, None) and result.items[0].ai["severity"] == "high"
    assert result.failures[0]["error"].endswith("strike ends before it starts (dates left out)")


def test_the_phrases_are_never_stored():
    result, _ = run([item()], full())
    assert set(result.items[0].ai["strike"]) == {"state", "location", "affects_rotterdam", "start", "end",
                                                 "match", "strike_id"}


@pytest.mark.parametrize("words, phrase, expected", [
    ("will strike tomorrow", "tomorrow", "2026-11-03"),
    ("will strike on Thursday", "on Thursday", "2026-11-05"),
    ("gaan donderdag staken", "donderdag", "2026-11-05"),
    ("are on strike today", "today", "2026-11-02"),
])
def test_relative_dates_are_resolved_against_the_published_date(words, phrase, expected):
    text = f"Invented article. Dockworkers {words}, the union said."
    result, _ = run([item(text=text)], full(strike=strike(start_phrase=phrase, end_phrase=phrase)))
    assert (result.items[0].ai["strike"]["start"], result.items[0].ai["strike"]["end"]) == (expected, expected)
    assert result.failures == []


def test_without_a_published_date_a_relative_phrase_gives_no_date_and_no_failure():
    undated = Item(**{**item(text="Invented article. Dockworkers will strike tomorrow.").__dict__, "published": None})
    result, _ = run([undated], full(strike=strike(start_phrase="tomorrow", end_phrase=None)))
    assert result.items[0].ai["strike"]["start"] is None and result.failures == []


@pytest.mark.parametrize("phrase, first, last", [
    ("5 November", "2026-11-05", "2026-11-05"),
    ("on 5th of November", "2026-11-05", "2026-11-05"),
    ("November 5", "2026-11-05", "2026-11-05"),
    ("5 november", "2026-11-05", "2026-11-05"),
    ("from 5 to 7 November", "2026-11-05", "2026-11-07"),
    ("van 5 t/m 7 november", "2026-11-05", "2026-11-07"),
    ("5, 6 and 7 November", "2026-11-05", "2026-11-07"),
    ("Thursday 5 November", "2026-11-05", "2026-11-05"),
    ("05-11-2026", "2026-11-05", "2026-11-05"),
    ("5/11", "2026-11-05", "2026-11-05"),
    ("2026-11-05", "2026-11-05", "2026-11-05"),
    ("05-11-2025", "2025-11-05", "2025-11-05"),  # a year in the source is taken as written
    ("today", "2026-11-02", "2026-11-02"),
    ("vandaag", "2026-11-02", "2026-11-02"),
    ("tonight", "2026-11-02", "2026-11-02"),
    ("tomorrow", "2026-11-03", "2026-11-03"),
    ("tomorrow morning", "2026-11-03", "2026-11-03"),
    ("morgen", "2026-11-03", "2026-11-03"),
    ("morgenochtend", "2026-11-03", "2026-11-03"),
    ("today and tomorrow", "2026-11-02", "2026-11-03"),
    ("on Thursday", "2026-11-05", "2026-11-05"),
    ("this Thursday", "2026-11-05", "2026-11-05"),
    ("aanstaande donderdag", "2026-11-05", "2026-11-05"),
    ("from Thursday to Saturday", "2026-11-05", "2026-11-07"),
    ("Sunday", "2026-11-08", "2026-11-08"),
])
def test_resolve_phrase(phrase, first, last):
    assert resolve_phrase(phrase, MON, TODAY) == (date.fromisoformat(first), date.fromisoformat(last))


@pytest.mark.parametrize("phrase", [
    "next week", "soon", "binnenkort", "later this month", "volgende week", "next Thursday",
    "volgende donderdag", "last Thursday", "Monday", "31 November", "in the coming days",
])
def test_vague_ambiguous_or_impossible_phrases_give_no_date(phrase):
    # "Monday": the item is published on a Monday, so it could mean today or next week.
    assert resolve_phrase(phrase, MON, TODAY) is None


@pytest.mark.parametrize("phrase", ["tomorrow", "Thursday", "today"])
def test_relative_phrases_need_a_published_date(phrase):
    assert resolve_phrase(phrase, None, TODAY) is None


def test_a_day_and_month_without_a_year_takes_the_nearest_year():
    assert resolve_phrase("5 January", date(2026, 12, 30), TODAY) == (date(2027, 1, 5),) * 2
    assert resolve_phrase("28 December", date(2027, 1, 2), TODAY) == (date(2026, 12, 28),) * 2
    assert resolve_phrase("5 November", None, TODAY) == (date(2026, 11, 5),) * 2  # no published date: today


@pytest.mark.parametrize("published, expected", [
    ("2026-11-02T05:00:00+01:00", MON),
    ("2026-11-01T23:30:00+00:00", MON),  # 00:30 in Amsterdam
    ("2026-11-02T00:30:00", MON),  # no timezone: Amsterdam time (as the filter reads it, §5.4)
    ("2026-11-02", MON),
    (None, None),
    ("not a date", None),
])
def test_published_day_is_the_amsterdam_date(published, expected):
    assert published_day(published) == expected


def test_phrase_in_ignores_case_and_spacing_but_needs_the_words():
    assert phrase_in("5  NOVEMBER", "Invented: a stop on 5 November.")
    assert not phrase_in("6 November", "Invented: a stop on 5 November.")
    assert not phrase_in("", "anything")


# --- every other invalid answer: unrated + failure, never a guess ------------------------------


@pytest.mark.parametrize("change, problem", [
    ({"severity": "critical"}, "unknown severity"),
    ({"severity": None}, "unknown severity"),
    ({"summary": ""}, "empty summary"),
    ({"impact": 42}, "impact is not text"),
    ({"tags": "Containers"}, "tags are not a list"),
    ({"strike": strike(state="postponed")}, "unknown strike state"),
    ({"strike": strike(match="maybe")}, "unknown strike match"),
    ({"strike": strike(affects_rotterdam="yes")}, "strike affects_rotterdam is not true/false"),
    ({"strike": strike(location="")}, "strike location missing"),
    ({"strike": "yes"}, "strike is not an object"),
])
def test_an_invalid_field_makes_the_item_unrated(change, problem):
    result, _ = run([item()], full(**change))
    assert result.items[0].ai == unrated()
    assert result.failures == [{"source": "AI summariser", "error": f"https://ect-news.test/1: {problem}"}]


# --- copied or too long: one retry asking to rephrase (owner's decision, 2 Nov 2026) -------------

COPIED = "Dockworkers at the ECT Delta terminal on the Maasvlakte will stop work on 5 November."
TOO_LONG = "word " * 80


def test_the_first_prompt_asks_for_own_words_and_warns_that_copies_are_rejected():
    _, client = run([item()], full())
    system = client.messages.calls[0]["system"]
    assert "entirely in your own words" in system and "a few words in a row" in system
    assert "rejected" in system
    assert "could not be used" not in user_text(client.messages.calls[0])  # no retry note the first time


@pytest.mark.parametrize("change, reason", [
    ({"summary": COPIED}, "summary copies the article (10+ words in a row)"),
    ({"impact": COPIED}, "impact copies the article (10+ words in a row)"),
    ({"summary": TOO_LONG}, "summary too long"),
    ({"impact": "word " * 100}, "impact too long"),
])
def test_a_copied_or_too_long_answer_is_retried_once_and_the_rephrased_answer_used(change, reason):
    result, client = run([item()], full(**change), full())
    assert len(client.messages.calls) == 2
    retry = user_text(client.messages.calls[1])
    assert "could not be used" in retry and reason in retry and "in your own words" in retry
    assert user_text(client.messages.calls[0]) in retry  # the same item, with the note added
    assert result.items[0].ai["summary"] == GOOD["summary"] and result.items[0].ai["severity"] == "high"
    assert result.failures == []
    assert (result.calls, result.input_tokens) == (2, 4000)  # both calls counted for the cost check


def test_if_the_retry_also_copies_the_item_is_unrated():
    result, client = run([item()], full(summary=COPIED), full(summary=COPIED))
    assert len(client.messages.calls) == 2
    assert result.items[0].ai == unrated()
    assert result.failures == [{"source": "AI summariser", "error":
                                "https://ect-news.test/1: summary copies the article (10+ words in a row) "
                                "(after a retry)"}]


def test_if_the_retry_fails_another_way_the_item_is_unrated_with_that_problem():
    result, _ = run([item()], full(summary=TOO_LONG), answer("{bad"))
    assert result.items[0].ai == unrated()
    assert result.failures[0]["error"] == "https://ect-news.test/1: unreadable answer (after a retry)"


def test_a_retry_that_hits_an_api_error_leaves_the_item_unrated():
    result, _ = run([item(1), item(2)], full(summary=COPIED), anthropic.APITimeoutError(request=REQUEST),
                    full(strike=None))
    assert result.items[0].ai == unrated() and result.items[1].ai["severity"] == "high"
    assert result.failures == [{"source": "AI summariser", "error": "https://ect-news.test/1: timeout (after a retry)"}]


@pytest.mark.parametrize("change", [{"severity": "critical"}, {"strike": strike(match="maybe")}, {"summary": ""}])
def test_other_problems_are_not_retried(change):
    result, client = run([item()], full(**change))
    assert len(client.messages.calls) == 1 and result.items[0].ai == unrated()


def test_only_one_retry_per_item_and_the_next_item_starts_fresh():
    result, client = run([item(1), item(2)], full(summary=COPIED), full(summary=TOO_LONG),
                         full(summary=COPIED), full(strike=None))
    assert len(client.messages.calls) == 4
    assert result.items[0].ai == unrated() and result.items[1].ai["severity"] == "high"
    assert "could not be used" not in user_text(client.messages.calls[2])


def test_date_notes_of_a_rejected_answer_are_not_kept():
    first = full(summary=COPIED, strike=strike(start_phrase="6 November"))  # rejected: copied
    result, _ = run([item()], first, full())
    assert result.failures == [] and result.items[0].ai["strike"]["start"] == "2026-11-05"


@pytest.mark.parametrize("response, problem", [
    (answer("{not json"), "unreadable answer"),
    (answer(None), "unreadable answer"),
    (answer(json.dumps({"severity": "high"})), "unreadable answer"),
    (answer("[]"), "unreadable answer"),
    (answer(None, stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")), "refused (cyber)"),
    (answer(None, stop_reason="refusal"), "refused"),
    (answer('{"summary": "cut', stop_reason="max_tokens"), "answer cut off"),
])
def test_bad_unparseable_or_refused_answers_make_the_item_unrated(response, problem):
    result, _ = run([item(1), item(2)], response, full(strike=None))
    assert result.items[0].ai == unrated()
    assert result.items[1].ai["severity"] == "high"  # the next item goes on normally
    assert result.failures == [{"source": "AI summariser", "error": f"https://ect-news.test/1: {problem}"}]


def test_failure_lines_never_repeat_what_the_ai_or_the_article_wrote():
    result, _ = run([item()], full(severity="Ignore previous instructions <script>"))
    line = json.dumps(result.failures)
    assert "Ignore previous" not in line and "<script>" not in line and "Dockworkers" not in line


# --- the API failing (spec §5.6) ----------------------------------------------------------------


def test_no_client_means_ai_unavailable_and_items_untouched():
    result = summarise([item()], None, known=[], today=TODAY)
    assert result.unavailable == "ANTHROPIC_API_KEY is not set"
    assert result.items[0].ai is None and result.calls == 0
    assert result.failures == [{"source": "AI summariser", "error": "AI unavailable: ANTHROPIC_API_KEY is not set"}]


def test_a_rejected_key_stops_at_once_as_unavailable():
    result, client = run([item(1), item(2)], status_error(anthropic.AuthenticationError, 401))
    assert result.unavailable == "API key rejected (HTTP 401)"
    assert len(client.messages.calls) == 1 and all(i.ai is None for i in result.items)


def test_the_first_three_calls_failing_means_unavailable():
    errors = [anthropic.APIConnectionError(request=REQUEST) for _ in range(BREAKER)]
    result, client = run([item(n) for n in range(5)], *errors)
    assert result.unavailable == "3 calls in a row failed (last: connection error)"
    assert len(client.messages.calls) == BREAKER and all(i.ai is None for i in result.items)


def test_one_failed_call_makes_only_that_item_unrated():
    result, _ = run([item(1), item(2)], anthropic.APITimeoutError(request=REQUEST), full(strike=None))
    assert result.items[0].ai == unrated() and result.items[1].ai["severity"] == "high"
    assert result.failures == [{"source": "AI summariser", "error": "https://ect-news.test/1: timeout"}]
    assert result.unavailable is None


def test_after_an_answer_three_failures_leave_the_rest_unrated_without_more_calls():
    errors = [status_error(anthropic.InternalServerError, 529) for _ in range(BREAKER)]
    result, client = run([item(n) for n in range(6)], full(strike=None), *errors)
    assert result.unavailable is None
    assert len(client.messages.calls) == 1 + BREAKER
    assert [i.ai["severity"] for i in result.items] == ["high", None, None, None, None, None]
    assert result.failures[-1]["error"] == "https://ect-news.test/5: not tried: 3 calls in a row failed"


def test_refusals_do_not_count_as_an_outage():
    refusal = answer(None, stop_reason="refusal")
    result, _ = run([item(n) for n in range(4)], refusal, refusal, refusal, full(strike=None))
    assert result.unavailable is None and result.items[3].ai["severity"] == "high"


# --- known strikes from stored items -------------------------------------------------------


def stored(day, *records):
    return (day, list(records))


def record(headline, strike_id, location="Maasvlakte", start=None, end=None, state="announced"):
    return {"headline": headline, "url": "https://x.test/" + headline,
            "strike": {"state": state, "location": location, "affects_rotterdam": True, "start": start,
                       "end": end, "match": "new", "strike_id": strike_id}}


def test_known_strikes_take_the_first_headline_and_the_newest_details():
    days = [  # newest first, as storage.read_recent returns them
        stored(date(2026, 11, 1), record("Second report", "strike-2026-10-30-1", location="ECT Delta",
                                         start="2026-11-05")),
        stored(date(2026, 10, 30), record("First report", "strike-2026-10-30-1"),
               {"headline": "Not a strike", "strike": None}, {"headline": "Unrated"}),
    ]
    assert known_strikes(days) == [{"id": "strike-2026-10-30-1", "location": "ECT Delta", "start": "2026-11-05",
                                    "end": None, "first_headline": "First report"}]


def test_known_strikes_are_listed_oldest_first_and_skip_items_without_an_id():
    days = [stored(date(2026, 11, 1), record("B", "strike-2026-11-01-1"), record("C", None)),
            stored(date(2026, 10, 25), record("A", "strike-2026-10-25-1"))]
    assert [s["id"] for s in known_strikes(days)] == ["strike-2026-10-25-1", "strike-2026-11-01-1"]


# --- the brief item shape (spec §6) ----------------------------------------------------------


BRIEF_ITEM_KEYS = {"severity", "headline", "url", "source", "language", "published", "summary", "impact",
                   "affects", "access", "written_by", "map", "strike"}


def test_a_rated_item_maps_to_the_brief_item_shape():
    result, _ = run([item()], full())
    shaped = brief_item(result.items[0], SOURCES)
    assert set(shaped) == BRIEF_ITEM_KEYS
    assert shaped["source"] == "ECT news"  # the source's name, as the page shows it
    assert shaped["severity"] == "high" and shaped["access"] == "full"
    assert shaped["map"] == result.items[0].ai["map"]


def test_an_unrated_or_never_summarised_item_maps_to_an_unrated_brief_item():
    for it in (item(), Item(**{**item().__dict__, "ai": unrated()})):
        shaped = brief_item(it, SOURCES)
        assert set(shaped) == BRIEF_ITEM_KEYS
        assert (shaped["severity"], shaped["summary"], shaped["impact"], shaped["written_by"]) == (None,) * 4


def test_brief_items_from_the_summariser_render(tmp_path):
    result, _ = run([item(1), headline_item(2), item(3)],
                    full(), headline_answer(), answer("{bad"))
    brief = {"date": "2026-11-02", "sample": False, "built_at": "2026-11-02T06:52:00+01:00", "corrections": [],
             "status": [], "items": [brief_item(i, SOURCES) for i in result.items],
             "build": {"sources_checked": 2, "items_collected": 3, "items_kept": 3, "failures": result.failures},
             "ships": None}
    storage.write("briefs", TODAY, brief, data_dir=tmp_path)
    assert render_site(tmp_path / "briefs", tmp_path / "site") >= 1
    page = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert GOOD["summary"] in page and "Invented: port strike called off" in page
