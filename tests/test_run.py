"""Pipeline runner (spec §5.1, §5.6, §6, §6.1, hard rule 9; issue #22).

`haven.run.run()` with **every step faked** (collect, filter, article text, summariser, weather,
Rhine): normal run, a step or source failing, the AI unavailable, the AI unavailable on the last
trigger (reduced brief), and a second run on the same day. The strike flag is the real module,
reading the stored days in pytest's `tmp_path`. Headlines and article text are invented (hard
rule 13); no test touches the internet or the real data/ folder.
"""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from haven import run as runner
from haven import storage
from haven.clock import AMSTERDAM
from haven.collect import ArticleResult, CollectResult
from haven.config import RhineThresholds, Source
from haven.feeds import Item
from haven.filter import FilterResult
from haven.rhine import RhineResult, kaub_from_answer, lobith_no_data
from haven.strike import NO_AI_NOTE
from haven.summarise import SummaryResult, unrated
from haven.weather import WeatherResult, no_data_reading

TODAY = date(2026, 11, 20)
START = datetime(2026, 11, 20, 5, 46, 0, tzinfo=timezone.utc)  # 06:46 Amsterdam (winter time)
READ_AT = "2026-11-20T06:46:05+01:00"  # when the fake collect step "read the sources"
SECRET = "Invented article sentence that must never reach a file"

SOURCES = (
    Source(id="ect-news", name="ECT news", verdict="use", urls=("https://ect.test/",), access="html",
           language="en", auto_keep=True),
    Source(id="pin-notices", name="PIN notices to shipping", verdict="use", urls=("https://pin.test/",),
           access="rss", language="en"),
    Source(id="nl-times", name="NL Times", verdict="headline-only", urls=("https://nlt.test/",),
           access="html", language="en"),
)
THRESHOLDS = RhineThresholds(alert_at_or_below=80, watch_at_or_below=150, watch_above=460, alert_above=640)

# The §6 shape: what every brief and brief item must have (sample briefs and spec §6).
BRIEF_KEYS = {"date", "sample", "built_at", "corrections", "status", "items", "build", "ships"}
ITEM_KEYS = {"severity", "headline", "url", "source", "language", "published", "summary", "impact",
             "affects", "access", "written_by", "map", "strike"}
STATUS_KEYS = {"key", "label", "icon", "value", "level", "place", "observed_at", "source_name",
               "source_url", "note"}
BUILD_KEYS = {"sources_checked", "items_collected", "duplicates", "items_kept", "summaries",
              "ai_unavailable", "feeds_read_at", "failures", "ai_usage"}


def item(n, source="pin-notices", access="full", **extra):
    return Item(source=source, headline=f"Invented headline {n}", url=f"https://{source}.test/{n}",
                published="2026-11-20T05:10:00+01:00", language="en", access=access, **extra)


# Collected this morning: one auto-kept (ECT), two for the AI check (one kept, one dropped),
# one dropped by the rules, one headline-only kept by the AI.
AUTO = item(1, source="ect-news")
AI_KEPT = item(2)
AI_DROPPED = item(3)
RULE_DROPPED = item(4)
HEADLINE_ONLY = item(5, source="nl-times", access="headline-only")
COLLECTED = [AUTO, AI_KEPT, AI_DROPPED, RULE_DROPPED, HEADLINE_ONLY]
DECISIONS = {
    AUTO.url: {"kept": True, "stage": "rules", "reason": "Rotterdam-specific source (auto-keep)"},
    AI_KEPT.url: {"kept": True, "stage": "ai", "reason": "Fog procedure for all ships"},
    AI_DROPPED.url: {"kept": False, "stage": "ai", "reason": "Routine notice"},
    RULE_DROPPED.url: {"kept": False, "stage": "rules", "reason": "older than 48 h"},
    HEADLINE_ONLY.url: {"kept": True, "stage": "ai", "reason": "Strike at a terminal"},
}


def summary_ai(n, **extra):
    ai = {"severity": "medium", "summary": f"Own-words summary {n}.", "impact": None,
          "affects": ["Containers"], "map": None, "strike": None,
          "written_by": {"model": "claude-sonnet-5-5", "api": "batch"}}
    ai.update(extra)
    return ai


class Fake:
    """Every step of the pipeline, faked. `calls` records the order the runner called them in."""

    def __init__(self, *, collected=COLLECTED, collect_failures=(), filter_down=False, summary_down=False,
                 weather_fails=False, crash=(), summary_ai_for=None):
        self.collected = list(collected)
        self.collect_failures = list(collect_failures)
        self.filter_down = filter_down
        self.summary_down = summary_down
        self.weather_fails = weather_fails
        self.crash = set(crash)
        self.summary_ai_for = summary_ai_for or {}
        self.calls = []
        self.seen = {}

    def _maybe_crash(self, step):
        self.calls.append(step)
        if step in self.crash:
            raise RuntimeError(f"bug in the fake {step}")

    def collect(self, sources, fetcher, today, data_dir, now):
        self._maybe_crash("collect")
        self.seen["collect"] = {"today": today, "data_dir": data_dir}
        return CollectResult(items=list(self.collected), failures=list(self.collect_failures), feeds_read_at=READ_AT,
                             sources_checked=3, items_collected=len(self.collected) + 2, duplicates=2)

    def filter(self, items, sources, config, now, client):
        self._maybe_crash("filter")
        self.seen["filter"] = {"now": now, "client": client, "items": [i.url for i in items]}
        if self.filter_down:  # rules decided theirs; the AI items keep no decision
            done = [replace(i, filter=DECISIONS[i.url]) if DECISIONS[i.url]["stage"] == "rules" else i for i in items]
            return FilterResult(items=done, failures=[{"source": "AI relevance check",
                                                       "error": "AI unavailable: 3 calls in a row failed (last: HTTP 529)"}],
                                ai_unavailable=True, ai_calls=3)
        done = [replace(i, filter=DECISIONS[i.url]) for i in items]
        return FilterResult(items=done, failures=[], ai_unavailable=False, ai_calls=3, input_tokens=2580,
                            output_tokens=156)

    def article_text(self, items, sources, fetcher):
        self._maybe_crash("article_text")
        self.seen["article_text"] = [i.url for i in items]
        done = [replace(i, article_text=SECRET) if i.access == "full" else i for i in items]
        return ArticleResult(items=done, failures=[])

    def start_summary(self, items, client, known, today, *, read_at):
        self._maybe_crash("start_summary")
        self.seen["start_summary"] = {"items": list(items), "known": known, "today": today, "read_at": read_at}
        return {"items": list(items)}

    def finish_summary(self, pending):
        self._maybe_crash("finish_summary")
        items = pending["items"]
        if self.summary_down:
            return SummaryResult(items=list(items), failures=[{"source": "AI summariser",
                                                               "error": "AI unavailable: API key rejected (HTTP 401)"}],
                                 unavailable="API key rejected (HTTP 401)")
        done = [replace(i, ai=self.summary_ai_for.get(i.url, summary_ai(n))) for n, i in enumerate(items, start=1)]
        return SummaryResult(items=done, failures=[], unavailable=None, calls=0, input_tokens=9000,
                             output_tokens=1200, batch_input_tokens=9000, batch_output_tokens=1200)

    def weather(self, fetcher, read_at):
        self._maybe_crash("weather")
        if self.weather_fails:
            return WeatherResult(no_data_reading(read_at), [{"source": "Weather warnings (MeteoAlarm)",
                                                             "error": "https://meteo.test: HTTP 503"}])
        reading = no_data_reading(read_at)
        reading.update(value="No warnings", level="green", knmi_level="green",
                       note=f"Warnings at {read_at.astimezone(AMSTERDAM):%H:%M} · not live")
        return WeatherResult(reading)

    def rhine(self, fetcher, read_at):
        self._maybe_crash("rhine")
        kaub = kaub_from_answer({"timestamp": "2026-11-20T06:30:00+01:00", "value": 21.0}, read_at, THRESHOLDS)
        lobith = lobith_no_data()
        lobith.update(value=669, observed_at="2026-11-20T03:50:00+01:00")
        return RhineResult(kaub=kaub, lobith=lobith)

    def steps(self):
        return runner.Steps(collect=self.collect, filter=self.filter, article_text=self.article_text,
                            start_summary=self.start_summary, finish_summary=self.finish_summary,
                            weather=self.weather, rhine=self.rhine)


def go(tmp_path, fake=None, last_trigger=False, start=START):
    fake = fake or Fake()
    ticks = iter(start + timedelta(seconds=10 * n) for n in range(1000))  # the clock moves on a little each call
    outcome = runner.run(last_trigger=last_trigger, data_dir=tmp_path, utc_now=lambda: next(ticks),
                         client=object(), fetcher=object(), sources=SOURCES, filter_config=object(),
                         steps=fake.steps())
    return outcome, fake


def files_on_disk(tmp_path, day=TODAY):
    return [kind for kind in ("items", "status", "briefs") if storage.path(kind, day, tmp_path).exists()]


def every_file_text(tmp_path):
    return "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file())


# --- normal run ----------------------------------------------------------------------------


def test_normal_run_writes_the_three_files_once_and_exits_zero(tmp_path):
    outcome, _ = go(tmp_path)
    assert outcome.exit_code == 0
    assert outcome.result == runner.WRITTEN
    assert files_on_disk(tmp_path) == ["items", "status", "briefs"]


def test_the_brief_has_the_spec_section_6_shape(tmp_path):
    go(tmp_path)
    brief = storage.read("briefs", TODAY, tmp_path)
    assert set(brief) == BRIEF_KEYS
    assert brief["date"] == "2026-11-20"
    assert brief["sample"] is False
    assert brief["corrections"] == []
    assert brief["ships"] is None  # no AIS snapshot in v1 (#31)
    assert set(brief["build"]) == BUILD_KEYS
    for entry in brief["status"]:
        assert STATUS_KEYS <= set(entry)
    for entry in brief["items"]:
        assert set(entry) == ITEM_KEYS


def test_built_at_is_amsterdam_time_when_the_brief_was_made(tmp_path):
    go(tmp_path)
    built_at = datetime.fromisoformat(storage.read("briefs", TODAY, tmp_path)["built_at"])
    assert built_at.utcoffset() == timedelta(hours=1)  # CET in November
    assert built_at.microsecond == 0
    assert built_at > datetime.fromisoformat(READ_AT)  # after the sources were read


def test_the_brief_lists_every_kept_item_in_collection_order(tmp_path):
    go(tmp_path)
    brief = storage.read("briefs", TODAY, tmp_path)
    assert [i["url"] for i in brief["items"]] == [AUTO.url, AI_KEPT.url, HEADLINE_ONLY.url]
    assert brief["items"][0]["source"] == "ECT news"  # the source's name, as shown on the page
    assert brief["items"][0]["summary"] == "Own-words summary 1."


def test_the_items_file_has_every_collected_item_with_its_filter_decision(tmp_path):
    go(tmp_path)
    lines = storage.read("items", TODAY, tmp_path)
    assert [line["url"] for line in lines] == [i.url for i in COLLECTED]
    assert [line["filter"] for line in lines] == [DECISIONS[i.url] for i in COLLECTED]
    assert lines[0]["severity"] == "medium"  # summariser output on kept items
    assert "severity" not in lines[2]  # dropped items were never summarised


def test_the_status_file_has_every_reading_and_the_brief_the_shown_ones(tmp_path):
    go(tmp_path)
    stored = storage.read("status", TODAY, tmp_path)
    assert [r["key"] for r in stored] == ["weather", "rhine", "rhine-lobith", "strike"]
    shown = storage.read("briefs", TODAY, tmp_path)["status"]
    assert [r["key"] for r in shown] == ["weather", "rhine", "strike"]  # Lobith is stored only
    assert shown[1]["value"] == 21 and shown[1]["level"] == "red"


def test_build_block_counts_sources_items_and_summaries(tmp_path):
    go(tmp_path)
    build = storage.read("briefs", TODAY, tmp_path)["build"]
    assert build["sources_checked"] == 3
    assert build["items_collected"] == 5  # new items, as stored in data/items/
    assert build["duplicates"] == 2
    assert build["items_kept"] == 3
    assert build["summaries"] == {"batch": 3, "fallback": 0}
    assert build["ai_unavailable"] is False
    assert build["feeds_read_at"] == READ_AT
    assert build["failures"] == []


def test_build_block_records_ai_usage_for_the_cost_check(tmp_path):
    go(tmp_path)
    usage = storage.read("briefs", TODAY, tmp_path)["build"]["ai_usage"]
    assert usage["relevance_check"] == {"calls": 3, "input_tokens": 2580, "output_tokens": 156}
    assert usage["summariser"] == {"calls": 0, "input_tokens": 9000, "output_tokens": 1200,
                                   "batch_input_tokens": 9000, "batch_output_tokens": 1200}


def test_article_text_is_read_for_kept_items_only_and_never_stored(tmp_path):
    _, fake = go(tmp_path)
    assert fake.seen["article_text"] == [AUTO.url, AI_KEPT.url, HEADLINE_ONLY.url]
    assert fake.seen["start_summary"]["items"][0].article_text == SECRET  # it reached the summariser
    assert SECRET not in every_file_text(tmp_path)  # hard rule 13


def test_filter_and_summariser_count_from_when_the_sources_were_read(tmp_path):
    _, fake = go(tmp_path)
    read_at = datetime.fromisoformat(READ_AT)
    assert fake.seen["filter"]["now"] == read_at
    assert fake.seen["start_summary"]["read_at"] == read_at
    assert fake.seen["start_summary"]["today"] == TODAY
    assert fake.seen["collect"] == {"today": TODAY, "data_dir": tmp_path}


def test_weather_and_rhine_are_read_while_the_batch_runs(tmp_path):
    _, fake = go(tmp_path)
    assert fake.calls == ["collect", "filter", "article_text", "start_summary", "weather", "rhine",
                          "finish_summary"]


def test_weather_is_read_at_its_own_time_not_the_feed_time(tmp_path):
    go(tmp_path)
    weather = storage.read("briefs", TODAY, tmp_path)["status"][0]
    assert weather["observed_at"] > READ_AT  # the real read time ("Warnings at HH:MM", §5.11)


def test_known_strikes_come_from_the_stored_items_of_the_last_14_days(tmp_path):
    strike = {"state": "announced", "location": "Maasvlakte", "affects_rotterdam": True,
              "start": "2026-11-25", "end": None, "match": "new", "strike_id": "strike-2026-11-18-1"}
    storage.write("items", TODAY - timedelta(days=2), [
        {"source": "nl-times", "headline": "Invented strike headline", "url": "https://nl-times.test/s",
         "published": "2026-11-18T08:00:00+01:00", "language": "en", "access": "headline-only",
         "filter": {"kept": True, "stage": "ai", "reason": "Strike"}, **unrated(), "strike": strike}],
        data_dir=tmp_path)
    _, fake = go(tmp_path)
    assert [s["id"] for s in fake.seen["start_summary"]["known"]] == ["strike-2026-11-18-1"]


def test_strike_flag_reads_todays_items_and_the_stored_days(tmp_path):
    today_strike = {"state": "announced", "location": "Maasvlakte", "affects_rotterdam": True,
                    "start": "2026-11-20", "end": "2026-11-20", "match": "new", "strike_id": "strike-2026-11-20-1"}
    fake = Fake(summary_ai_for={HEADLINE_ONLY.url: summary_ai(3, summary=None, strike=today_strike)})
    go(tmp_path, fake)
    strike = storage.read("briefs", TODAY, tmp_path)["status"][2]
    assert strike["key"] == "strike"
    assert strike["level"] == "red"
    assert strike["items"][0]["url"] == HEADLINE_ONLY.url
    assert strike["observed_at"] == READ_AT  # the time the sources were read (§5.7)


def test_quiet_day_with_nothing_new_still_writes_a_brief(tmp_path):
    outcome, _ = go(tmp_path, Fake(collected=[]))
    assert outcome.exit_code == 0
    brief = storage.read("briefs", TODAY, tmp_path)
    assert brief["items"] == []
    assert storage.read("items", TODAY, tmp_path) == []  # "nothing collected" is recorded too


# --- a source or step failing (hard rule 9) ------------------------------------------------------


def test_failing_source_and_failing_reading_are_listed_and_the_brief_is_written(tmp_path):
    fake = Fake(collect_failures=[{"source": "NL Times", "error": "https://nlt.test/: HTTP 503"}],
                weather_fails=True)
    outcome, _ = go(tmp_path, fake)
    assert outcome.exit_code == 0
    brief = storage.read("briefs", TODAY, tmp_path)
    assert brief["build"]["failures"] == [
        {"source": "NL Times", "error": "https://nlt.test/: HTTP 503"},
        {"source": "Weather warnings (MeteoAlarm)", "error": "https://meteo.test: HTTP 503"},
    ]
    assert brief["status"][0]["value"] is None  # No data, never a guess
    assert brief["status"][1]["value"] == 21  # the Rhine is unaffected


@pytest.mark.parametrize("step, source", [
    ("collect", "Collect step"),
    ("filter", "Relevance filter"),
    ("article_text", "Article text"),
    ("start_summary", "AI summariser"),
    ("finish_summary", "AI summariser"),
    ("weather", "Weather warnings (MeteoAlarm)"),
    ("rhine", "Rhine level"),
])
def test_a_step_that_crashes_is_a_failure_line_and_the_brief_is_still_written(tmp_path, step, source):
    outcome, _ = go(tmp_path, Fake(crash={step}))
    assert outcome.exit_code == 0
    failures = storage.read("briefs", TODAY, tmp_path)["build"]["failures"]
    assert {"source": source, "error": "unexpected error (RuntimeError)"} in failures


def test_collect_crashing_gives_an_empty_day_and_no_feed_read_time(tmp_path):
    go(tmp_path, Fake(crash={"collect"}))
    brief = storage.read("briefs", TODAY, tmp_path)
    assert brief["items"] == []
    assert brief["build"]["feeds_read_at"] is None  # the next PIN gap check must not trust it
    assert brief["build"]["sources_checked"] == 0
    assert [r["key"] for r in brief["status"]] == ["weather", "rhine", "strike"]


def test_filter_crashing_keeps_nothing_and_says_so(tmp_path):
    go(tmp_path, Fake(crash={"filter"}))
    brief = storage.read("briefs", TODAY, tmp_path)
    assert brief["items"] == []
    assert all("filter" not in line for line in storage.read("items", TODAY, tmp_path))


def test_article_text_crashing_still_summarises_the_kept_items(tmp_path):
    _, fake = go(tmp_path, Fake(crash={"article_text"}))
    assert [i.url for i in fake.seen["start_summary"]["items"]] == [AUTO.url, AI_KEPT.url, HEADLINE_ONLY.url]
    assert all(i.article_text is None for i in fake.seen["start_summary"]["items"])


@pytest.mark.parametrize("step", ["start_summary", "finish_summary"])
def test_summariser_crashing_leaves_the_kept_items_unrated(tmp_path, step):
    go(tmp_path, Fake(crash={step}))
    brief = storage.read("briefs", TODAY, tmp_path)
    assert [i["severity"] for i in brief["items"]] == [None, None, None]
    assert brief["build"]["ai_unavailable"] is False  # a bug of ours, not an AI outage
    assert brief["build"]["summaries"] == {"batch": 0, "fallback": 0}


def test_rhine_crashing_gives_no_data_for_both_gauges(tmp_path):
    go(tmp_path, Fake(crash={"rhine"}))
    stored = {r["key"]: r for r in storage.read("status", TODAY, tmp_path)}
    assert stored["rhine"]["value"] is None and stored["rhine"]["level"] is None
    assert stored["rhine-lobith"]["value"] is None


def test_weather_crashing_gives_no_data(tmp_path):
    go(tmp_path, Fake(crash={"weather"}))
    weather = storage.read("briefs", TODAY, tmp_path)["status"][0]
    assert weather["key"] == "weather" and weather["value"] is None and weather["level"] is None


def test_crash_messages_name_the_kind_of_error_only(tmp_path):
    go(tmp_path, Fake(crash={"finish_summary"}))
    assert "bug in the fake" not in every_file_text(tmp_path)


# --- the AI fully unavailable (§5.6) --------------------------------------------------------


@pytest.mark.parametrize("down", [{"filter_down": True}, {"summary_down": True}])
def test_ai_unavailable_writes_nothing_and_exits_non_zero(tmp_path, down):
    outcome, _ = go(tmp_path, Fake(**down))
    assert outcome.exit_code != 0
    assert outcome.result == runner.AI_UNAVAILABLE
    assert files_on_disk(tmp_path) == []
    assert not any(tmp_path.iterdir())  # not even an empty folder


def test_ai_unavailable_in_the_filter_stops_before_any_further_request(tmp_path):
    _, fake = go(tmp_path, Fake(filter_down=True))
    assert fake.calls == ["collect", "filter"]  # no article pages, no summariser, no status requests


def test_ai_unavailable_says_why(tmp_path):
    outcome, _ = go(tmp_path, Fake(summary_down=True))
    assert "API key rejected (HTTP 401)" in outcome.message


# --- the AI unavailable on the last trigger: the reduced brief (§5.6, #6) --------------------------


@pytest.mark.parametrize("down", [{"filter_down": True}, {"summary_down": True}])
def test_last_trigger_writes_a_reduced_brief(tmp_path, down):
    outcome, _ = go(tmp_path, Fake(**down), last_trigger=True)
    assert outcome.exit_code == 0
    assert outcome.result == runner.REDUCED
    brief = storage.read("briefs", TODAY, tmp_path)
    assert set(brief) == BRIEF_KEYS
    assert brief["build"]["ai_unavailable"] is True
    assert [i["url"] for i in brief["items"]] == [AUTO.url]  # only items auto-kept by the rules
    assert all(i["severity"] is None and i["summary"] is None and i["written_by"] is None
               for i in brief["items"])  # all unrated
    assert brief["build"]["summaries"] == {"batch": 0, "fallback": 0}
    assert brief["build"]["items_kept"] == 1


@pytest.mark.parametrize("down", [{"filter_down": True}, {"summary_down": True}])
def test_reduced_brief_status_as_normal_and_strike_flag_no_data(tmp_path, down):
    go(tmp_path, Fake(**down), last_trigger=True)
    status = {r["key"]: r for r in storage.read("briefs", TODAY, tmp_path)["status"]}
    assert status["weather"]["level"] == "green"
    assert status["rhine"]["value"] == 21
    assert status["strike"]["level"] is None and status["strike"]["note"] == NO_AI_NOTE


def test_reduced_brief_lists_why_the_ai_was_unavailable(tmp_path):
    go(tmp_path, Fake(filter_down=True), last_trigger=True)
    failures = storage.read("briefs", TODAY, tmp_path)["build"]["failures"]
    assert {"source": "AI relevance check",
            "error": "AI unavailable: 3 calls in a row failed (last: HTTP 529)"} in failures


def test_reduced_brief_items_file_keeps_every_item_and_marks_the_shown_ones_unrated(tmp_path):
    go(tmp_path, Fake(filter_down=True), last_trigger=True)
    lines = {line["url"]: line for line in storage.read("items", TODAY, tmp_path)}
    assert list(lines) == [i.url for i in COLLECTED]
    assert lines[AUTO.url]["severity"] is None  # shown unrated
    assert "filter" not in lines[AI_KEPT.url]  # the AI check never decided it


def test_last_trigger_flag_changes_nothing_when_the_ai_works(tmp_path):
    outcome, _ = go(tmp_path, last_trigger=True)
    assert outcome.result == runner.WRITTEN
    assert storage.read("briefs", TODAY, tmp_path)["build"]["ai_unavailable"] is False


# --- write once ------------------------------------------------------------------------------


def test_second_run_on_the_same_day_fails_cleanly_and_changes_nothing(tmp_path):
    go(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    outcome, fake = go(tmp_path)
    assert outcome.exit_code != 0
    assert outcome.result == runner.ALREADY_WRITTEN
    assert "briefs/2026-11-20.json" in outcome.message
    assert fake.calls == []  # stops before any request or AI call
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_any_of_todays_files_already_there_stops_the_run(tmp_path):
    storage.write("items", TODAY, [], data_dir=tmp_path)  # e.g. left by a hand edit
    outcome, fake = go(tmp_path)
    assert outcome.result == runner.ALREADY_WRITTEN
    assert fake.calls == []
    assert files_on_disk(tmp_path) == ["items"]


def test_today_is_the_amsterdam_date(tmp_path):
    late_utc = datetime(2026, 11, 19, 23, 30, tzinfo=timezone.utc)  # already 20 Nov in Amsterdam
    go(tmp_path, start=late_utc)
    assert files_on_disk(tmp_path) == ["items", "status", "briefs"]


# --- the command ---------------------------------------------------------------------------


def test_main_passes_the_flags_and_returns_the_exit_code(tmp_path, monkeypatch):
    seen = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return runner.Outcome(result=runner.AI_UNAVAILABLE, exit_code=1, message="AI unavailable")

    monkeypatch.setattr(runner, "run", fake_run)
    monkeypatch.setattr(runner, "load_env", lambda: [])
    assert runner.main(["--last-trigger", "--data-dir", str(tmp_path)]) == 1
    assert seen["last_trigger"] is True
    assert seen["data_dir"] == tmp_path
