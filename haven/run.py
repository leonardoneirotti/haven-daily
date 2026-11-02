"""Pipeline runner: collect → filter → summarise → status → brief, written once (spec §5.1, §5.6; issue #22).

`python -m haven.run [--last-trigger] [--data-dir DIR]` is what the morning job (#26) runs. It
writes today's three files **once** (`haven.storage.write_day`, all or nothing, the brief last):

- `data/items/<today>.jsonl`: every item collected this morning, kept and dropped, with its filter
  decision and (kept items) the summariser's output (§6.1);
- `data/status/<today>.json`: every status reading (weather, Kaub, Lobith, strike flag), No data
  as `null` (§6.1);
- `data/briefs/<today>.json`: the brief (§6): `sample: false`, `built_at` (Amsterdam time),
  `corrections: []`, the shown readings, every kept item, and the `build` block.

The order, and why:

1. **Collect** (`haven.collect.run_collect`): every source, duplicates of the last 14 days dropped.
   Its `feeds_read_at` is "the run" for the filter's 48 h and 12 h rules and for the summariser.
2. **Filter** (`haven.filter.run_filter`): rules, then Haiku for what the rules can't decide.
3. **Article text** (`haven.collect.add_article_text`) for **kept items only**, in memory.
4. **Summariser, sent** (`haven.summarise.start_batch`): one batch, returns at once.
5. **Weather and Rhine** (`haven.weather`, `haven.rhine`) while the batch runs, so they cost no
   time (the 20 minutes count from when the batch was sent, §5.5). Each is read at its own time.
6. **Summariser, collected** (`haven.summarise.finish_batch`): waits at most 20 minutes, Haiku
   fallback for what the batch didn't answer.
7. **Strike flag** (`haven.strike.read_strike_flag`) from today's items and the stored days.
8. **Write** the three files.

**Each step catches its own errors** (hard rule 9): the steps already turn a source or API problem
into failure lines; a crash inside a step (a bug of ours) becomes one more line, `unexpected error
(<type>)`, naming the kind of error only (the traceback goes to the job log), and the run goes on
with what that step would give on a bad day: no items, No data, items unrated.

**The AI fully unavailable** (§5.6): the relevance check or the summariser reports the AI as
unavailable (no key, key rejected, the first 3 calls failing). Then **nothing is written** and the
run exits 1, so GitHub notifies the owner and the next trigger retries. An unavailable relevance
check stops the run at once: no article pages, no batch, no status requests. **With
`--last-trigger`** (the 06:45 UTC run, #26) a **reduced brief** is written instead: status as
normal, strike flag No data, only the items auto-kept by the rules, all unrated,
`build.ai_unavailable: true` (#6).

**Write once:** if any of today's three files already exists, the run stops before any request
or AI call and exits 2, changing nothing.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from haven import clock, storage
from haven.collect import ArticleResult, CollectResult, add_article_text, run_collect
from haven.config import load_filter, load_sources
from haven.env import load_env
from haven.fetch import Fetcher
from haven.filter import AI_CHECK, FilterResult, ai_client, run_filter
from haven.rhine import RhineResult, kaub_no_data, lobith_no_data, read_rhine
from haven.strike import FAILURE_SOURCE as STRIKE_STEP
from haven.strike import StrikeFlag, StrikeResult, read_strike_flag, reading
from haven.summarise import SUMMARISER, SummaryResult, brief_item, finish_batch, known_strikes, start_batch, unrated
from haven.weather import FAILURE_SOURCE as WEATHER_STEP
from haven.weather import WeatherResult, no_data_reading, read_weather

__all__ = ["AI_UNAVAILABLE", "ALREADY_WRITTEN", "REDUCED", "WRITTEN", "Outcome", "Steps", "main", "run"]

WRITTEN = "written"  # a normal brief
REDUCED = "reduced"  # the AI was unavailable on the last trigger: a reduced brief (§5.6)
AI_UNAVAILABLE = "ai-unavailable"  # nothing written; the next trigger retries
ALREADY_WRITTEN = "already-written"  # today's files exist; nothing done
EXIT_CODES = {WRITTEN: 0, REDUCED: 0, AI_UNAVAILABLE: 1, ALREADY_WRITTEN: 2}

# The `source` of a failure line when a step itself crashes (the steps name their own otherwise).
COLLECT_STEP = "Collect step"
FILTER_STEP = "Relevance filter"
ARTICLE_STEP = "Article text"
RHINE_STEP = "Rhine level"
KNOWN_STRIKE_DAYS = 14  # the summariser's known-strike list (§5.5, §5.7)
_AI_DOWN = "AI unavailable: "  # how the filter and summariser start their outage line

FROM_ENV = object()  # `client` default: make one from ANTHROPIC_API_KEY (None = no key = AI unavailable)


@dataclass(frozen=True)
class Steps:
    """The pipeline's steps, replaceable in tests (each with the real function's signature)."""
    collect: Callable = run_collect  # (sources, fetcher, today, data_dir=, now=) -> CollectResult
    filter: Callable = run_filter  # (items, sources, config, now, client) -> FilterResult
    article_text: Callable = add_article_text  # (items, sources, fetcher) -> ArticleResult
    start_summary: Callable = start_batch  # (items, client, known, today, read_at=) -> pending batch
    finish_summary: Callable = finish_batch  # (pending) -> SummaryResult
    weather: Callable = read_weather  # (fetcher, read_at) -> WeatherResult
    rhine: Callable = read_rhine  # (fetcher, read_at) -> RhineResult


@dataclass(frozen=True)
class Outcome:
    result: str  # WRITTEN / REDUCED / AI_UNAVAILABLE / ALREADY_WRITTEN
    exit_code: int
    message: str
    brief: dict | None = None
    paths: tuple[Path, ...] = field(default=())


def _outcome(result: str, message: str, brief: dict | None = None, paths=()) -> Outcome:
    return Outcome(result=result, exit_code=EXIT_CODES[result], message=message, brief=brief, paths=tuple(paths))


def _guarded(source: str, failures: list[dict], call: Callable):
    """`call()`, or None after a crash, which becomes one failure line (kind of error only)."""
    try:
        return call()
    except Exception as error:  # a bug of ours must not stop the morning run (hard rule 9)
        traceback.print_exc(file=sys.stderr)  # the details go to the job log, not the public page
        failures.append({"source": source, "error": f"unexpected error ({type(error).__name__})"})
        return None


def run(*, last_trigger: bool = False, data_dir: Path = storage.DATA_DIR, utc_now=clock.system_clock,
        client=FROM_ENV, fetcher=None, sources=None, filter_config=None, steps: Steps | None = None) -> Outcome:
    """The morning pipeline, once. Writes today's three files or nothing; never half of them."""
    steps = steps or Steps()
    data_dir = Path(data_dir)
    today = clock.today(utc_now)

    def now() -> datetime:
        return clock.now(utc_now).replace(microsecond=0)

    existing = [f"{p.parent.name}/{p.name}" for p in (storage.path(k, today, data_dir) for k in storage.WRITE_ORDER)
                if p.exists()]
    if existing:
        return _outcome(ALREADY_WRITTEN, f"{', '.join(existing)} already exists: a day's files are written once. "
                                         "Nothing was done.")

    sources = load_sources() if sources is None else sources
    filter_config = load_filter() if filter_config is None else filter_config
    fetcher = Fetcher() if fetcher is None else fetcher
    client = ai_client() if client is FROM_ENV else client
    failures: list[dict] = []  # in pipeline order, for build.failures
    started = now()

    # 1. Collect.
    collected = _guarded(COLLECT_STEP, failures,
                         lambda: steps.collect(sources, fetcher, today, data_dir=data_dir, now=now))
    if collected is None:  # no items, and no feed read time the next PIN gap check could trust
        collected = CollectResult(items=[], failures=[], feeds_read_at=None, sources_checked=0,
                                  items_collected=0, duplicates=0)
    failures.extend(collected.failures)
    read_at = datetime.fromisoformat(collected.feeds_read_at) if collected.feeds_read_at else started

    # 2. Filter.
    filtered = _guarded(FILTER_STEP, failures,
                        lambda: steps.filter(collected.items, sources, filter_config, read_at, client))
    if filtered is None:  # nothing decided, so nothing kept
        filtered = FilterResult(items=list(collected.items), failures=[], ai_unavailable=False)
    failures.extend(filtered.failures)
    items = list(filtered.items)  # every collected item, in collection order
    kept_at = [n for n, item in enumerate(items) if item.filter and item.filter.get("kept")]
    ai_down = filtered.ai_unavailable
    if ai_down and not last_trigger:
        return _ai_unavailable(failures)

    # 3-4. Article text for the kept items, then send the batch.
    pending = texts = None
    if not ai_down:
        texts = _guarded(ARTICLE_STEP, failures, lambda: steps.article_text([items[n] for n in kept_at], sources, fetcher))
        if texts is None:
            texts = ArticleResult(items=[items[n] for n in kept_at], failures=[])
        failures.extend(texts.failures)
        known = _guarded(SUMMARISER, failures, lambda: _known_strikes(today, data_dir)) or []
        pending = _guarded(SUMMARISER, failures,
                           lambda: steps.start_summary(texts.items, client, known, today, read_at=read_at))

    # 5. Weather and Rhine while the batch runs; their failure lines go after the summariser's.
    status_failures: list[dict] = []
    weather = _guarded(WEATHER_STEP, status_failures, lambda: steps.weather(fetcher, now()))
    weather = weather or WeatherResult(no_data_reading(now()))
    rhine = _guarded(RHINE_STEP, status_failures, lambda: steps.rhine(fetcher, now()))
    rhine = rhine or RhineResult(kaub=kaub_no_data(), lobith=lobith_no_data())

    # 6. Collect the summaries.
    summary = None
    if not ai_down:
        if pending is not None:
            summary = _guarded(SUMMARISER, failures, lambda: steps.finish_summary(pending))
        if summary is None:  # the summariser crashed: the kept items stay, unrated
            summary = SummaryResult(items=[replace(item, ai=unrated()) for item in texts.items], failures=[],
                                    unavailable=None)
        failures.extend(summary.failures)
        ai_down = summary.unavailable is not None
        if ai_down and not last_trigger:
            return _ai_unavailable(failures)
        if not ai_down:
            for n, done in zip(kept_at, summary.items):
                items[n] = done

    # The reduced brief (§5.6): only the items the rules auto-kept, all unrated.
    if ai_down:
        shown_at = [n for n in kept_at if items[n].filter.get("stage") == "rules"]
        for n in shown_at:
            items[n] = replace(items[n], ai=unrated())
        summaries = {"batch": 0, "fallback": 0}
    else:
        shown_at = kept_at
        summaries = summary.summaries

    # 7. Strike flag, from today's items and the stored days.
    records = [item.record() for item in items]
    strike = _guarded(STRIKE_STEP, status_failures, lambda: read_strike_flag(
        records, today, read_at, sources, ai_unavailable=ai_down, data_dir=data_dir))
    strike = strike or StrikeResult(reading(StrikeFlag(None, None), read_at))
    status_failures.extend(weather.failures + rhine.failures + strike.failures)

    # 8. The brief, and the three files.
    brief = {
        "date": today.isoformat(),
        "sample": False,
        "built_at": now().isoformat(),
        "corrections": [],
        "status": [weather.reading, *rhine.shown, strike.reading],
        "items": [brief_item(items[n], sources) for n in shown_at],
        "build": {
            "sources_checked": collected.sources_checked,
            "items_collected": len(collected.items),
            "duplicates": collected.duplicates,
            "items_kept": len(shown_at),
            "summaries": summaries,
            "ai_unavailable": ai_down,
            "feeds_read_at": collected.feeds_read_at,
            "failures": failures + status_failures,
            "ai_usage": _usage(filtered, summary),
        },
        "ships": None,  # the AIS snapshot is v2 (#31)
    }
    stored_status = [weather.reading, *rhine.stored, strike.reading]
    try:
        paths = storage.write_day(today, {"items": records, "status": stored_status, "briefs": brief}, data_dir)
    except storage.AlreadyWrittenError as error:  # another run wrote today's files in the meantime
        return _outcome(ALREADY_WRITTEN, f"{error}. Nothing was written.")
    kind = "Reduced brief (AI unavailable)" if ai_down else "Brief"
    return _outcome(REDUCED if ai_down else WRITTEN,
                    f"{kind} for {today.isoformat()} written: {len(collected.items)} new items, "
                    f"{len(shown_at)} in the brief, {len(brief['build']['failures'])} failure lines.",
                    brief, paths)


def _ai_unavailable(failures: list[dict]) -> Outcome:
    why = [f["error"][len(_AI_DOWN):] for f in failures if f["error"].startswith(_AI_DOWN)]
    return _outcome(AI_UNAVAILABLE, f"AI unavailable ({'; '.join(why) or 'no reason given'}): nothing was written. "
                                    "The next trigger retries; the last one (--last-trigger) writes a reduced brief.")


def _known_strikes(today: date, data_dir: Path) -> list[dict]:
    """The summariser's known strikes from the 14 stored days before today; a broken day is skipped
    (the duplicate check has already reported it)."""
    days = []
    for back in range(1, KNOWN_STRIKE_DAYS + 1):
        day = today - timedelta(days=back)
        try:
            records = storage.read("items", day, data_dir)
        except storage.StorageError:
            continue
        if records is not None:
            days.append((day, records))
    return known_strikes(days)


def _usage(filtered: FilterResult, summary: SummaryResult | None) -> dict:
    """Calls and tokens per AI step, for the week-one cost check (§2 AI budget)."""
    summary = summary or SummaryResult(items=[], failures=[], unavailable=None)
    return {
        "relevance_check": {"calls": filtered.ai_calls, "input_tokens": filtered.input_tokens,
                            "output_tokens": filtered.output_tokens},
        "summariser": {"calls": summary.calls, "input_tokens": summary.input_tokens,
                       "output_tokens": summary.output_tokens, "batch_input_tokens": summary.batch_input_tokens,
                       "batch_output_tokens": summary.batch_output_tokens},
    }


def main(argv=None) -> int:
    """`python -m haven.run [--last-trigger] [--data-dir DIR]`. Exit 0 = brief written, 1 = AI
    unavailable (nothing written), 2 = today's files already exist (nothing done)."""
    parser = argparse.ArgumentParser(prog="python -m haven.run", description=__doc__.splitlines()[0])
    parser.add_argument("--last-trigger", action="store_true",
                        help="the day's last scheduled run: if the AI is unavailable, write a reduced brief")
    parser.add_argument("--data-dir", type=Path, default=storage.DATA_DIR,
                        help="where data/items, data/status and data/briefs live (default: the repo's data/)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # headlines and "·" on a Windows console
    load_env()
    outcome = run(last_trigger=args.last_trigger, data_dir=args.data_dir)
    print(outcome.message)
    if outcome.brief is not None:
        build = outcome.brief["build"]
        usage = build["ai_usage"]
        print(f"Summaries: {build['summaries']['batch']} batch, {build['summaries']['fallback']} fallback. "
              f"AI tokens: relevance check {usage['relevance_check']['input_tokens']:,} in / "
              f"{usage['relevance_check']['output_tokens']:,} out; summariser "
              f"{usage['summariser']['input_tokens']:,} in / {usage['summariser']['output_tokens']:,} out.")
        for failure in build["failures"]:
            print(f"FAILURE  {failure['source']}: {failure['error']}")
        for path in outcome.paths:
            print(f"Wrote {path}")
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
