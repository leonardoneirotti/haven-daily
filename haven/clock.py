"""Today and now in Amsterdam time (spec §5.1.1).

GitHub runs the job in UTC, but a brief belongs to an Amsterdam date: 22:30 UTC
on a summer evening is already tomorrow in Rotterdam. `zoneinfo` knows the
Dutch summer/winter time rules, so the clock change needs no code of our own.

Every function takes an optional `utc_now` clock (a function returning a
timezone-aware datetime). Tests pass a fixed instant; real runs use the system
clock.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

AMSTERDAM = ZoneInfo("Europe/Amsterdam")

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    """The real current time, in UTC."""
    return datetime.now(timezone.utc)


def now(utc_now: Clock = system_clock) -> datetime:
    """Current Amsterdam date and time, with its UTC offset (+01:00 or +02:00)."""
    instant = utc_now()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("The clock returned a datetime without a timezone; it must be timezone-aware (UTC).")
    return instant.astimezone(AMSTERDAM)


def today(utc_now: Clock = system_clock) -> date:
    """Current Amsterdam date: the date a brief written now belongs to."""
    return now(utc_now).date()
