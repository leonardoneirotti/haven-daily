"""Haiku 5.5 vs Sonnet 5.5 side by side (spec §5.5, §10 step 6; issue #17).

The comparison script runs the real summariser twice on the same kept items, once per model,
and prints a side-by-side view for the owner. These tests use the fake client from
test_summarise.py: no API call, no network. Headlines and article texts are invented (hard
rule 13), and the view must never contain article text or teasers: it ends up in
docs/model-comparison.md, in the public repo.
"""

import json

import anthropic
import pytest

from haven.compare import (
    HAIKU,
    MODELS,
    SONNET,
    compare,
    cost_usd,
    estimate,
    format_markdown,
    unsupported_terms,
)
from test_summarise import (
    ARTICLE,
    SOURCES,
    TODAY,
    GOOD,
    answer,
    full,
    headline_answer,
    headline_item,
    item,
    status_error,
)

SECRET_TEXT = "Invented article marker zebra-quartz: the berth stays shut until Friday."
SECRET_TEASER = "Invented teaser marker mango-lattice."


class ByModel:
    """A fake Messages client that answers by model and records every request."""

    def __init__(self, answers):
        self.answers = {model: list(a) for model, a in answers.items()}
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        queue = self.answers[kwargs["model"]]
        if not queue:
            raise AssertionError(f"more calls to {kwargs['model']} than the test expected")
        a = queue.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a


class Client:
    def __init__(self, **answers):  # keyword = "haiku" / "sonnet"
        self.messages = ByModel({HAIKU: answers.get("haiku", []), SONNET: answers.get("sonnet", [])})


def sonnet_answer(**changes):
    data = json.loads(json.dumps(GOOD))
    data.update(summary="A one-day stoppage is planned by dock staff at a Maasvlakte box terminal.",
                severity="medium", tags=["Containers", "Sea access"])
    data.update(changes)
    return answer(json.dumps(data), input_tokens=2100, output_tokens=500)


# --- the models and the prices ------------------------------------------------------------


def test_the_two_models_are_haiku_and_sonnet_5_5():
    assert MODELS == ("claude-haiku-5-5", "claude-sonnet-5-5")


def test_cost_uses_each_models_list_price():
    # Haiku 5.5 $0.10 / $0.50, Sonnet 5.5 $2 / $10 per million tokens (spec §5.5, standard API)
    assert cost_usd(HAIKU, 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert cost_usd(SONNET, 1_000_000, 1_000_000) == pytest.approx(12.00)
    assert cost_usd(SONNET, 3000, 1500) == pytest.approx(0.021)


def test_cost_of_an_unknown_model_is_refused():
    with pytest.raises(KeyError):
        cost_usd("claude-opus-5-5", 1, 1)


def test_the_estimate_adds_the_filter_and_both_summary_runs():
    est = estimate(ai_check_items=40, summary_items=5)
    assert est["filter"] == pytest.approx(40 * cost_usd(HAIKU, 860, 52))
    assert est[HAIKU] == pytest.approx(5 * cost_usd(HAIKU, 3000, 1100))
    assert est[SONNET] == pytest.approx(5 * cost_usd(SONNET, 3000, 1500))
    assert est["total"] == pytest.approx(est["filter"] + est[HAIKU] + est[SONNET])


def test_the_estimate_with_nothing_to_do_is_zero():
    assert estimate(ai_check_items=0, summary_items=0)["total"] == 0


# --- the same items, the same request, two models -------------------------------------------


def test_both_models_get_exactly_the_same_request_apart_from_the_model():
    client = Client(haiku=[full()], sonnet=[sonnet_answer()])
    compare([item(1)], client, known=[], today=TODAY)
    haiku, sonnet = client.messages.calls
    assert haiku["model"] == HAIKU and sonnet["model"] == SONNET
    assert {k: v for k, v in haiku.items() if k != "model"} == {k: v for k, v in sonnet.items() if k != "model"}


def test_each_model_gets_its_own_result_for_every_item():
    client = Client(haiku=[full(), headline_answer()], sonnet=[sonnet_answer(), headline_answer(severity="low")])
    result = compare([item(1), headline_item(2)], client, known=[], today=TODAY)
    assert [i.ai["severity"] for i in result.outputs[HAIKU].items] == ["high", "medium"]
    assert [i.ai["severity"] for i in result.outputs[SONNET].items] == ["medium", "low"]
    assert result.outputs[HAIKU].items[0].ai["written_by"] == {"model": HAIKU, "api": "standard"}
    assert result.outputs[SONNET].items[0].ai["written_by"] == {"model": SONNET, "api": "standard"}


def test_max_items_caps_what_is_sent_and_lists_the_rest():
    client = Client(haiku=[full()], sonnet=[sonnet_answer()])
    result = compare([item(1), item(2), item(3)], client, known=[], today=TODAY, max_items=1)
    assert len(client.messages.calls) == 2  # one item, two models
    assert [i.url for i in result.left_out] == [item(2).url, item(3).url]


def test_one_model_failing_does_not_stop_the_other():
    error = status_error(anthropic.InternalServerError, 500)
    client = Client(haiku=[full(), full()], sonnet=[error, sonnet_answer()])
    result = compare([item(1), item(2)], client, known=[], today=TODAY)
    assert [i.ai["severity"] for i in result.outputs[HAIKU].items] == ["high", "high"]
    assert [i.ai["severity"] for i in result.outputs[SONNET].items] == [None, "medium"]
    assert "HTTP 500" in result.outputs[SONNET].failures[0]["error"]


# --- facts check: words in the AI's text that aren't in the source -------------------------


def test_a_number_not_in_the_source_is_flagged():
    source = "Dockworkers will stop work on 5 November for 24 hours."
    assert unsupported_terms("A 24-hour stoppage on 6 November.", source) == ["6"]


def test_a_name_not_in_the_source_is_flagged_but_the_first_word_of_a_sentence_is_not():
    source = "Dockworkers at ECT Delta will stop work."
    assert unsupported_terms("Staff at ECT Delta and Euromax will strike. Expect delays.", source) == ["Euromax"]


def test_matching_ignores_case_and_repeats_are_listed_once():
    source = "the ect delta terminal"
    assert unsupported_terms("Trucks at ECT Delta wait. Trucks at Euromax and Euromax.", source) == ["Euromax"]


def test_words_from_the_fixed_lists_are_not_flagged():
    assert unsupported_terms("Barge slots at Maasvlakte II are short.", "Barge slots are short.",
                             vocabulary=("Maasvlakte II",)) == []


def test_nothing_to_check_gives_nothing():
    assert unsupported_terms(None, "anything") == []


def test_the_check_runs_on_summary_and_impact_against_headline_and_article():
    said = sonnet_answer(summary="Dock staff at Antwerp plan a stoppage.", impact="Book 7 extra barges.")
    client = Client(haiku=[full()], sonnet=[said])
    result = compare([item(1)], client, known=[], today=TODAY)
    assert result.checks[SONNET][0] == ["Antwerp", "7"]
    assert result.checks[HAIKU][0] == []


def test_a_headline_only_item_has_nothing_to_check():
    client = Client(haiku=[headline_answer()], sonnet=[headline_answer()])
    result = compare([headline_item(1)], client, known=[], today=TODAY)
    assert result.checks[HAIKU] == [[]] and result.checks[SONNET] == [[]]


# --- the side-by-side view ------------------------------------------------------------------


def view(items, haiku, sonnet, **kw):
    client = Client(haiku=haiku, sonnet=sonnet)
    return format_markdown(compare(items, client, known=[], today=TODAY, **kw), SOURCES)


def test_the_view_shows_headline_link_and_both_answers():
    text = view([item(1)], [full()], [sonnet_answer()])
    assert item(1).headline in text and item(1).url in text and "ECT news" in text
    assert GOOD["summary"] in text and GOOD["impact"] in text
    assert "A one-day stoppage is planned" in text
    assert "| Severity | high | medium |" in text
    assert "Containers · Labour · ECT Delta" in text and "Containers · Sea access · ECT Delta" in text


def test_the_view_never_contains_article_text_or_teasers():
    secret = item(1, text=ARTICLE + " " + SECRET_TEXT, snippet=SECRET_TEASER)
    text = view([secret], [full()], [sonnet_answer()])
    assert "zebra-quartz" not in text and "mango-lattice" not in text
    assert ARTICLE[:60] not in text


def test_the_view_shows_tokens_and_cost_per_model():
    text = view([item(1)], [full()], [sonnet_answer()])
    assert "2,000 in / 300 out" in text  # Haiku, from the fake answer's usage
    assert "2,100 in / 500 out" in text  # Sonnet
    assert f"${cost_usd(HAIKU, 2000, 300):.4f}" in text
    assert f"${cost_usd(SONNET, 2100, 500):.4f}" in text


def test_the_view_shows_an_unrated_answer_and_its_failure_line():
    error = status_error(anthropic.InternalServerError, 500)
    text = view([item(1)], [full()], [error])
    assert "| Severity | high | unrated |" in text
    assert "HTTP 500" in text


def test_the_view_shows_the_strike_details():
    text = view([item(1)], [full()], [sonnet_answer()])
    assert "announced · ECT Delta, Maasvlakte · 2026-11-05 to 2026-11-05 · new strike-2026-11-02-1" in text


def test_the_view_marks_headline_only_items():
    text = view([headline_item(1)], [headline_answer()], [headline_answer()])
    assert "headline only" in text


def test_the_view_shows_unlisted_places_and_tags():
    off_list = sonnet_answer(tags=["Containers", "Reefers"], place="antwerp-gateway")
    text = view([item(1)], [full()], [off_list])
    assert "Reefers" in text and "antwerp-gateway" in text


def test_the_view_lists_words_to_check():
    text = view([item(1)], [full()], [sonnet_answer(summary="Dock staff at Antwerp plan a stoppage.")])
    assert "Antwerp" in text


def test_a_pipe_in_an_answer_does_not_break_the_table():
    text = view([item(1)], [full(summary="Stoppage | one day at the terminal.")], [sonnet_answer()])
    assert "Stoppage \\| one day" in text


def test_the_view_lists_items_left_out_by_the_cap():
    text = view([item(1), item(2)], [full()], [sonnet_answer()], max_items=1)
    assert "Not compared" in text and item(2).headline in text


def test_the_morning_job_keeps_the_48_hour_limit():
    from haven.filter import MAX_AGE, apply_rules, run_filter
    import inspect
    assert MAX_AGE.total_seconds() == 48 * 3600
    assert inspect.signature(apply_rules).parameters["max_age"].default == MAX_AGE
    assert inspect.signature(run_filter).parameters["max_age"].default == MAX_AGE
