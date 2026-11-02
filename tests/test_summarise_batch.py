"""Summariser through the Batch API, with a 20-minute limit and the Haiku fallback (spec §5.5; issue #16).

A fake batch client and a fake clock: no test calls the API, touches the network or really
waits (`time.sleep` is made to fail). The helpers (items, answers, the fake Messages client)
come from test_summarise.py, so both files test the same item shapes and checks.

Two kinds of "fallback" must not be confused (owner's decision in #15, spec §5.5 point 8):
- **no answer** from the batch (not finished in 20 minutes, cancelled, expired, errored)
  = the item goes through the standard API with Haiku 5.5 (this issue);
- **an answer** from the batch that can't be used (a refusal, a bad answer) = the item is
  unrated, and no other model is asked.
"""

import time
from types import SimpleNamespace

import anthropic
import pytest

from haven.summarise import (
    BATCH_WAIT,
    CANCEL_WAIT,
    FALLBACK_MODEL,
    SUMMARY_MODEL,
    finish_batch,
    start_batch,
    summarise,
    summarise_batch,
    unrated,
)
from test_summarise import (
    COPIED,
    REQUEST,
    TODAY,
    FakeClient,
    FakeMessages,
    answer,
    full,
    headline_answer,
    headline_item,
    item,
    status_error,
    strike,
    user_text,
)

SONNET = "claude-sonnet-5-5"
NEVER = None  # the batch never ends by itself / a cancel never takes effect


@pytest.fixture(autouse=True)
def no_real_waiting(monkeypatch):
    def refuse(seconds):
        raise AssertionError(f"a test really waited ({seconds} s); use the fake clock")
    monkeypatch.setattr(time, "sleep", refuse)


# --- fakes ---------------------------------------------------------------------------------


class Clock:
    """Seconds since the start of the test; `sleep` only moves the clock on."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert seconds > 0
        self.sleeps.append(seconds)
        self.now += seconds


def succeeded(response):
    return SimpleNamespace(type="succeeded", message=response)


def no_answer(kind):  # "errored", "expired" or "canceled"
    return SimpleNamespace(type=kind)


class FakeBatches:
    """`results`: {item index: result} for the requests the batch has finished.

    `ends_at`: seconds after creation when the batch ends by itself (NEVER = keeps running).
    `cancel_takes`: seconds from cancel() until it has ended (NEVER = stays "canceling").
    Requests without a result when the batch ends are "canceled". Results come back in
    reverse order, because the real API returns them in any order.
    """

    def __init__(self, clock, results=None, ends_at=60, cancel_takes=5, create_error=None,
                 retrieve_errors=(), results_error=None):
        self.clock = clock
        self.by_index = results or {}
        self.ends_at = ends_at
        self.cancel_takes = cancel_takes
        self.create_error = create_error
        self.retrieve_errors = list(retrieve_errors)
        self.results_error = results_error
        self.created = []
        self.created_at = None
        self.cancelled_at = None
        self.n = 0

    def create(self, requests):
        self.created.append(list(requests))
        if self.create_error is not None:
            raise self.create_error
        self.created_at, self.n = self.clock(), len(self.created[-1])
        return SimpleNamespace(id="msgbatch_test", processing_status="in_progress")

    def ended(self):
        if self.ends_at is not None and self.clock() - self.created_at >= self.ends_at:
            return True
        return (self.cancelled_at is not None and self.cancel_takes is not None
                and self.clock() >= self.cancelled_at + self.cancel_takes)

    def retrieve(self, batch_id):
        assert batch_id == "msgbatch_test"
        if self.retrieve_errors:
            raise self.retrieve_errors.pop(0)
        status = "ended" if self.ended() else "canceling" if self.cancelled_at is not None else "in_progress"
        return SimpleNamespace(id=batch_id, processing_status=status)

    def cancel(self, batch_id):
        assert batch_id == "msgbatch_test" and not self.ended()
        self.cancelled_at = self.clock()
        return SimpleNamespace(id=batch_id, processing_status="canceling")

    def results(self, batch_id):
        assert batch_id == "msgbatch_test"
        assert self.ended(), "the real API has no results before the batch has ended"
        if self.results_error is not None:
            raise self.results_error
        out = [SimpleNamespace(custom_id=f"item-{i}", result=self.by_index.get(i, no_answer("canceled")))
               for i in range(self.n)]
        return iter(reversed(out))


class BatchClient:
    def __init__(self, batches, *answers):
        self.messages = FakeMessages(answers)  # the standard API (fallback and rephrase retries)
        self.messages.batches = batches


def run_batch(items, *answers, known=(), model=SUMMARY_MODEL, **batch_kw):
    clock = Clock()
    batches = FakeBatches(clock, **batch_kw)
    client = BatchClient(batches, *answers)
    result = summarise_batch(list(items), client, known=list(known), today=TODAY, model=model,
                             clock=clock, sleep=clock.sleep)
    return result, client, batches, clock


def written_by(result):
    return [i.ai["written_by"] for i in result.items]


BATCH = {"model": SUMMARY_MODEL, "api": "batch"}
HAIKU_STANDARD = {"model": FALLBACK_MODEL, "api": "standard"}


def test_the_limits_are_the_specs():
    assert BATCH_WAIT == 20 * 60
    assert FALLBACK_MODEL == "claude-haiku-5-5"
    assert 0 < CANCEL_WAIT <= 5 * 60  # the page still publishes around 07:05 (§5.5 step 4)


# --- batch finished in time ----------------------------------------------------------------


def test_a_batch_finished_in_time_writes_every_item_and_nothing_falls_back():
    items = [item(1), headline_item(2), item(3)]
    result, client, batches, clock = run_batch(
        items, ends_at=4 * 60,
        results={0: succeeded(full(strike=None)), 1: succeeded(headline_answer()), 2: succeeded(full(strike=None))})
    assert written_by(result) == [BATCH] * 3
    assert result.summaries == {"batch": 3, "fallback": 0}
    assert result.items[0].ai["severity"] == "high" and result.items[1].ai["severity"] == "medium"
    assert client.messages.calls == [] and batches.cancelled_at is None
    assert result.failures == [] and result.unavailable is None
    assert 4 * 60 <= clock.now < 5 * 60  # stopped waiting soon after the batch ended


def test_the_batch_holds_one_request_per_item_identical_to_the_standard_request():
    items = [item(1), headline_item(2)]
    standard = FakeClient(full(strike=None), headline_answer())
    summarise(items, standard, known=[], today=TODAY, model=SONNET)
    _, _, batches, _ = run_batch(items, model=SONNET,
                                 results={0: succeeded(full(strike=None)), 1: succeeded(headline_answer())})
    [requests] = batches.created
    assert [r["custom_id"] for r in requests] == ["item-0", "item-1"]
    assert [r["params"] for r in requests] == standard.messages.calls  # same prompt, model, schema
    assert "<article>" not in user_text(requests[1]["params"])  # headline-only stays headline-only


def test_results_are_matched_by_custom_id_never_by_position():
    items = [item(1), item(2), item(3)]
    result, *_ = run_batch(items, results={0: succeeded(full(severity="low", strike=None)),
                                           1: succeeded(full(severity="medium", strike=None)),
                                           2: succeeded(full(severity="high", strike=None))})
    assert [i.ai["severity"] for i in result.items] == ["low", "medium", "high"]
    assert [i.url for i in result.items] == [i.url for i in items]  # input order kept


# --- partly done at 20 minutes ---------------------------------------------------------------


def test_unfinished_items_are_cancelled_at_20_minutes_and_go_to_haiku_standard_whatever_the_batch_model():
    items = [item(1), item(2), item(3)]
    result, client, batches, clock = run_batch(
        items, full(strike=None), full(strike=None), model=SONNET, ends_at=NEVER,
        results={1: succeeded(full(strike=None))})
    assert batches.cancelled_at == BATCH_WAIT  # waited exactly 20 minutes, then cancelled
    assert [call["model"] for call in client.messages.calls] == [FALLBACK_MODEL, FALLBACK_MODEL]
    assert written_by(result) == [HAIKU_STANDARD, {"model": SONNET, "api": "batch"}, HAIKU_STANDARD]
    assert result.summaries == {"batch": 1, "fallback": 2}
    assert result.failures == []  # a slow batch is not a failure; build.summaries shows it
    assert clock.now <= BATCH_WAIT + CANCEL_WAIT


def test_the_fallback_sends_the_same_item_but_names_the_haiku_model():
    _, client, batches, _ = run_batch([item(1)], full(strike=None), model=SONNET, ends_at=NEVER)
    batch_params = batches.created[0][0]["params"]
    [call] = client.messages.calls
    assert call == {**batch_params, "model": FALLBACK_MODEL}


@pytest.mark.parametrize("kind", ["errored", "expired", "canceled"])
def test_a_request_the_batch_did_not_answer_goes_to_the_fallback(kind):
    result, client, batches, _ = run_batch([item(1), item(2)], full(strike=None),
                                           results={0: no_answer(kind), 1: succeeded(full(strike=None))})
    assert batches.cancelled_at is None  # the batch ended by itself
    assert written_by(result) == [HAIKU_STANDARD, BATCH]
    assert len(client.messages.calls) == 1


def test_the_wait_counts_from_the_batch_start_so_another_step_can_run_meanwhile():
    clock = Clock()
    batches = FakeBatches(clock, ends_at=NEVER, results={0: succeeded(full(strike=None))})
    client = BatchClient(batches, full(strike=None))
    run = start_batch([item(1), item(2)], client, known=[], today=TODAY, clock=clock)
    clock.now += 15 * 60  # e.g. the AIS snapshot (#31) runs during the wait
    result = finish_batch(run, sleep=clock.sleep)
    assert batches.cancelled_at == BATCH_WAIT  # not 15 + 20 minutes
    assert sum(clock.sleeps) <= 5 * 60 + CANCEL_WAIT
    assert result.summaries == {"batch": 1, "fallback": 1}


def test_if_the_batch_ended_during_the_other_step_finishing_does_not_wait():
    clock = Clock()
    batches = FakeBatches(clock, ends_at=5 * 60, results={0: succeeded(full(strike=None))})
    run = start_batch([item(1)], BatchClient(batches), known=[], today=TODAY, clock=clock)
    clock.now += 12 * 60
    result = finish_batch(run, sleep=clock.sleep)
    assert clock.sleeps == [] and written_by(result) == [BATCH]


def test_a_cancel_that_does_not_end_the_batch_sends_every_item_to_the_fallback():
    # Results can only be read once the batch has ended; waiting longer would delay the page.
    result, client, batches, clock = run_batch(
        [item(1), item(2)], full(strike=None), full(strike=None), ends_at=NEVER, cancel_takes=NEVER,
        results={0: succeeded(full(strike=None))})
    assert written_by(result) == [HAIKU_STANDARD, HAIKU_STANDARD]
    assert clock.now <= BATCH_WAIT + CANCEL_WAIT
    assert result.failures == [{"source": "AI summariser", "error":
                                "batch did not end after cancelling; all items sent to the standard API"}]


# --- the batch failing ---------------------------------------------------------------------


@pytest.mark.parametrize("error, problem", [
    (status_error(anthropic.InternalServerError, 500), "HTTP 500"),
    (status_error(anthropic.BadRequestError, 400), "HTTP 400"),
    (anthropic.APIConnectionError(request=REQUEST), "connection error"),
    (anthropic.APITimeoutError(request=REQUEST), "timeout"),
])
def test_if_the_batch_cannot_be_created_every_item_goes_to_haiku_standard(error, problem):
    result, client, _, clock = run_batch([item(1), item(2)], full(strike=None), full(strike=None),
                                         model=SONNET, create_error=error)
    assert written_by(result) == [HAIKU_STANDARD, HAIKU_STANDARD]
    assert result.summaries == {"batch": 0, "fallback": 2}
    assert clock.sleeps == []  # nothing to wait for
    assert result.failures == [{"source": "AI summariser", "error":
                                f"batch not created ({problem}); all items sent to the standard API"}]


@pytest.mark.parametrize("cls, code", [(anthropic.AuthenticationError, 401), (anthropic.PermissionDeniedError, 403)])
def test_a_rejected_key_at_batch_creation_means_ai_unavailable(cls, code):
    result, client, _, _ = run_batch([item(1)], create_error=status_error(cls, code))
    assert result.unavailable == f"API key rejected (HTTP {code})"
    assert result.items[0].ai is None and client.messages.calls == []


def test_no_client_means_ai_unavailable_and_no_batch():
    result = summarise_batch([item()], None, known=[], today=TODAY)
    assert result.unavailable == "ANTHROPIC_API_KEY is not set" and result.items[0].ai is None


def test_no_items_means_no_batch_and_no_wait():
    result, client, batches, clock = run_batch([])
    assert batches.created == [] and clock.sleeps == []
    assert result.items == [] and result.summaries == {"batch": 0, "fallback": 0}


def test_errors_while_checking_the_batch_are_not_fatal():
    result, _, _, _ = run_batch([item(1)], ends_at=60, results={0: succeeded(full(strike=None))},
                                retrieve_errors=[anthropic.APIConnectionError(request=REQUEST),
                                                 status_error(anthropic.InternalServerError, 503)])
    assert written_by(result) == [BATCH]


def test_results_that_cannot_be_read_send_the_items_to_the_fallback():
    result, _, _, _ = run_batch([item(1)], full(strike=None), results={0: succeeded(full(strike=None))},
                                results_error=anthropic.APIConnectionError(request=REQUEST))
    assert written_by(result) == [HAIKU_STANDARD]
    assert result.failures == [{"source": "AI summariser", "error":
                                "batch results could not be read (connection error); "
                                "all items sent to the standard API"}]


def test_without_any_batch_answer_three_failed_fallback_calls_mean_ai_unavailable():
    errors = [anthropic.APIConnectionError(request=REQUEST) for _ in range(3)]
    result, *_ = run_batch([item(n) for n in range(4)], *errors,
                           create_error=status_error(anthropic.InternalServerError, 500))
    assert result.unavailable == "3 calls in a row failed (last: connection error)"
    assert all(i.ai is None for i in result.items)


def test_after_batch_answers_three_failed_fallback_calls_leave_the_rest_unrated():
    errors = [anthropic.APIConnectionError(request=REQUEST) for _ in range(3)]
    result, client, _, _ = run_batch([item(n) for n in range(5)], *errors, ends_at=NEVER,
                                     results={0: succeeded(full(strike=None))})
    assert result.unavailable is None  # the batch answered, so the API was up this morning
    assert [i.ai["severity"] for i in result.items] == ["high", None, None, None, None]
    assert len(client.messages.calls) == 3
    assert result.failures[-1]["error"] == "https://ect-news.test/4: not tried: 3 calls in a row failed"


# --- what the fallback is NOT: an answer from the batch is never sent to another model ------------


def test_a_fallback_item_that_fails_is_unrated():
    result, *_ = run_batch([item(1), item(2)], anthropic.APITimeoutError(request=REQUEST), ends_at=NEVER,
                           results={1: succeeded(full(strike=None))})
    assert result.items[0].ai == unrated() and written_by(result)[1] == BATCH
    assert result.failures == [{"source": "AI summariser", "error": "https://ect-news.test/1: timeout"}]
    assert result.summaries == {"batch": 1, "fallback": 0}  # unrated items count in neither


def test_a_refusal_in_the_batch_makes_the_item_unrated_and_no_other_model_is_asked():
    refusal = answer(None, stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"))
    result, client, _, _ = run_batch([item(1)], results={0: succeeded(refusal)})
    assert client.messages.calls == []  # owner's decision in #15: no refusal fallback
    assert result.items[0].ai == unrated()
    assert result.failures == [{"source": "AI summariser", "error": "https://ect-news.test/1: refused (cyber)"}]


@pytest.mark.parametrize("response", [full(severity="critical"), answer("{bad"),
                                      answer('{"summary": "cut', stop_reason="max_tokens")])
def test_a_bad_answer_in_the_batch_is_unrated_not_sent_to_the_fallback(response):
    result, client, _, _ = run_batch([item(1)], results={0: succeeded(response)})
    assert client.messages.calls == [] and result.items[0].ai == unrated()


def test_a_copied_batch_answer_gets_its_one_rephrase_retry_through_the_standard_api_with_the_same_model():
    result, client, _, _ = run_batch([item(1)], full(strike=None), model=SONNET,
                                     results={0: succeeded(full(summary=COPIED, strike=None))})
    [retry] = client.messages.calls
    assert retry["model"] == SONNET  # the same model rephrases; no switch to Haiku
    assert "could not be used" in user_text(retry)
    assert written_by(result) == [{"model": SONNET, "api": "standard"}]
    assert result.summaries == {"batch": 0, "fallback": 1} and result.failures == []


def test_if_the_rephrase_retry_of_a_batch_answer_also_copies_the_item_is_unrated():
    result, _, _, _ = run_batch([item(1)], full(summary=COPIED), results={0: succeeded(full(summary=COPIED))})
    assert result.items[0].ai == unrated()
    assert result.failures[0]["error"].endswith("(after a retry)")


# --- strike ids, tokens ----------------------------------------------------------------------


def test_new_strike_ids_follow_the_input_order_across_batch_and_fallback():
    result, *_ = run_batch([item(1), item(2)], full(), ends_at=NEVER, results={1: succeeded(full())})
    assert [i.ai["written_by"]["api"] for i in result.items] == ["standard", "batch"]
    assert [i.ai["strike"]["strike_id"] for i in result.items] == ["strike-2026-11-02-1", "strike-2026-11-02-2"]


def test_batch_tokens_are_counted_apart_for_the_cost_check():
    result, *_ = run_batch([item(1), item(2)], full(strike=None), ends_at=NEVER,
                           results={0: succeeded(full(strike=None))})
    assert (result.input_tokens, result.output_tokens) == (4000, 600)  # all tokens
    assert (result.batch_input_tokens, result.batch_output_tokens) == (2000, 300)  # at 50% (§5.5)
    assert result.calls == 1  # standard-API calls; the batch request is not one


def test_the_standard_summariser_alone_counts_its_items_as_standard():
    result = summarise([item(1)], FakeClient(full(strike=None)), known=[], today=TODAY)
    assert result.summaries == {"batch": 0, "fallback": 1}
    assert (result.batch_input_tokens, result.batch_output_tokens) == (0, 0)


def test_a_strike_from_a_batch_answer_keeps_its_known_id():
    known = [{"id": "strike-2026-10-30-1", "location": "ECT Delta", "start": None, "end": None,
              "first_headline": "Invented: union announces ECT strike"}]
    result, *_ = run_batch([item(1)], known=known,
                           results={0: succeeded(full(strike=strike(match="same", strike_id="strike-2026-10-30-1")))})
    assert result.items[0].ai["strike"]["strike_id"] == "strike-2026-10-30-1"
