"""Relevance filter, stage 2: the AI check (spec §5.4, §5.6, hard rule 12; issue #13).

A fake Anthropic client returns made-up answers or raises the SDK's real error classes; no
test calls the API or touches the network. Headlines and teasers are invented (hard rule 13).
"""

import json
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from haven.clock import AMSTERDAM
from haven.config import FilterConfig, Source
from haven.feeds import Item
from haven.filter import (
    AI_MODEL,
    BREAKER,
    ai_client,
    check_with_ai,
    format_report,
    run_filter,
)

RUN = datetime(2026, 11, 1, 6, 45, tzinfo=AMSTERDAM)
FAKE_KEY = "fake-key-for-tests-0000"
TEASER = "Invented teaser: the terminal stops loading for two days."

PORT = Source(id="port-authority-news", name="Port of Rotterdam Authority news", verdict="use",
              urls=("https://port.test/",), access="html", language="en", auto_keep=True)
PIN = Source(id="pin-notices", name="PIN notices to shipping", verdict="use",
             urls=("https://pin.test/rss",), access="rss", language="en")
RIJNMOND = Source(id="rtv-rijnmond", name="RTV Rijnmond", verdict="headline-only",
                  urls=("https://rijnmond.test/rss",), access="rss", language="nl")
SOURCES = (PORT, PIN, RIJNMOND)


def item(n=1, source="pin-notices", access="full", snippet=TEASER, headline=None, published="2026-11-01T05:00:00+01:00",
         language="en"):
    return Item(source=source, headline=headline or f"Invented notice number {n}", url=f"https://{source}.test/{n}",
                published=published, language=language, access=access, snippet=snippet)


# --- fake client -------------------------------------------------------------------------

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def answer(text, stop_reason="end_turn", stop_details=None, input_tokens=300, output_tokens=40):
    content = [SimpleNamespace(type="thinking", thinking="", signature="sig")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(content=content, stop_reason=stop_reason, stop_details=stop_details,
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens))


def verdict(kept, reason="Invented reason."):
    return answer(json.dumps({"kept": kept, "reason": reason}))


def status_error(cls, code, message="invented error detail"):
    return cls(message, response=httpx2.Response(code, request=REQUEST), body=None)


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


def request_text(call):
    """Everything the request sends, as one string (to check what reached the AI)."""
    return json.dumps(call, default=str)


# --- valid answers -----------------------------------------------------------------------


def test_valid_answers_are_recorded_as_ai_decisions_in_input_order():
    client = FakeClient(verdict(True, "Fog procedure limits traffic for all ships."),
                        verdict(False, "Routine buoy change, no effect on traffic."))
    result = check_with_ai([item(1), item(2)], client)
    assert [i.url for i in result.items] == ["https://pin-notices.test/1", "https://pin-notices.test/2"]
    assert result.items[0].filter == {"kept": True, "stage": "ai", "reason": "Fog procedure limits traffic for all ships."}
    assert result.items[1].filter == {"kept": False, "stage": "ai", "reason": "Routine buoy change, no effect on traffic."}
    assert result.failures == [] and result.unavailable is None
    assert result.items[0].snippet == TEASER  # still in memory, never in the record
    assert TEASER not in json.dumps(result.items[0].record())


def test_the_request_uses_haiku_low_effort_structured_output_and_no_sampling_parameters():
    client = FakeClient(verdict(True))
    check_with_ai([item()], client)
    [call] = client.messages.calls
    assert call["model"] == AI_MODEL == "claude-haiku-5-5"
    assert call["output_config"]["effort"] == "low"
    schema = call["output_config"]["format"]["schema"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert schema["properties"]["kept"] == {"type": "boolean"}
    assert schema["properties"]["reason"]["type"] == "string"
    assert schema["required"] == ["kept", "reason"] and schema["additionalProperties"] is False
    assert call["max_tokens"] >= 1024  # thinking counts toward max_tokens on Haiku 5.5
    for banned in ("temperature", "top_p", "top_k", "thinking", "fallbacks"):
        assert banned not in call  # 400 on Haiku 5.5 / no server-side fallback for Haiku
    assert call["messages"][-1]["role"] == "user"
    assert "Port of Rotterdam" in call["system"]


def test_tokens_are_counted_for_the_cost_check():
    client = FakeClient(verdict(True), verdict(False))
    result = check_with_ai([item(1), item(2)], client)
    assert (result.input_tokens, result.output_tokens, result.calls) == (600, 80, 2)


# --- what is sent (hard rule 12) -----------------------------------------------------------


def test_a_use_item_sends_headline_and_teaser_as_data():
    client = FakeClient(verdict(True))
    check_with_ai([item(headline="Invented: terminal closed for repairs")], client)
    text = client.messages.calls[0]["messages"][-1]["content"]
    assert "<headline>Invented: terminal closed for repairs</headline>" in text
    assert f"<teaser>{TEASER}</teaser>" in text


def test_a_headline_only_item_sends_no_teaser_even_if_one_is_in_memory():
    client = FakeClient(verdict(False))
    headline_only = item(source="rtv-rijnmond", access="headline-only", language="nl",
                         headline="Verzonnen kop over de haven")
    check_with_ai([headline_only], client)
    sent = request_text(client.messages.calls[0])
    assert "Verzonnen kop over de haven" in sent
    assert TEASER not in sent
    assert "<teaser>" not in client.messages.calls[0]["messages"][-1]["content"]


def test_a_use_item_without_a_teaser_sends_the_headline_only():
    client = FakeClient(verdict(True))
    check_with_ai([item(snippet=None)], client)
    assert "<teaser>" not in client.messages.calls[0]["messages"][-1]["content"]


# --- one item fails: kept, with a failure line ---------------------------------------------


@pytest.mark.parametrize("bad, problem", [
    (answer("not json at all"), "unreadable answer"),
    (answer(json.dumps({"kept": True})), "unreadable answer"),                       # reason missing
    (answer(json.dumps({"kept": "yes", "reason": "Invented."})), "unreadable answer"),  # wrong type
    (answer(json.dumps({"kept": True, "reason": "   "})), "unreadable answer"),        # empty reason
    (answer(None), "unreadable answer"),                                              # thinking only
    (answer(None, stop_reason="max_tokens"), "answer cut off"),
    (answer(None, stop_reason="refusal", stop_details=SimpleNamespace(category="general_harms", explanation="x")),
     "refused (general_harms)"),
    (anthropic.APITimeoutError(request=REQUEST), "timeout"),
    (anthropic.APIConnectionError(request=REQUEST), "connection error"),
    (status_error(anthropic.InternalServerError, 529), "HTTP 529"),
    (status_error(anthropic.RateLimitError, 429), "HTTP 429"),
    (ValueError("invented bug"), "unexpected error (ValueError)"),
])
def test_one_failed_item_is_kept_with_a_reason_and_a_failure_line_and_the_others_go_on(bad, problem):
    client = FakeClient(verdict(False, "Invented: not port related."), bad, verdict(True, "Invented: port related."))
    result = check_with_ai([item(1), item(2), item(3)], client)
    first, failed, third = result.items
    assert first.filter["kept"] is False and third.filter["kept"] is True
    assert failed.filter == {"kept": True, "stage": "ai", "reason": f"AI check failed ({problem}); kept to be safe"}
    assert result.failures == [{"source": "AI relevance check", "error": f"https://pin-notices.test/2: {problem}"}]
    assert result.unavailable is None


def test_a_long_or_multi_line_reason_is_made_one_short_line():
    client = FakeClient(verdict(True, "Line one\nline two " + "x" * 400))
    reason = check_with_ai([item()], client).items[0].filter["reason"]
    assert "\n" not in reason and len(reason) <= 200 and reason.startswith("Line one line two")


def test_error_messages_from_the_api_are_not_copied_into_failures():
    # The failure line names the kind of error only, so nothing the API echoes can leak.
    client = FakeClient(status_error(anthropic.InternalServerError, 500, message=f"detail {FAKE_KEY}"), verdict(True))
    result = check_with_ai([item(1), item(2)], client)
    assert FAKE_KEY not in json.dumps(result.failures) + json.dumps([i.filter for i in result.items])


# --- the whole AI is unavailable (spec §5.6) -----------------------------------------------


def test_no_key_means_ai_unavailable_and_no_call():
    assert ai_client(environ={}) is None
    assert ai_client(environ={"ANTHROPIC_API_KEY": ""}) is None
    result = check_with_ai([item(1), item(2)], None)
    assert result.unavailable == "ANTHROPIC_API_KEY is not set"
    assert [i.filter for i in result.items] == [None, None]  # nothing decided; the runner (#22) chooses
    assert result.calls == 0


def test_the_client_takes_the_key_from_anthropic_api_key_only():
    client = ai_client(environ={"ANTHROPIC_API_KEY": FAKE_KEY, "ANTHROPIC_AUTH_TOKEN": "other"})
    assert isinstance(client, anthropic.Anthropic)
    assert client.api_key == FAKE_KEY
    assert client.timeout == 30.0


@pytest.mark.parametrize("error", [
    status_error(anthropic.AuthenticationError, 401),
    status_error(anthropic.PermissionDeniedError, 403),
])
def test_a_rejected_key_stops_at_once(error):
    client = FakeClient(error)
    result = check_with_ai([item(1), item(2), item(3)], client)
    assert len(client.messages.calls) == 1
    assert result.unavailable.startswith("API key rejected (HTTP 4")
    assert [i.filter for i in result.items] == [None, None, None]


def test_failing_calls_in_a_row_at_the_start_mean_ai_unavailable():
    client = FakeClient(*[anthropic.APIConnectionError(request=REQUEST)] * BREAKER)
    result = check_with_ai([item(n) for n in range(1, 8)], client)
    assert len(client.messages.calls) == BREAKER == 3  # the other items are not tried
    assert result.unavailable == "3 calls in a row failed (last: connection error)"
    assert all(i.filter is None for i in result.items)
    assert {"source": "AI relevance check", "error": "AI unavailable: 3 calls in a row failed (last: connection error)"} \
        in result.failures


def test_an_outage_after_a_success_keeps_the_rest_without_calling():
    client = FakeClient(verdict(False), *[anthropic.APITimeoutError(request=REQUEST)] * BREAKER)
    result = check_with_ai([item(n) for n in range(1, 7)], client)
    assert len(client.messages.calls) == 1 + BREAKER
    assert result.unavailable is None  # the AI worked this morning; the brief isn't a reduced one
    assert result.items[0].filter["kept"] is False
    assert all(i.filter["kept"] is True and i.filter["reason"].startswith("AI check failed") for i in result.items[1:])
    assert result.items[-1].filter["reason"] == "AI check failed (not tried: 3 calls in a row failed); kept to be safe"


def test_a_bad_answer_does_not_count_toward_the_outage():
    # Malformed answers and refusals mean the API is up: they never make the AI "unavailable".
    client = FakeClient(*[answer("not json")] * (BREAKER + 1))
    result = check_with_ai([item(n) for n in range(1, BREAKER + 2)], client)
    assert result.unavailable is None and len(client.messages.calls) == BREAKER + 1


# --- both stages together ------------------------------------------------------------------


def test_run_filter_sends_only_undecided_items_to_the_ai_and_keeps_input_order():
    items = [
        item(1, source="port-authority-news"),                                   # auto-keep
        item(2, published="2026-10-20T08:00:00+01:00"),                           # too old
        item(3),                                                                  # to the AI
        item(4, source="rtv-rijnmond", access="headline-only", language="nl"),    # to the AI
    ]
    client = FakeClient(verdict(True, "Invented: port related."), verdict(False, "Invented: city news."))
    result = run_filter(items, SOURCES, FilterConfig(off_topic={}), RUN, client)
    assert [i.url for i in result.items] == [i.url for i in items]
    assert [(i.filter["kept"], i.filter["stage"]) for i in result.items] == [
        (True, "rules"), (False, "rules"), (True, "ai"), (False, "ai")]
    assert len(client.messages.calls) == 2
    assert result.ai_unavailable is False


def test_run_filter_reports_an_ai_outage_and_leaves_ai_items_undecided():
    items = [item(1, source="port-authority-news"), item(2)]
    result = run_filter(items, SOURCES, FilterConfig(off_topic={}), RUN, None)
    assert result.ai_unavailable is True
    assert result.items[0].filter["kept"] is True and result.items[1].filter is None


def test_run_filter_makes_no_call_when_the_rules_decide_everything():
    client = FakeClient()
    result = run_filter([item(1, source="port-authority-news")], SOURCES, FilterConfig(off_topic={}), RUN, client)
    assert client.messages.calls == [] and result.ai_unavailable is False


# --- the report ------------------------------------------------------------------------------


def test_the_report_lists_kept_then_dropped_then_unchecked_with_stage_and_reason():
    items = [
        item(1, headline="Invented dropped headline"),
        item(2, headline="Invented kept headline"),
        item(3, headline="Invented unchecked headline"),
    ]
    items[0] = replace(items[0], filter={"kept": False, "stage": "rules", "reason": "older than 48 h"})
    items[1] = replace(items[1], filter={"kept": True, "stage": "ai", "reason": "Invented: fog."})
    report = format_report(items)
    lines = report.splitlines()
    kept = next(n for n, line in enumerate(lines) if "Invented kept headline" in line)
    dropped = next(n for n, line in enumerate(lines) if "Invented dropped headline" in line)
    unchecked = next(n for n, line in enumerate(lines) if "Invented unchecked headline" in line)
    assert kept < dropped < unchecked
    assert "ai" in lines[kept] and "Invented: fog." in lines[kept]
    assert "rules" in lines[dropped] and "older than 48 h" in lines[dropped]
    assert "1 kept, 1 dropped, 1 not checked" in report


def test_report_lines_stay_readable_in_a_terminal():
    long = item(headline="Invented " + "very long headline " * 20)
    long = replace(long, filter={"kept": True, "stage": "ai", "reason": "Invented " + "r" * 190})
    assert all(len(line) <= 160 for line in format_report([long]).splitlines())
