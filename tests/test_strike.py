"""Strike flag: pure logic over stored items (spec §5.7, §2.2; issue #21).

Every item here is invented, in the shape the summariser stores (§6.1): `filter.kept`,
`headline`, `url`, `source` (id), `published` and `strike` with `state`, `location`,
`affects_rotterdam`, `start`, `end`, `match`, `strike_id`.

"Today" is 2 Nov 2026 (a Monday). `days` lists (collection day, records); today's own
records are passed in by the runner, because today's items file isn't written yet.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from haven import storage, strike
from haven.config import Source

TODAY = date(2026, 11, 2)
READ_AT = datetime(2026, 11, 2, 5, 45, tzinfo=timezone.utc)  # 06:45 Amsterdam
SOURCES = (Source(id="nltimes", name="NL Times", verdict="headline-only"),
           Source(id="rijnmond", name="RTV Rijnmond", verdict="headline-only"))

_urls = iter(range(1, 10_000))


def ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def iso(day: date) -> str:
    return day.isoformat()


def item(state="announced", start=None, end=None, *, match="new", strike_id="strike-2026-10-30-1",
         rotterdam=True, location="Maasvlakte", published=None, kept=True, source="nltimes",
         headline=None):
    n = next(_urls)
    return {
        "source": source,
        "headline": headline or f"Invented strike headline {n}",
        "url": f"https://example.org/strike/{n}",
        "published": published,
        "language": "en",
        "access": "headline-only",
        "filter": {"kept": kept, "stage": "rules", "reason": "auto-keep"},
        "severity": "high",
        "strike": {"state": state, "location": location, "affects_rotterdam": rotterdam,
                   "start": iso(start) if isinstance(start, date) else start,
                   "end": iso(end) if isinstance(end, date) else end,
                   "match": match, "strike_id": strike_id},
    }


def flag(*days, ai_unavailable=False):
    return strike.flag_from_items(list(days), TODAY, SOURCES, ai_unavailable=ai_unavailable)


def urls(result):
    return [shown["url"] for shown in result.items]


# --- §5.7 table, one test per row ------------------------------------------------------


def test_no_strike_items_is_normal_with_nothing_linked():
    result = flag((TODAY, [{"headline": "Not a strike", "url": "https://example.org/x",
                            "source": "nltimes", "filter": {"kept": True}, "strike": None}]))
    assert result.level == "green"
    assert result.value == "No active strike"
    assert result.items == []


def test_row_cancelled_is_ignored():
    first = item("announced", TODAY, TODAY)
    called_off = item("cancelled", match="same")
    result = flag((ago(1), [called_off]), (ago(3), [first]))
    assert result.level == "green"


def test_row_end_before_today_is_ignored_for_every_state():
    for state in ("announced", "ongoing"):
        result = flag((ago(3), [item(state, ago(4), ago(1))]))
        assert result.level == "green", state
        assert result.items == []


def test_row_announced_dates_include_today_is_alert():
    for start, end in ((TODAY, TODAY), (ago(1), TODAY), (TODAY, TODAY + timedelta(days=2)),
                       (ago(2), TODAY + timedelta(days=2))):
        result = flag((ago(5), [item("announced", start, end)]))
        assert result.level == "red", (start, end)


def test_announced_starting_today_without_end_is_alert():
    result = flag((ago(5), [item("announced", TODAY, None)]))
    assert result.level == "red"
    assert result.value == "Strike today · Maasvlakte"


def test_row_ongoing_end_not_passed_is_alert():
    for end in (TODAY, TODAY + timedelta(days=3)):
        result = flag((ago(6), [item("ongoing", ago(7), end)]))
        assert result.level == "red", end
        assert result.value == "Strike ongoing · Maasvlakte"


def test_row_ongoing_no_end_newest_item_two_days_old_is_alert():
    result = flag((ago(2), [item("ongoing", published=f"{iso(ago(2))}T23:30:00+01:00")]))
    assert result.level == "red"


def test_row_ongoing_no_end_newest_item_three_days_old_is_watch_as_of():
    result = flag((ago(3), [item("ongoing", published=f"{iso(ago(3))}T08:00:00+01:00")]))
    assert result.level == "amber"
    assert result.value == "Strike ongoing as of 30 Oct, no newer report · Maasvlakte"


def test_ongoing_age_uses_collection_day_when_published_is_missing():
    assert flag((ago(2), [item("ongoing")])).level == "red"
    assert flag((ago(3), [item("ongoing")])).level == "amber"


def test_ongoing_age_uses_the_published_day_not_the_collection_day():
    # published 3 days ago (Amsterdam date), collected 2 days ago: 3 days old
    late = item("ongoing", published=f"{iso(ago(3))}T22:00:00+01:00")
    assert flag((ago(2), [late])).level == "amber"


def test_ongoing_without_end_never_drops_to_normal_inside_the_window():
    assert flag((ago(14), [item("ongoing")])).level == "amber"


def test_row_announced_start_after_today_is_watch():
    result = flag((ago(1), [item("announced", TODAY + timedelta(days=3), TODAY + timedelta(days=3))]))
    assert result.level == "amber"
    assert result.value == "Strike announced for 5 Nov · Maasvlakte"


def test_row_announced_no_dates_is_watch():
    result = flag((ago(1), [item("announced")]))
    assert result.level == "amber"
    assert result.value == "Strike announced, no date given · Maasvlakte"


# --- cases the table doesn't name (Claude's defaults, spec §5.7) -----------------------


def test_announced_started_before_today_without_end_is_read_as_ongoing():
    fresh = flag((ago(1), [item("announced", ago(1), None, published=f"{iso(ago(1))}T09:00:00+01:00")]))
    assert fresh.level == "red"
    assert fresh.value == "Strike since 1 Nov · Maasvlakte"
    stale = flag((ago(4), [item("announced", ago(4), None)]))
    assert stale.level == "amber"
    assert stale.value == "Strike since 29 Oct, no newer report · Maasvlakte"


def test_announced_with_only_an_end_date_is_watch_until_it_passes():
    result = flag((ago(1), [item("announced", None, TODAY + timedelta(days=4))]))
    assert result.level == "amber"
    assert result.value == "Strike announced until 6 Nov · Maasvlakte"
    assert flag((ago(3), [item("announced", None, ago(1))])).level == "green"


def test_ongoing_with_a_start_after_today_is_still_alert():
    assert flag((TODAY, [item("ongoing", TODAY + timedelta(days=1), None)])).level == "red"


def test_not_rotterdam_is_ignored():
    result = flag((TODAY, [item("ongoing", TODAY, TODAY, rotterdam=False)]))
    assert result.level == "green"
    assert result.items == []


def test_dropped_items_are_ignored():
    assert flag((TODAY, [item("ongoing", TODAY, TODAY, kept=False)])).level == "green"


def test_missing_location_leaves_it_out_of_the_value():
    assert flag((TODAY, [item("ongoing", TODAY, TODAY, location=None)])).value == "Strike ongoing"


# --- newest item wins ------------------------------------------------------------------


def test_newest_item_wins_ongoing_overrides_announced():
    later = item("announced", TODAY + timedelta(days=5), None)
    now_on = item("ongoing", match="same")
    result = flag((TODAY, [now_on]), (ago(3), [later]))
    assert result.level == "red"
    assert urls(result) == [now_on["url"]]


def test_newest_item_wins_even_if_it_lowers_a_confident_match():
    today_strike = item("announced", TODAY, TODAY)
    moved = item("announced", TODAY + timedelta(days=7), TODAY + timedelta(days=7), match="same")
    result = flag((ago(1), [moved]), (ago(4), [today_strike]))
    assert result.level == "amber"
    assert result.value == "Strike announced for 9 Nov · Maasvlakte"


def test_same_day_items_newest_published_wins_whatever_the_file_order():
    early = item("ongoing", match="same", published=f"{iso(TODAY)}T05:00:00+01:00")
    late = item("cancelled", match="same", published=f"{iso(TODAY)}T06:00:00+01:00")
    first = item("announced", TODAY, TODAY)
    result = flag((TODAY, [late, early]), (ago(2), [first]))
    assert result.level == "green"


def test_same_day_items_without_times_later_in_the_file_wins():
    first = item("announced", TODAY, TODAY)
    a = item("cancelled", match="same")
    b = item("ongoing", match="same")
    assert flag((TODAY, [a, b]), (ago(2), [first])).level == "red"


# --- the flag and what it links --------------------------------------------------------


def test_flag_is_the_worst_level():
    watch = item("announced", strike_id="strike-2026-10-31-1")
    alert = item("ongoing", TODAY, TODAY, strike_id="strike-2026-11-01-1")
    result = flag((ago(1), [alert]), (ago(2), [watch]))
    assert result.level == "red"
    assert urls(result) == [alert["url"]]


def test_same_level_links_the_strike_with_the_newest_deciding_item():
    older = item("announced", strike_id="strike-2026-10-28-1")
    newer = item("announced", location="Botlek", strike_id="strike-2026-10-31-1")
    result = flag((ago(1), [newer]), (ago(4), [older]))
    assert urls(result) == [newer["url"]]
    assert result.value == "Strike announced, no date given · Botlek"


def test_deciding_item_details():
    old = item("announced", TODAY, TODAY, headline="Dockers call strike at Maasvlakte",
               source="rijnmond", published="2026-10-29T17:20:00+01:00")
    result = flag((ago(4), [old]))
    assert result.items == [{
        "headline": "Dockers call strike at Maasvlakte",
        "url": old["url"],
        "source": "RTV Rijnmond",
        "published": "2026-10-29T17:20:00+01:00",
        "day": "2026-10-29",
        "day_page": "days/2026-10-29.html",
        "role": "decides",
        "state": "announced",
        "match": "new",
    }]


def test_todays_item_has_no_day_page_and_unknown_source_keeps_its_id():
    today_item = item("ongoing", TODAY, TODAY, source="someone")
    shown = flag((TODAY, [today_item])).items[0]
    assert shown["day_page"] is None
    assert shown["source"] == "someone"


def test_normal_after_a_cancellation_links_the_cancellation():
    first = item("announced", TODAY, TODAY)
    called_off = item("cancelled", match="same")
    result = flag((ago(1), [called_off]), (ago(3), [first]))
    assert result.level == "green"
    assert result.value == "Strike called off · Maasvlakte"
    assert urls(result) == [called_off["url"]]
    assert result.items[0]["role"] == "decides"


def test_a_cancellation_is_not_linked_when_another_strike_raises_the_flag():
    called_off = item("cancelled", match="same")
    other = item("announced", strike_id="strike-2026-11-01-1")
    result = flag((ago(1), [called_off, other]), (ago(3), [item("announced", TODAY, TODAY)]))
    assert result.level == "amber"
    assert urls(result) == [other["url"]]


def test_cancellation_of_a_non_rotterdam_strike_is_not_linked():
    first = item("announced", TODAY, TODAY, rotterdam=False)
    called_off = item("cancelled", match="same", rotterdam=False)
    result = flag((ago(1), [called_off]), (ago(3), [first]))
    assert result.value == "No active strike"
    assert result.items == []


# --- the window: 14 days, plus strikes dated today or later up to 60 days back ---------


def test_announced_18_days_ahead_is_still_alert_on_its_day():
    long_ahead = item("announced", TODAY, TODAY)
    result = flag((ago(18), [long_ahead]))
    assert result.level == "red"
    assert urls(result) == [long_ahead["url"]]
    assert result.items[0]["day_page"] == f"days/{iso(ago(18))}.html"


def test_announced_18_days_ahead_is_watch_the_day_before():
    tomorrow = item("announced", TODAY + timedelta(days=1), TODAY + timedelta(days=1))
    assert flag((ago(17), [tomorrow])).level == "amber"


def test_old_strike_with_a_later_end_counts_by_its_end_date():
    long_one = item("ongoing", ago(40), TODAY + timedelta(days=2))
    assert flag((ago(40), [long_one])).level == "red"


def test_cancellation_outside_14_days_still_cancels_a_strike_dated_today():
    first = item("announced", TODAY, TODAY)
    called_off = item("cancelled", match="same")  # no dates: outside the window on its own
    result = flag((ago(16), [called_off]), (ago(20), [first]))
    assert result.level == "green"
    assert urls(result) == [called_off["url"]]


def test_undated_strike_older_than_14_days_is_not_counted():
    assert flag((ago(15), [item("ongoing")])).level == "green"
    assert flag((ago(15), [item("announced")])).level == "green"


def test_strike_dated_in_the_past_older_than_14_days_is_not_counted():
    assert flag((ago(20), [item("announced", ago(10), ago(10))])).level == "green"


# --- safety rules: only `same` lowers; `unsure` shows both items -----------------------


def test_cancellation_clears_only_on_same():
    first = item("announced", TODAY, TODAY)
    maybe_off = item("cancelled", match="unsure")
    result = flag((ago(1), [maybe_off]), (ago(3), [first]))
    assert result.level == "red"
    assert urls(result) == [first["url"], maybe_off["url"]]
    assert [shown["role"] for shown in result.items] == ["decides", "unsure"]


def test_unsure_that_lowers_does_not_lower_a_watch_either():
    first = item("announced")
    maybe_later = item("announced", None, ago(1), match="unsure")  # would be "over"
    result = flag((ago(1), [maybe_later]), (ago(3), [first]))
    assert result.level == "amber"
    assert urls(result) == [first["url"], maybe_later["url"]]


def test_unsure_with_the_same_level_is_shown_next_to_the_strike():
    first = item("announced")
    maybe_same = item("announced", match="unsure")
    result = flag((ago(1), [maybe_same]), (ago(3), [first]))
    assert result.level == "amber"
    assert urls(result) == [first["url"], maybe_same["url"]]


def test_unsure_that_raises_counts_as_its_own_strike_and_shows_both():
    first = item("announced", TODAY + timedelta(days=4), TODAY + timedelta(days=4))
    maybe_on = item("ongoing", match="unsure")
    result = flag((TODAY, [maybe_on]), (ago(2), [first]))
    assert result.level == "red"
    assert result.value == "Strike ongoing · Maasvlakte"
    assert urls(result) == [maybe_on["url"], first["url"]]
    assert [shown["role"] for shown in result.items] == ["decides", "possibly the same as"]


def test_unsure_that_raises_a_non_rotterdam_strike_counts_on_its_own():
    first = item("announced", rotterdam=False)
    maybe = item("announced", TODAY, TODAY, match="unsure")
    result = flag((TODAY, [maybe]), (ago(2), [first]))
    assert result.level == "red"
    assert urls(result) == [maybe["url"], first["url"]]


def test_unsure_cancellation_older_than_a_confident_report_is_not_shown():
    first = item("announced", TODAY, TODAY)
    maybe_off = item("cancelled", match="unsure")
    confirmed = item("announced", TODAY, TODAY, match="same")
    result = flag((ago(1), [confirmed]), (ago(2), [maybe_off]), (ago(3), [first]))
    assert result.level == "red"
    assert urls(result) == [confirmed["url"]]


def test_unsure_naming_a_strike_not_in_the_window_counts_on_its_own():
    maybe = item("ongoing", match="unsure", strike_id="strike-2026-09-01-1")
    result = flag((TODAY, [maybe]))
    assert result.level == "red"
    assert urls(result) == [maybe["url"]]


def test_unsure_cancellation_of_a_strike_not_in_the_window_shows_nothing():
    maybe_off = item("cancelled", match="unsure", strike_id="strike-2026-09-01-1")
    result = flag((TODAY, [maybe_off]))
    assert result.level == "green"
    assert result.items == []


def test_old_unsure_item_does_not_bring_back_an_old_strike():
    # Old strike outside the window; an unsure cancellation inside it must not revive it.
    old = item("ongoing")
    maybe_off = item("cancelled", match="unsure")
    assert flag((ago(1), [maybe_off]), (ago(30), [old])).level == "green"


# --- AI unavailable, and bad data ------------------------------------------------------


def test_ai_unavailable_is_no_data():
    result = flag((TODAY, [item("ongoing", TODAY, TODAY)]), ai_unavailable=True)
    assert result.level is None
    assert result.value is None
    assert result.items == []


def test_unreadable_strike_details_are_skipped_with_a_failure_line():
    broken = item("striking")
    broken_id = item("ongoing", TODAY, TODAY, strike_id=None)
    result = flag((TODAY, [broken, broken_id]))
    assert result.level == "red"  # the id-less strike still counts, on its own
    assert len(result.failures) == 1
    assert result.failures[0]["source"] == "Strike flag"
    assert "2026-11-02" in result.failures[0]["error"]
    assert broken["headline"] not in result.failures[0]["error"]


def test_unreadable_date_counts_as_no_date_with_a_failure_line():
    result = flag((ago(1), [item("announced", "5 November", None)]))
    assert result.level == "amber"
    assert result.value == "Strike announced, no date given · Maasvlakte"
    assert len(result.failures) == 1


def test_records_that_are_not_objects_are_skipped():
    assert flag((TODAY, ["oops", None, item("announced")])).level == "amber"


# --- the status reading ----------------------------------------------------------------


def test_reading_in_the_status_shape():
    first = item("announced", TODAY, TODAY, source="rijnmond")
    reading = strike.reading(flag((ago(3), [first])), READ_AT)
    assert reading == {
        "key": "strike",
        "label": "Strike flag",
        "icon": "megaphone",
        "value": "Strike today · Maasvlakte",
        "level": "red",
        "place": "From the news of the last 14 days",
        "items": reading["items"],
        "observed_at": "2026-11-02T06:45:00+01:00",
        "source_name": "RTV Rijnmond",
        "source_url": first["url"],
        "note": None,
    }
    assert [shown["url"] for shown in reading["items"]] == [first["url"]]


def test_reading_with_nothing_linked():
    reading = strike.reading(flag(), READ_AT)
    assert reading["level"] == "green"
    assert reading["value"] == "No active strike"
    assert reading["source_name"] == "Haven Daily's news sources"
    assert reading["source_url"] is None
    assert reading["items"] == []


def test_reading_when_the_ai_was_unavailable():
    reading = strike.reading(flag(ai_unavailable=True), READ_AT)
    assert reading["value"] is None and reading["level"] is None
    assert reading["note"] == "Can't be judged without the AI step."


def test_reading_stores_no_article_text():
    reading = strike.reading(flag((TODAY, [item("ongoing", TODAY, TODAY)])), READ_AT)
    storage._refuse_article_text(reading, "status")  # raises if a text-like field slipped in


# --- reading stored days ---------------------------------------------------------------


def test_read_strike_flag_reads_60_days_of_stored_items(tmp_path):
    storage.write("items", ago(18), [item("announced", TODAY, TODAY)], data_dir=tmp_path)
    storage.write("items", ago(61), [item("ongoing", None, TODAY, strike_id="strike-old-1")],
                  data_dir=tmp_path)
    result = strike.read_strike_flag([], TODAY, READ_AT, SOURCES, data_dir=tmp_path)
    assert result.failures == []
    assert result.reading["level"] == "red"
    assert len(result.reading["items"]) == 1


def test_read_strike_flag_counts_todays_records(tmp_path):
    result = strike.read_strike_flag([item("ongoing", TODAY, TODAY)], TODAY, READ_AT, SOURCES,
                                     data_dir=tmp_path)
    assert result.reading["level"] == "red"
    assert result.reading["items"][0]["day_page"] is None


def test_read_strike_flag_never_raises_on_a_broken_file(tmp_path):
    (tmp_path / "items").mkdir()
    (tmp_path / "items" / f"{iso(ago(2))}.jsonl").write_text("{broken\n", encoding="utf-8")
    result = strike.read_strike_flag([], TODAY, READ_AT, SOURCES, data_dir=tmp_path)
    assert result.reading["level"] is None
    assert result.reading["value"] is None
    assert len(result.failures) == 1
    assert result.failures[0]["source"] == "Strike flag"


def test_read_strike_flag_ai_unavailable_reads_nothing(tmp_path):
    result = strike.read_strike_flag([item("ongoing", TODAY, TODAY)], TODAY, READ_AT, SOURCES,
                                     ai_unavailable=True, data_dir=tmp_path)
    assert result.reading["level"] is None
    assert result.reading["note"] == "Can't be judged without the AI step."
    assert result.failures == []


def test_reading_round_trips_through_storage(tmp_path):
    result = strike.read_strike_flag([item("announced")], TODAY, READ_AT, SOURCES, data_dir=tmp_path)
    storage.write("status", TODAY, [result.reading], data_dir=tmp_path)
    assert json.loads((tmp_path / "status" / f"{iso(TODAY)}.json").read_text(encoding="utf-8"))
