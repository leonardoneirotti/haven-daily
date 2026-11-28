"""Three fixes before launch, from the dry run of 27 Nov 2026 (issue #164; run 46024230132).

The owner (28 Nov 2026), in one small PR, tested with the stored dry-run data, no paid API run:

1. Place fallback: the summariser picked no place for the extreme low-water notice although our own
   summary names Botlek, Waalhaven/Nieuwe Maas and Europoort, so the day's only High item had no
   number on the chart. Now, when the AI picks no listed place, the first listed place the item's
   own text names (headline, then summary) is pinned, and logged.
2. Impact line: High and Medium items always get a "What it means" line. An empty one is retried
   once, like the wording check. Low items may stay empty (an incident already cleared).
3. Dials: "No reading yesterday" / "since yesterday" become the date actually compared ("vs 25 Nov");
   with no earlier brief, "No earlier reading".

The low-water notice below is the dry run's: its headline and Haven Daily's own summary, as stored in
the brief. The article text is invented (hard rule 13). No test touches the network.
"""

import json
from pathlib import Path

import pytest

from haven import places as places_module
from haven import render
from haven import run as runner
from haven import summarise
from test_render_real import dial, kaub, make_brief, render_days, text_of
from test_summarise import GOOD, SOURCES, answer, item, run, user_text
from test_summarise_batch import run_batch, succeeded

ROOT = Path(__file__).resolve().parent.parent
SPEC = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")

# --- 1. place fallback -----------------------------------------------------------------------

LOW_WATER_HEADLINE = "Information regarding navigation - extreme low water"
LOW_WATER_SUMMARY = ("Port of Rotterdam warns that extreme low water may occur at low tide in the coming days, "
                     "with forecasts of about 0.41 to 0.43 m below ALAT at Botlek, Waalhaven/Nieuwe Maas and "
                     "Europoort in the early hours of 29 November.")
LOW_WATER_IMPACT = ("Very low water could reduce available depth for vessels and may affect draught-sensitive "
                    "movements around Botlek, Waalhaven and Europoort near those times.")
INVENTED_NOTICE = "Invented notice text about low water at a few port areas in the coming days."


def low_water_answer(**changes):
    data = {"summary": LOW_WATER_SUMMARY, "impact": LOW_WATER_IMPACT, "severity": "high", "place": "none",
            "tags": ["Sea access", "Botlek", "Europoort", "Waalhaven", "Nieuwe Maas"], "strike": None}
    data.update(changes)
    return answer(json.dumps(data))


def low_water_item():
    return item(headline=LOW_WATER_HEADLINE, text=INVENTED_NOTICE)


def test_the_dry_runs_low_water_notice_gets_a_number_on_the_map():
    result, _ = run([low_water_item()], low_water_answer())
    ai = result.items[0].ai
    assert ai["map"] is not None and ai["map"]["label"] == "Botlek"  # the first place the summary names
    botlek = next(p for p in places_module.load_places() if p.id == "botlek")
    assert (ai["map"]["lat"], ai["map"]["lon"]) == (botlek.lat, botlek.lon)  # from the list, never the AI


def test_a_place_taken_from_the_text_is_recorded_and_logged():
    result, _ = run([low_water_item()], low_water_answer())
    ai = result.items[0].ai
    assert ai["place_from_text"] == "Botlek"
    brief = summarise.brief_item(result.items[0], SOURCES)
    assert brief["place_from_text"] == "Botlek" and brief["map"]["label"] == "Botlek"
    lines = runner.log_lines({"items": [brief], "build": {"failures": []}})
    assert lines == [f"Place from the item's text: {brief['url']}: Botlek (the AI picked no listed place)"]


def test_an_answer_off_the_place_list_falls_back_too():
    result, _ = run([low_water_item()], low_water_answer(place="harbour-somewhere"))
    ai = result.items[0].ai
    assert ai["map"]["label"] == "Botlek" and ai["place_from_text"] == "Botlek"
    assert ai["unlisted"] == {"places": ["harbour-somewhere"], "tags": []}  # still listed for the owner


def test_the_headline_is_read_before_the_summary():
    result, _ = run([item(headline="Invented: works at the Calandbrug", text=INVENTED_NOTICE)],
                    low_water_answer())
    assert result.items[0].ai["map"]["label"] == "Calandbrug"


def test_a_road_is_pinned_only_when_the_text_names_no_other_place():
    on_road = "Invented: lane closed on the A15 near the Botlek, traffic slow."
    only_road = "Invented: lane closed on the A15, traffic slow."
    first, _ = run([low_water_item()], low_water_answer(summary=on_road, impact=None, severity="low"))
    second, _ = run([low_water_item()], low_water_answer(summary=only_road, impact=None, severity="low"))
    assert first.items[0].ai["map"]["label"] == "Botlek"  # a road is only a fallback (#138)
    assert second.items[0].ai["map"]["label"] == "A15"


def test_a_text_that_names_no_listed_place_stays_off_the_map():
    summary = "Invented: a notice about low water somewhere in the port in the coming days."
    result, _ = run([low_water_item()], low_water_answer(summary=summary))
    ai = result.items[0].ai
    assert ai["map"] is None and "place_from_text" not in ai
    assert "place_from_text" not in summarise.brief_item(result.items[0], SOURCES)


def test_a_place_the_ai_picked_is_kept_and_nothing_is_recorded():
    result, _ = run([low_water_item()], low_water_answer(place="europoort"))
    ai = result.items[0].ai
    assert ai["map"]["label"] == "Europoort" and "place_from_text" not in ai


def test_names_are_matched_as_proper_nouns_only():
    # As prefer_specific (#138): "scheur" is also a Dutch word; the fairway is "Scheur".
    assert places_module.named_first("Invented: a scheur in the quay wall.") is None
    assert places_module.named_first("Invented: dredging in the Scheur.") == "scheur"


def test_the_longer_name_wins_at_the_same_spot():
    assert places_module.named_first("Invented: works at Maasvlakte II this week.") == "maasvlakte-2"


def test_the_spec_describes_the_place_fallback():
    assert "**Place from the item's text** *(#164" in SPEC


# --- 2. an impact line for High and Medium ---------------------------------------------------

HEDGED = "Container moves at that terminal could stop on the day; planners may want to plan pickups around it."


@pytest.mark.parametrize("severity", ["high", "medium"])
@pytest.mark.parametrize("empty", [None, "", "   "])
def test_an_empty_impact_on_a_high_or_medium_item_is_retried_once(severity, empty):
    first = dict(GOOD, severity=severity, impact=empty)
    second = dict(GOOD, severity=severity, impact=HEDGED)
    result, client = run([item()], answer(json.dumps(first)), answer(json.dumps(second)))
    assert len(client.messages.calls) == 2
    assert result.items[0].ai["impact"] == HEDGED
    note = user_text(client.messages.calls[1])
    assert f"no impact for an item rated {severity}" in note
    assert "based only on what the item says" in note


def test_empty_twice_keeps_the_item_and_says_so():
    empty = dict(GOOD, impact=None)
    result, client = run([item()], answer(json.dumps(empty)), answer(json.dumps(empty)))
    ai = result.items[0].ai
    assert len(client.messages.calls) == 2
    assert ai["severity"] == "high" and ai["summary"] == GOOD["summary"] and ai["impact"] is None
    assert "impact_left_out" not in ai  # the page says "Not enough information", as before
    assert [f["error"] for f in result.failures] == [
        "https://ect-news.test/1: no impact for an item rated high (after a retry)"]


@pytest.mark.parametrize("empty", [None, ""])
def test_a_low_item_may_have_no_impact_without_a_retry(empty):
    result, client = run([item()], answer(json.dumps(dict(GOOD, severity="low", impact=empty))))
    assert len(client.messages.calls) == 1
    assert result.items[0].ai["impact"] is None and result.failures == []


def test_a_batch_answer_without_impact_for_a_high_item_is_retried_outside_the_batch():
    empty = dict(GOOD, impact=None)
    result, client, *_ = run_batch([item(1)], answer(json.dumps(dict(GOOD, impact=HEDGED))),
                                   results={0: succeeded(answer(json.dumps(empty)))})
    ai = result.items[0].ai
    assert ai["impact"] == HEDGED and ai["written_by"]["api"] == "standard"
    # The run log says why (#143): "Outside the batch: <url>: rephrase retry: no impact …".
    assert ai["written_by"]["why"].startswith("rephrase retry: no impact for an item rated high")


def test_a_source_whose_permission_has_no_impact_is_never_retried_for_one():
    # The permission's impact = false (#107): an impact is never asked for, so never retried.
    import test_publisher_permission as perm

    result, client = perm.run([perm.rijnmond_item()], perm.rijnmond_answer(severity="high"),
                              sources=(perm.rijnmond(),))
    assert len(client.messages.calls) == 1 and result.items[0].ai["impact"] is None


def test_the_spec_describes_the_impact_rule():
    assert "**An impact line for High and Medium** *(#164" in SPEC


# --- 3. the dials name the date they compare with -----------------------------------------------


def test_the_change_names_the_previous_briefs_date(tmp_path):
    pages = render_days(tmp_path, make_brief("2026-11-19", status=[kaub(24, "2026-11-19")]),
                        make_brief("2026-11-20", status=[kaub(21)]))
    card = text_of(dial(pages["2026-11-20"], "rhine"))
    assert "−3 cm vs 19 Nov" in card and "yesterday" not in card.lower()


def test_after_a_missing_day_it_compares_with_the_last_brief_and_says_which(tmp_path):
    pages = render_days(tmp_path, make_brief("2026-11-18", status=[kaub(24, "2026-11-18")]),
                        make_brief("2026-11-20", status=[kaub(21)]))
    card = text_of(dial(pages["2026-11-20"], "rhine"))
    assert "−3 cm vs 18 Nov" in card and "yesterday" not in card.lower()


def test_the_first_brief_says_no_earlier_reading(tmp_path):
    pages = render_days(tmp_path, make_brief("2026-11-20", status=[kaub(21)]))
    assert "No earlier reading" in text_of(dial(pages["2026-11-20"], "rhine"))


def test_an_earlier_brief_without_that_reading_names_its_date(tmp_path):
    pages = render_days(tmp_path, make_brief("2026-11-18", status=[kaub(None, "2026-11-18")]),
                        make_brief("2026-11-20", status=[kaub(21)]))
    assert "No reading on 18 Nov" in text_of(dial(pages["2026-11-20"], "rhine"))


def test_unchanged_and_text_values_name_the_date_too():
    before, now = dict(kaub(21), value=21), kaub(21)
    assert render.describe_change(now, before, False, "2026-11-25") == "Unchanged vs 25 Nov"
    text_now = {"value": "No warnings", "unit": None}
    assert render.describe_change(text_now, {"value": "No warnings"}, False, "2026-11-25") == "Same as 25 Nov"
    assert render.describe_change(text_now, {"value": "Code yellow · Wind"}, False, "2026-11-25") == (
        "25 Nov: Code yellow · Wind")
    assert render.describe_change(text_now, None, True, None) == "No earlier reading"


def test_no_page_of_the_sample_site_says_yesterday(tmp_path):
    render.render_site(ROOT / "data" / "sample" / "briefs", tmp_path / "site")
    for page in (tmp_path / "site").rglob("*.html"):
        assert "yesterday" not in text_of(page.read_text(encoding="utf-8")).lower(), page.name


def test_the_spec_describes_the_dates_on_the_dials():
    assert "**The dials name the date they compare with** *(#164" in SPEC
    assert "vs 25 Nov" in SPEC and "No earlier reading" in SPEC
