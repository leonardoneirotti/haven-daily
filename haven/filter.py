"""Relevance filter (spec §5.1 step 2, §5.4). Stage 1: rules (issue #12).

Question per item: *is this relevant to a logistics planner working with the Port of
Rotterdam?* Stage 1 answers it with free, predictable rules before any AI. Every item leaves
it with an outcome and a reason:

- **KEEP**: kept by the rules (an auto-keep source); skips the AI check.
- **DROP**: dropped by the rules.
- **TO_AI**: the rules can't tell; the AI check (stage 2, #13) decides.

The rules, in this order (first match wins, so the reason is always the first rule that hit):

1. **Older than 48 h** -> dropped, reason "older than 48 h". An item exactly 48 h old is kept
   (owner's decision, 1 Nov 2026). A date-only item (`"2026-10-30"`) is aged from the **end** of
   that day, midnight Amsterdam time, so it is never dropped too early. A timestamp without a
   timezone is read as Amsterdam time. An item with **no readable date** (or a date in the
   future) is never dropped for age: the collect step has already dropped it if its link was
   seen in the last 14 days (`haven/collect.py`), so it is new.
2. **Auto-keep source** (Port Authority news, ECT; `auto_keep` in `config/sources.toml`) ->
   kept, without the word lists and without the AI check.
3. **Off-topic word in the headline** -> dropped, reason `off-topic word "<word>"`. The word
   lists are in `config/filter.toml`, one per language; the item's language picks the list.
4. Anything else -> to the AI check.

Age comes first, so a three-day-old Port Authority story is still dropped; auto-keep comes
before the words, so a badly chosen word can't drop a Rotterdam-specific item (both owner's
decisions, 1 Nov 2026).

Kept and dropped items get their decision on `Item.filter` (`{"kept", "stage": "rules",
"reason"}`), which goes into the day's items file (§6.1). Items for the AI check get theirs
from stage 2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache

from haven.clock import AMSTERDAM
from haven.config import FilterConfig, Source
from haven.feeds import Item

MAX_AGE = timedelta(hours=48)  # exactly 48 h is kept; dropped only when older (spec §5.4)

KEEP, DROP, TO_AI = "keep", "drop", "ai"

TOO_OLD = "older than 48 h"
AUTO_KEEP = "Rotterdam-specific source (auto-keep)"
GOES_TO_AI = "not decided by the rules: goes to the AI check"

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Decision:
    outcome: str  # KEEP / DROP / TO_AI
    reason: str

    def record(self) -> dict | None:
        """The `filter` field for data/items/, or None when the AI check still has to decide."""
        if self.outcome == TO_AI:
            return None
        return {"kept": self.outcome == KEEP, "stage": "rules", "reason": self.reason}


@dataclass(frozen=True)
class Ruled:
    item: Item  # with `filter` set when the rules kept or dropped it
    decision: Decision


def apply_rules(items: list[Item], sources, config: FilterConfig, now: datetime) -> list[Ruled]:
    """Stage 1 for every item, in the order given.

    `now` is the moment ages are counted to. The runner (#22) passes the collect step's
    `feeds_read_at`, when the sources were read: an earlier moment can only keep an item longer,
    never drop it too early.
    """
    by_id = {source.id: source for source in sources}
    ruled = []
    for item in items:
        decision = decide(item, by_id.get(item.source), config.off_topic.get(item.language, ()), now)
        if decision.outcome != TO_AI:
            item = replace(item, filter=decision.record())
        ruled.append(Ruled(item=item, decision=decision))
    return ruled


def decide(item: Item, source: Source | None, words, now: datetime) -> Decision:
    """The rules for one item. `source` is None for a source not in the config (never auto-kept)."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("The run time has no timezone; it must be timezone-aware (Amsterdam or UTC).")

    start = age_start(item.published)
    if start is not None and _utc(now) - _utc(start) > MAX_AGE:
        return Decision(DROP, TOO_OLD)

    if source is not None and source.auto_keep:
        return Decision(KEEP, AUTO_KEEP)

    word = off_topic_word(item.headline, words)
    if word is not None:
        return Decision(DROP, f'off-topic word "{word}"')

    return Decision(TO_AI, GOES_TO_AI)


def age_start(published: str | None) -> datetime | None:
    """The moment an item's age is counted from, or None when it has no readable date.

    - a timestamp with a timezone: that moment;
    - a timestamp without a timezone: that time in Amsterdam (owner's decision, 1 Nov 2026);
    - a date only ("2026-10-30"): the end of that day, i.e. midnight at the start of the next
      day, Amsterdam time (owner's decision, 1 Nov 2026);
    - missing or unreadable: None (like an unreadable date in the collectors, §5.8).
    """
    if not isinstance(published, str):
        return None
    try:
        if _DATE_ONLY.match(published):
            day = date.fromisoformat(published)
            return datetime.combine(day + timedelta(days=1), time(0), tzinfo=AMSTERDAM)
        moment = datetime.fromisoformat(published)
    except ValueError:
        return None
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=AMSTERDAM)
    return moment


def off_topic_word(headline: str, words) -> str | None:
    """The first word of the list found in the headline, as written in the config, or None.

    Matching ignores upper/lower case and finds whole words only ("sport" doesn't match
    "transport"). A word may be a phrase ("Champions League"; any spaces between the words).
    A `*` at the end matches any ending: "voetbal*" also finds "voetbalclub", which Dutch
    compound words need.
    """
    for word in words:
        if _pattern(word).search(headline):
            return word
    return None


@lru_cache(maxsize=None)
def _pattern(word: str) -> re.Pattern:
    prefix = word.endswith("*")
    parts = word.rstrip("*").split()
    body = r"\s+".join(re.escape(part) for part in parts)
    return re.compile(r"(?<!\w)" + body + (r"\w*" if prefix else "") + r"(?!\w)", re.IGNORECASE)


def _utc(moment: datetime) -> datetime:
    # Subtracting two datetimes that share one tzinfo ignores the UTC offset, which is wrong
    # across the clock change. In UTC the difference is always real elapsed time.
    return moment.astimezone(timezone.utc)
