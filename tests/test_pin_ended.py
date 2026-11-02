"""Ended PIN notices (spec §5.4, §2.1; issue #67).

A PIN notice's "End Date" is when the *notice* stops being valid. The rules stage reads it from
the notice text in memory (the `End Date dd Mon yyyy - hh:mm` line, Amsterdam time):

- ended **more than 12 hours** before the run -> dropped by the rules, with the End Date in the
  reason (owner's decision, 2 Nov 2026);
- ended **within the last 12 hours** (exactly 12 h included) -> kept, and the summariser makes it
  Low in code, whatever the AI answered (owner's confirmation, 2 Nov 2026);
- **no readable End Date** -> this rule doesn't apply; the other rules and the AI still do.

"The run" is when the sources were read (`feeds_read_at`), as for the 48 h rule. Notice texts
are invented (hard rule 13). No test touches the network.
"""

from datetime import datetime, timedelta, timezone

import pytest

from haven.clock import AMSTERDAM
from haven.config import FilterConfig, Source
from haven.feeds import PIN_SOURCE_ID, Item
from haven.filter import (
    DROP,
    PIN_ENDED_GRACE,
    TO_AI,
    apply_rules,
    decide,
    notice_ended,
    pin_end,
    read_end_date,
)

RUN = datetime(2026, 11, 2, 6, 45, tzinfo=AMSTERDAM)  # when the sources were read (winter time)

PIN = Source(id=PIN_SOURCE_ID, name="PIN notices to shipping", verdict="use",
             urls=("https://pin.test/rss.xml",), access="rss", language="en")
CONTARGO = Source(id="contargo-news", name="Contargo business news", verdict="use",
                  urls=("https://contargo.test/news",), access="html", language="en")
WORDS = FilterConfig(off_topic={"en": ("football",)})


def notice_text(end="2 Nov 2026 - 02:47"):
    return ("Invented notice. Area Invented Harbour Publication Date 1 Nov 2026 - 21:00 "
            f"End Date {end} Please follow the invented instructions of the traffic centre.")


def pin(end="2 Nov 2026 - 02:47", headline="Visibility Arrangement - Activate", published="2026-11-01T21:00:00+01:00",
        text=None, source=PIN_SOURCE_ID, n=1):
    return Item(source=source, headline=headline, url=f"https://pin.test/notice/{n}", published=published,
                language="en", access="full", snippet=None,
                article_text=text if text is not None else notice_text(end))


def ruled(it, now=RUN, sources=(PIN, CONTARGO)):
    by_id = {s.id: s for s in sources}
    return decide(it, by_id.get(it.source), WORDS.off_topic["en"], now)


# --- reading the End Date --------------------------------------------------------------------


def test_the_end_date_is_read_as_amsterdam_time():
    assert read_end_date(notice_text("1 Nov 2026 - 02:47")) == datetime(2026, 11, 1, 2, 47, tzinfo=AMSTERDAM)


@pytest.mark.parametrize("written, expected", [
    ("30 Oct 2026 - 21:16", datetime(2026, 10, 30, 21, 16)),
    ("3 Nov 2026 - 9:05", datetime(2026, 11, 3, 9, 5)),
    ("1 November 2026 - 02:47", datetime(2026, 11, 1, 2, 47)),
    ("15 Sept 2026 - 10:00", datetime(2026, 9, 15, 10, 0)),
    ("15 sep 2026 - 10:00", datetime(2026, 9, 15, 10, 0)),
    ("1 Nov 2026 – 02:47", datetime(2026, 11, 1, 2, 47)),  # an en dash
    ("1 Nov 2026 02:47", datetime(2026, 11, 1, 2, 47)),  # no dash
])
def test_end_date_forms_that_are_read(written, expected):
    assert read_end_date(notice_text(written)) == expected.replace(tzinfo=AMSTERDAM)


def test_summer_time_is_used_on_a_summer_date():
    end = read_end_date(notice_text("15 Jul 2026 - 10:00"))
    assert end.utcoffset() == timedelta(hours=2)


@pytest.mark.parametrize("text", [
    "Invented notice without any end date. Please follow the instructions.",
    notice_text("31 Nov 2026 - 10:00"),  # no such day
    notice_text("1 Foo 2026 - 10:00"),  # no such month
    notice_text("1 Nov 2026 - 25:10"),  # no such hour
    notice_text("1 Nov 2026 - 10:75"),  # no such minute
    notice_text("1 Nov 26 - 10:00"),  # a two-digit year
    notice_text("- Please"),
    notice_text(""),
    "",
])
def test_no_readable_end_date_gives_none(text):
    assert read_end_date(text) is None


def test_a_date_without_a_time_counts_to_the_end_of_that_day():
    # Like a date-only published date (§5.4): never dropped too early.
    assert read_end_date(notice_text("1 Nov 2026 Please")) == datetime(2026, 11, 2, 0, 0, tzinfo=AMSTERDAM)


def test_two_end_dates_give_the_later_one():
    text = notice_text("1 Nov 2026 - 02:47") + " Correction: End Date 2 Nov 2026 - 04:00"
    assert read_end_date(text) == datetime(2026, 11, 2, 4, 0, tzinfo=AMSTERDAM)


def test_an_hour_that_happens_twice_at_the_clock_change_is_read_as_the_later_one():
    # 25 Oct 2026: 02:00-03:00 happens twice (summer time ends). The later reading (winter
    # time, 01:30 UTC) can only keep a notice longer, never drop it too early.
    end = read_end_date(notice_text("25 Oct 2026 - 02:30"))
    assert end.astimezone(timezone.utc) == datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)


def test_an_hour_that_does_not_exist_at_the_clock_change_is_read_as_the_later_one():
    # 29 Mar 2026: 02:00-03:00 doesn't exist (summer time starts). Read it the later way too.
    end = read_end_date(notice_text("29 Mar 2026 - 02:30"))
    assert end.astimezone(timezone.utc) == datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc)


def test_only_pin_notices_have_an_end_date():
    assert pin_end(pin()) == datetime(2026, 11, 2, 2, 47, tzinfo=AMSTERDAM)
    assert pin_end(pin(source="contargo-news")) is None  # "End Date" in another source's text: ignored
    assert pin_end(Item(source=PIN_SOURCE_ID, headline="Invented notice", url="https://pin.test/x",
                        published=None, language="en", access="full", article_text=None)) is None


# --- the rule ----------------------------------------------------------------------------------


def test_a_notice_that_ended_more_than_12_hours_before_the_run_is_dropped_with_its_end_date():
    decision = ruled(pin(end="1 Nov 2026 - 18:44"))  # 12 h 1 min before 06:45
    assert decision.outcome == DROP
    assert decision.reason == "PIN notice ended more than 12 h ago (End Date 2026-11-01 18:44)"


def test_exactly_12_hours_is_kept_and_one_minute_more_is_dropped():
    assert PIN_ENDED_GRACE == timedelta(hours=12)
    assert ruled(pin(end="1 Nov 2026 - 18:45")).outcome == TO_AI
    assert ruled(pin(end="1 Nov 2026 - 18:44")).outcome == DROP


@pytest.mark.parametrize("end", ["2 Nov 2026 - 02:47", "2 Nov 2026 - 06:45", "3 Nov 2026 - 10:00"])
def test_a_notice_that_ended_within_12_hours_or_has_not_ended_goes_on_to_the_ai_check(end):
    assert ruled(pin(end=end)).outcome == TO_AI


def test_no_readable_end_date_means_the_rule_does_not_apply():
    assert ruled(pin(text="Invented notice without a date line.")).outcome == TO_AI
    assert ruled(pin(end="31 Nov 2026 - 10:00")).outcome == TO_AI
    # ...but the other rules still do.
    assert ruled(pin(text="Invented notice.", headline="Invented football notice")).outcome == DROP


def test_a_de_activate_notice_follows_the_same_rule():
    assert ruled(pin(headline="Visibility Arrangement - De-activate", end="1 Nov 2026 - 10:00")).outcome == DROP
    assert ruled(pin(headline="Visibility Arrangement - De-activate", end="2 Nov 2026 - 01:00")).outcome == TO_AI


def test_the_48_hour_rule_comes_first():
    decision = ruled(pin(published="2026-10-29T06:00:00+01:00", end="29 Oct 2026 - 10:00"))
    assert decision.reason == "older than 48 h"


def test_another_source_mentioning_an_end_date_is_not_dropped_by_this_rule():
    assert ruled(pin(source="contargo-news", end="1 Nov 2026 - 01:00")).outcome == TO_AI


def test_the_12_hours_are_real_hours_across_the_clock_change():
    # End Date 02:30 on 25 Oct (read as 01:30 UTC); the run at 13:30 UTC is exactly 12 h later.
    run = datetime(2026, 10, 25, 13, 30, tzinfo=timezone.utc)
    notice = pin(end="25 Oct 2026 - 02:30", published="2026-10-25T00:00:00+02:00")
    assert ruled(notice, now=run).outcome == TO_AI
    assert ruled(notice, now=run + timedelta(minutes=1)).outcome == DROP


def test_the_comparisons_wider_age_limit_does_not_change_the_12_hours():
    by_id = {PIN.id: PIN}
    [result] = apply_rules([pin(end="1 Nov 2026 - 10:00")], by_id.values(), WORDS, RUN, timedelta(days=7))
    assert result.decision.outcome == DROP


def test_the_reason_is_stored_and_holds_the_date_only_never_the_notice_text():
    [result] = apply_rules([pin(end="1 Nov 2026 - 10:00")], (PIN,), WORDS, RUN)
    record = result.item.record()
    assert record["filter"] == {"kept": False, "stage": "rules",
                                "reason": "PIN notice ended more than 12 h ago (End Date 2026-11-01 10:00)"}
    assert "Invented notice" not in str(record) and "traffic centre" not in str(record)


# --- ended or not, for the summariser ---------------------------------------------------------


def test_notice_ended_compares_the_end_date_with_the_run():
    assert notice_ended(pin(end="2 Nov 2026 - 02:47"), RUN)
    assert notice_ended(pin(end="2 Nov 2026 - 06:45"), RUN)  # ending at the very moment counts as ended
    assert not notice_ended(pin(end="2 Nov 2026 - 06:46"), RUN)
    assert not notice_ended(pin(text="Invented notice without a date line."), RUN)
    assert not notice_ended(pin(source="contargo-news", end="1 Nov 2026 - 01:00"), RUN)


def test_notice_ended_refuses_a_run_time_without_a_timezone():
    with pytest.raises(ValueError):
        notice_ended(pin(), datetime(2026, 11, 2, 6, 45))
