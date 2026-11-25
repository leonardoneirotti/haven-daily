"""What a summary costs, and why an item leaves the batch (issue #143).

The 25 Nov 2026 run looked like two standard Sonnet calls of ~30,000 input tokens each. They were
~5,065 each: `ai_usage.summariser.input_tokens` counts every summariser token, batch included.
The two items had a batch answer that failed a check allowing one rephrase retry, which goes to
the same model through the standard API (§5.5), and nothing recorded which check. So:

- every route (batch, rephrase retry, fallback) sends the same request, with the article text
  capped at ARTICLE_TEXT_MAX by the summariser itself, whatever the collector passed;
- `written_by.why` says why an item was written outside the batch;
- the stored usage has the standard API's own tokens next to the batch's, so the cost is read right.
"""

import re

import pytest

from haven import run as haven_run
from haven.feeds import ARTICLE_TEXT_MAX
from haven.summarise import FALLBACK_MODEL, SUMMARY_MODEL, SummaryResult, _request, system_prompt
from haven.config import load_places, load_tag_list
from test_summarise import COPIED, READ_AT, TODAY, full, item, user_text
from test_summarise_batch import NEVER, no_answer, run_batch, succeeded

SONNET = SUMMARY_MODEL


def article_of(text: str) -> str:
    return re.search(r"<article>(.*?)</article>", text, re.S).group(1)


# --- the same input on every route ------------------------------------------------------------------


def test_the_summariser_caps_the_article_text_itself():
    long = item(1, text="Invented sentence about a terminal. " * 1000)  # ~36,000 characters
    request = _request(long, SONNET, system_prompt(load_places(), load_tag_list()), [], TODAY, READ_AT)
    assert len(article_of(user_text(request))) <= ARTICLE_TEXT_MAX


def test_a_long_article_costs_the_same_in_the_batch_and_in_the_retry():
    long = item(1, text="Invented sentence about a terminal. " * 1000)
    _, client, batches, _ = run_batch([long], full(strike=None), model=SONNET,
                                      results={0: succeeded(full(summary=COPIED, strike=None))})
    batch_text = user_text(batches.created[0][0]["params"])
    [retry] = client.messages.calls
    retry_text = user_text(retry)
    assert retry_text.startswith(batch_text)  # the same request, plus the retry note at the end
    assert len(retry_text) - len(batch_text) < 400
    assert retry["system"] == batches.created[0][0]["params"]["system"]
    assert len(article_of(batch_text)) <= ARTICLE_TEXT_MAX


def test_the_fallback_sends_the_batch_request_with_the_backup_model():
    long = item(1, text="Invented sentence about a terminal. " * 1000)
    _, client, batches, _ = run_batch([long], full(strike=None), model=SONNET, ends_at=NEVER)
    [call] = client.messages.calls
    assert call == {**batches.created[0][0]["params"], "model": FALLBACK_MODEL}


# --- why an item was written outside the batch -----------------------------------------------------------


def test_a_batch_answer_written_in_the_batch_has_no_reason():
    result, *_ = run_batch([item(1)], results={0: succeeded(full(strike=None))})
    assert "why" not in result.items[0].ai["written_by"]


def test_a_rephrase_retry_says_which_check_asked_for_it():
    result, *_ = run_batch([item(1)], full(strike=None), model=SONNET,
                           results={0: succeeded(full(summary=COPIED, strike=None))})
    written = result.items[0].ai["written_by"]
    assert written["model"] == SONNET and written["api"] == "standard"
    assert written["why"].startswith("rephrase retry: ")
    assert "words in a row" in written["why"]


@pytest.mark.parametrize("kind", ["errored", "expired", "canceled"])
def test_an_item_the_batch_did_not_answer_says_how(kind):
    result, *_ = run_batch([item(1)], full(strike=None), results={0: no_answer(kind)})
    written = result.items[0].ai["written_by"]
    assert written == {"model": FALLBACK_MODEL, "api": "standard", "why": f"not answered by the batch ({kind})"}


def test_an_unfinished_batch_says_so():
    result, *_ = run_batch([item(1)], full(strike=None), ends_at=NEVER)
    assert result.items[0].ai["written_by"]["why"] == "not answered by the batch (canceled)"


def test_a_batch_that_could_not_be_created_says_so():
    import anthropic
    from test_summarise import REQUEST
    import httpx2
    error = anthropic.InternalServerError("invented", response=httpx2.Response(500, request=REQUEST), body=None)
    result, *_ = run_batch([item(1)], full(strike=None), create_error=error)
    assert result.items[0].ai["written_by"]["why"] == "the batch could not be created"


# --- tokens: the standard API's own share -------------------------------------------------------------------


def test_the_result_has_the_standard_apis_own_tokens():
    result, *_ = run_batch([item(1), item(2)], full(strike=None),
                           results={0: succeeded(full(strike=None)), 1: no_answer("errored")})
    assert result.standard_input_tokens == result.input_tokens - result.batch_input_tokens > 0
    assert result.standard_output_tokens == result.output_tokens - result.batch_output_tokens > 0


def test_the_stored_usage_names_both_routes():
    summary = SummaryResult(items=[], failures=[], unavailable=None, calls=2, input_tokens=59_693,
                            output_tokens=1_823, batch_input_tokens=49_564, batch_output_tokens=1_449)
    from haven.filter import FilterResult
    usage = haven_run._usage(FilterResult(items=[], failures=[], ai_unavailable=False), summary)["summariser"]
    assert usage["standard_input_tokens"] == 10_129 and usage["standard_output_tokens"] == 374
    assert usage["batch_input_tokens"] == 49_564 and usage["input_tokens"] == 59_693  # unchanged meaning


def test_the_run_prints_each_route_and_why_an_item_left_the_batch():
    source = (haven_run.__file__ and open(haven_run.__file__, encoding="utf-8").read())
    assert "standard_input_tokens" in source and "batch_input_tokens" in source
    assert '["why"]' in source or "['why']" in source
