"""The guard at the start of the daily job (spec §5.1.1, issue #26).

Expected values worked out by hand from the Dutch time rules: CET = UTC+1 in
winter, CEST = UTC+2 in summer; in 2026 the clocks go forward on Sunday 29 March
at 01:00 UTC and back on Sunday 25 October at 01:00 UTC.

The three scheduled triggers are 04:45, 05:45 and 06:45 UTC. A scheduled run
before 06:30 Amsterdam stops; any run stops when today's brief exists; the
06:45 UTC trigger is the day's last one (reduced brief if the AI is down, §5.6).
"""

from datetime import date, datetime, timezone

import pytest

from haven import guard, storage

UTC = timezone.utc
FIRST, SECOND, LAST = "45 4 * * *", "45 5 * * *", "45 6 * * *"


def at(*args):
    """A clock that always returns this UTC instant."""
    instant = datetime(*args, tzinfo=UTC)
    return lambda: instant


def scheduled(cron, clock, data_dir):
    return guard.decide("schedule", schedule=cron, data_dir=data_dir, utc_now=clock)


def manual(clock, data_dir, last_trigger=False):
    return guard.decide("workflow_dispatch", manual_last_trigger=last_trigger, data_dir=data_dir, utc_now=clock)


def write_brief(data_dir, day):
    path = storage.path("briefs", day, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


# --- winter time (CET, UTC+1) --------------------------------------------------


def test_winter_0445_utc_is_0545_in_amsterdam_too_early_so_it_stops(tmp_path):
    decision = scheduled(FIRST, at(2026, 11, 3, 4, 45), tmp_path)
    assert decision.build is False
    assert "before 06:30" in decision.reason


def test_winter_0545_utc_is_0645_in_amsterdam_so_it_builds(tmp_path):
    decision = scheduled(SECOND, at(2026, 11, 3, 5, 45), tmp_path)
    assert decision.build is True
    assert decision.last_trigger is False
    assert decision.day == date(2026, 11, 3)


def test_winter_0645_utc_builds_as_the_last_trigger(tmp_path):
    decision = scheduled(LAST, at(2026, 11, 3, 6, 45), tmp_path)
    assert decision.build is True
    assert decision.last_trigger is True


def test_winter_first_trigger_started_late_after_0630_builds(tmp_path):
    # GitHub often starts cron runs late: 05:31 UTC = 06:31 Amsterdam.
    decision = scheduled(FIRST, at(2026, 11, 3, 5, 31), tmp_path)
    assert decision.build is True
    assert decision.last_trigger is False


# --- summer time (CEST, UTC+2) -------------------------------------------------


def test_summer_0445_utc_is_0645_in_amsterdam_so_it_builds(tmp_path):
    decision = scheduled(FIRST, at(2026, 7, 1, 4, 45), tmp_path)
    assert decision.build is True
    assert decision.last_trigger is False
    assert decision.day == date(2026, 7, 1)


def test_summer_later_triggers_stop_once_the_first_wrote_the_brief(tmp_path):
    write_brief(tmp_path, date(2026, 7, 1))
    for cron, hour in ((SECOND, 5), (LAST, 6)):
        decision = scheduled(cron, at(2026, 7, 1, hour, 45), tmp_path)
        assert decision.build is False
        assert "already" in decision.reason


def test_summer_last_trigger_retries_when_no_brief_was_written(tmp_path):
    decision = scheduled(LAST, at(2026, 7, 1, 6, 45), tmp_path)
    assert decision.build is True
    assert decision.last_trigger is True


# --- the 06:30 edge --------------------------------------------------------------


def test_one_second_before_0630_amsterdam_stops(tmp_path):
    decision = scheduled(FIRST, at(2026, 11, 3, 5, 29, 59), tmp_path)
    assert decision.build is False


def test_exactly_0630_amsterdam_builds(tmp_path):
    decision = scheduled(FIRST, at(2026, 11, 3, 5, 30), tmp_path)
    assert decision.build is True


# --- clock-change days -----------------------------------------------------------


def test_spring_forward_day_0445_utc_is_already_0645_cest_so_it_builds(tmp_path):
    # Sunday 29 March 2026: clocks go forward at 01:00 UTC, so 04:45 UTC = 06:45 CEST.
    decision = scheduled(FIRST, at(2026, 3, 29, 4, 45), tmp_path)
    assert decision.build is True
    assert decision.day == date(2026, 3, 29)


def test_day_before_spring_forward_0445_utc_is_still_0545_cet_so_it_stops(tmp_path):
    decision = scheduled(FIRST, at(2026, 3, 28, 4, 45), tmp_path)
    assert decision.build is False


def test_fall_back_day_0445_utc_is_0545_cet_so_it_stops(tmp_path):
    # Sunday 25 October 2026: clocks go back at 01:00 UTC, so 04:45 UTC = 05:45 CET.
    decision = scheduled(FIRST, at(2026, 10, 25, 4, 45), tmp_path)
    assert decision.build is False


def test_fall_back_day_0545_utc_is_0645_cet_so_it_builds(tmp_path):
    decision = scheduled(SECOND, at(2026, 10, 25, 5, 45), tmp_path)
    assert decision.build is True
    assert decision.day == date(2026, 10, 25)


def test_day_before_fall_back_0445_utc_is_still_0645_cest_so_it_builds(tmp_path):
    decision = scheduled(FIRST, at(2026, 10, 24, 4, 45), tmp_path)
    assert decision.build is True


# --- brief already there ---------------------------------------------------------


def test_scheduled_run_stops_when_todays_brief_exists(tmp_path):
    write_brief(tmp_path, date(2026, 11, 3))
    decision = scheduled(SECOND, at(2026, 11, 3, 5, 45), tmp_path)
    assert decision.build is False
    assert decision.last_trigger is False
    assert "2026-11-03" in decision.reason


def test_yesterdays_brief_does_not_stop_today(tmp_path):
    write_brief(tmp_path, date(2026, 11, 2))
    decision = scheduled(SECOND, at(2026, 11, 3, 5, 45), tmp_path)
    assert decision.build is True


def test_only_the_brief_counts_not_a_leftover_items_file(tmp_path):
    # The runner writes all three files or none (§5.13); the brief is what says "done".
    items = storage.path("items", date(2026, 11, 3), tmp_path)
    items.parent.mkdir(parents=True)
    items.write_text("", encoding="utf-8")
    decision = scheduled(SECOND, at(2026, 11, 3, 5, 45), tmp_path)
    assert decision.build is True


# --- manual runs (workflow_dispatch) ---------------------------------------------


def test_manual_run_builds_at_any_time_even_before_0630(tmp_path):
    decision = manual(at(2026, 11, 3, 2, 0), tmp_path)  # 03:00 Amsterdam
    assert decision.build is True
    assert decision.day == date(2026, 11, 3)


def test_manual_run_stops_green_when_todays_brief_exists(tmp_path):
    write_brief(tmp_path, date(2026, 11, 3))
    decision = manual(at(2026, 11, 3, 9, 0), tmp_path)
    assert decision.build is False
    assert "already" in decision.reason


def test_manual_run_is_not_the_last_trigger_unless_the_owner_ticks_it(tmp_path):
    assert manual(at(2026, 11, 3, 9, 0), tmp_path).last_trigger is False
    assert manual(at(2026, 11, 3, 9, 0), tmp_path, last_trigger=True).last_trigger is True


def test_manual_run_uses_the_amsterdam_date_late_in_the_evening(tmp_path):
    # 22:30 UTC on 1 July = 00:30 on 2 July in Amsterdam: the 1 July brief doesn't stop it.
    write_brief(tmp_path, date(2026, 7, 1))
    decision = manual(at(2026, 7, 1, 22, 30), tmp_path)
    assert decision.build is True
    assert decision.day == date(2026, 7, 2)


# --- refused input ---------------------------------------------------------------


def test_an_unknown_cron_is_refused_so_the_last_trigger_cannot_be_missed(tmp_path):
    with pytest.raises(guard.GuardError, match="45 7"):
        scheduled("45 7 * * *", at(2026, 11, 3, 7, 45), tmp_path)


def test_a_scheduled_run_without_its_cron_is_refused(tmp_path):
    with pytest.raises(guard.GuardError):
        scheduled("", at(2026, 11, 3, 5, 45), tmp_path)


def test_an_unknown_event_is_refused(tmp_path):
    with pytest.raises(guard.GuardError, match="push"):
        guard.decide("push", data_dir=tmp_path, utc_now=at(2026, 11, 3, 5, 45))


def test_the_last_trigger_is_the_latest_of_the_three():
    assert guard.SCHEDULE_CRONS == (FIRST, SECOND, LAST)
    assert guard.LAST_TRIGGER_CRON == LAST


# --- command line: what the workflow reads -------------------------------------


def read_outputs(path):
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines())


def test_main_writes_build_true_and_the_day_for_the_workflow(tmp_path, monkeypatch, capsys):
    outputs = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    code = guard.main(["--event", "schedule", "--schedule", LAST, "--data-dir", str(tmp_path)],
                      utc_now=at(2026, 11, 3, 6, 45))
    assert code == 0
    assert read_outputs(outputs) == {"build": "true", "last_trigger": "true", "day": "2026-11-03"}
    assert "Build" in capsys.readouterr().out


def test_main_stop_exits_0_so_the_run_ends_green(tmp_path, monkeypatch, capsys):
    outputs = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    code = guard.main(["--event", "schedule", "--schedule", FIRST, "--data-dir", str(tmp_path)],
                      utc_now=at(2026, 11, 3, 4, 45))
    assert code == 0
    assert read_outputs(outputs)["build"] == "false"
    assert "Stop" in capsys.readouterr().out


def test_main_reads_the_manual_tick_box_as_text(tmp_path, monkeypatch):
    outputs = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    guard.main(["--event", "workflow_dispatch", "--schedule", "", "--manual-last-trigger", "true",
                "--data-dir", str(tmp_path)], utc_now=at(2026, 11, 3, 9, 0))
    assert read_outputs(outputs)["last_trigger"] == "true"


def test_main_fails_red_on_refused_input(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github_output"))
    code = guard.main(["--event", "schedule", "--schedule", "0 7 * * *", "--data-dir", str(tmp_path)],
                      utc_now=at(2026, 11, 3, 7, 0))
    assert code == 1
    assert not (tmp_path / "github_output").exists()


def test_main_works_without_github_output_for_a_local_try(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    code = guard.main(["--event", "workflow_dispatch", "--data-dir", str(tmp_path)],
                      utc_now=at(2026, 11, 3, 9, 0))
    assert code == 0
