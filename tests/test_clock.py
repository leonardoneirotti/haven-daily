"""Amsterdam date/time helper (spec §5.1.1): "today" is always the Amsterdam date.

Expected values are worked out by hand from the Dutch time rules:
CET = UTC+1 in winter, CEST = UTC+2 in summer; in 2026 the clocks go forward
on Sunday 29 March at 01:00 UTC and back on Sunday 25 October at 01:00 UTC.
"""

from datetime import date, datetime, timezone

import pytest

from haven import clock

UTC = timezone.utc


def fixed(*args):
    """A clock that always returns this UTC instant."""
    instant = datetime(*args, tzinfo=UTC)
    return lambda: instant


# --- around midnight UTC -------------------------------------------------------


def test_summer_2230_utc_is_already_tomorrow_in_amsterdam():
    assert clock.today(fixed(2026, 7, 1, 22, 30)) == date(2026, 7, 2)


def test_winter_2230_utc_is_still_today_in_amsterdam():
    assert clock.today(fixed(2026, 1, 15, 22, 30)) == date(2026, 1, 15)


def test_winter_2330_utc_is_already_tomorrow_in_amsterdam():
    assert clock.today(fixed(2026, 1, 15, 23, 30)) == date(2026, 1, 16)


def test_new_year_rolls_over_one_hour_before_utc():
    assert clock.today(fixed(2026, 12, 31, 23, 0)) == date(2027, 1, 1)


# --- clock change, spring: 29 March 2026, 02:00 CET -> 03:00 CEST -------------


def test_one_minute_before_spring_change_is_cet():
    assert clock.now(fixed(2026, 3, 29, 0, 59)).isoformat() == "2026-03-29T01:59:00+01:00"


def test_at_spring_change_jumps_to_cest():
    assert clock.now(fixed(2026, 3, 29, 1, 0)).isoformat() == "2026-03-29T03:00:00+02:00"


def test_first_scheduled_run_builds_on_spring_change_day():
    # 04:45 UTC trigger: already summer time, so 06:45 Amsterdam (§5.1.1 table).
    assert clock.now(fixed(2026, 3, 29, 4, 45)).isoformat() == "2026-03-29T06:45:00+02:00"


# --- clock change, autumn: 25 October 2026, 03:00 CEST -> 02:00 CET -----------


def test_one_minute_before_autumn_change_is_cest():
    assert clock.now(fixed(2026, 10, 25, 0, 59)).isoformat() == "2026-10-25T02:59:00+02:00"


def test_at_autumn_change_falls_back_to_cet():
    assert clock.now(fixed(2026, 10, 25, 1, 0)).isoformat() == "2026-10-25T02:00:00+01:00"


def test_second_scheduled_run_builds_on_autumn_change_day():
    # 04:45 UTC is now only 05:45 Amsterdam (too early); 05:45 UTC is 06:45.
    assert clock.now(fixed(2026, 10, 25, 4, 45)).isoformat() == "2026-10-25T05:45:00+01:00"
    assert clock.now(fixed(2026, 10, 25, 5, 45)).isoformat() == "2026-10-25T06:45:00+01:00"


def test_today_on_both_change_days():
    assert clock.today(fixed(2026, 3, 29, 1, 0)) == date(2026, 3, 29)
    assert clock.today(fixed(2026, 10, 25, 1, 0)) == date(2026, 10, 25)


# --- the injectable clock -----------------------------------------------------


def test_naive_clock_is_rejected():
    # A datetime without a timezone could mean any zone; refuse to guess.
    with pytest.raises(ValueError, match="timezone"):
        clock.now(lambda: datetime(2026, 7, 1, 12, 0))


def test_non_utc_aware_clock_is_converted():
    new_york = datetime.fromisoformat("2026-07-01T18:30:00-04:00")  # 22:30 UTC
    assert clock.today(lambda: new_york) == date(2026, 7, 2)


def test_default_clock_is_the_real_one():
    now = clock.now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() in (3600, 7200)
