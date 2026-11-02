"""Weather status: KNMI warnings for Zuid-Holland via MeteoAlarm (spec §2.2, §4; issue #18).

Every feed here is written by us in the structure of the real MeteoAlarm feed
(`feeds-netherlands`, checked 2 Nov 2026): one entry per warning version, each with
an `alert` (identifier, msgType, status, sent, references) and two `info` blocks
(nl-NL and en-GB) carrying the area, onset/expires and the `awareness_level` /
`awareness_type` parameters. Headlines and descriptions are invented, and the tests
check that none of them reaches the reading. The network is a fake.

"Today" is the Amsterdam date of the moment the feed was read. On 2 Nov 2026
Amsterdam is on winter time (UTC+1), so 06:45 Amsterdam = 05:45 UTC.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from haven import storage, weather
from haven.fetch import Fetcher, RawResponse, TransportError

READ_AT = datetime(2026, 11, 2, 5, 45, tzinfo=timezone.utc)  # 06:45 Amsterdam
DAY = "2026-11-02"
INVENTED_HEADLINE = "Invented headline about squalls over the polder"
INVENTED_TEXT = "Invented warning text that must never be stored anywhere"


# --- building feeds in the real structure ---------------------------------------------

_counter = iter(range(1, 10_000))


def warning(
    level="yellow",
    hazard="1; Wind",
    onset=f"{DAY}T00:00:00+01:00",
    expires=f"{DAY}T23:59:59+01:00",
    sent="2026-11-01T22:10:00+01:00",
    area=("Zuid-Holland", "NL009"),
    msg_type="Alert",
    status="Actual",
    identifier=None,
    references=(),
    level_value=None,
):
    """One feed entry. `references` = identifiers this version replaces."""
    identifier = identifier or f"2.49.0.0.528.0.NL.test.{next(_counter)}"
    level_number = {"green": 1, "yellow": 2, "orange": 3, "red": 4}.get(level, 9)
    level_value = level_value or f"{level_number}; {level}; Moderate"
    area_desc, code = area

    def info(language):
        block = {
            "area": [{"areaDesc": area_desc, "geocode": [{"value": code, "valueName": "EMMA_ID"}]}],
            "category": ["Met"],
            "certainty": "Likely",
            "contact": "procesbewaker@knmi.nl",
            "description": INVENTED_TEXT,
            "effective": sent,
            "event": "Invented event name",
            "headline": INVENTED_HEADLINE,
            "language": language,
            "parameter": [
                {"valueName": "awareness_type", "value": hazard},
                {"valueName": "awareness_level", "value": level_value},
            ],
            "responseType": ["None"],
            "senderName": "KNMI Koninklijk Nederlands Meteorologisch Instituut",
            "severity": "Moderate",
            "urgency": "Future",
            "web": "https://www.knmi.nl/nederland-nu/weer/waarschuwingen",
        }
        if onset is not None:
            block["onset"] = onset
        if expires is not None:
            block["expires"] = expires
        return block

    alert = {
        "identifier": identifier,
        "incidents": "Alert",
        "info": [info("nl-NL"), info("en-GB")],
        "msgType": msg_type,
        "scope": "Public",
        "sender": "procesbewaker@knmi.nl",
        "sent": sent,
        "source": "KNMI",
        "status": status,
    }
    if references:
        alert["references"] = " ".join(f"procesbewaker@knmi.nl,{ref},2026-11-01T20:00:00+01:00" for ref in references)
    return {"alert": alert, "uuid": f"uuid-{identifier}"}


def green_day(day=DAY, sent="2026-10-28T03:08:43+01:00", area=("Zuid-Holland", "NL009")):
    """KNMI's daily 'no warning' entries: one green entry per hazard, valid the whole day."""
    hazards = ["1; Wind", "2; snow-ice", "3; Thunderstorm", "4; Fog", "10; Rain"]
    return [
        warning("green", hazard, onset=f"{day}T00:00:00+01:00", expires=f"{day}T23:59:59+01:00", sent=sent, area=area)
        for hazard in hazards
    ]


def feed(*entries):
    flat = []
    for entry in entries:
        flat.extend(entry if isinstance(entry, list) else [entry])
    return {"warnings": flat}


def reading(*entries, read_at=READ_AT):
    return weather.reading_from_feed(feed(*entries), read_at)


# --- the level: highest Zuid-Holland warning valid during the rest of today ---------


def test_no_warnings_is_normal():
    result = reading(green_day())
    assert result["level"] == "green"
    assert result["value"] == "No warnings"
    assert result["knmi_level"] == "green"
    assert result["hazards"] == []
    assert result["warnings"] == []


def test_one_yellow_warning_is_watch():
    result = reading(green_day(), warning("yellow", "1; Wind", onset=f"{DAY}T04:00:00+01:00", expires=f"{DAY}T18:00:00+01:00"))
    assert result["level"] == "amber"
    assert result["value"] == "Code yellow · Wind"
    assert result["knmi_level"] == "yellow"
    assert result["hazards"] == ["Wind"]


def test_yellow_and_orange_is_alert_and_orange_decides():
    result = reading(
        green_day(),
        warning("yellow", "4; Fog", onset=f"{DAY}T03:00:00+01:00", expires=f"{DAY}T11:00:00+01:00"),
        warning("orange", "1; Wind", onset=f"{DAY}T12:00:00+01:00", expires=f"{DAY}T22:00:00+01:00"),
    )
    assert result["level"] == "red"
    assert result["value"] == "Code orange · Wind"
    assert result["knmi_level"] == "orange"
    # both listed for the display, highest level first
    assert [(w["level"], w["hazard"]) for w in result["warnings"]] == [("orange", "Wind"), ("yellow", "Fog")]


def test_red_is_alert():
    result = reading(green_day(), warning("red", "1; Wind"))
    assert result["level"] == "red"
    assert result["value"] == "Code red · Wind"


def test_a_warning_valid_only_tomorrow_does_not_count():
    result = reading(
        green_day(),
        green_day("2026-11-03"),
        warning("orange", "1; Wind", onset="2026-11-03T00:00:00+01:00", expires="2026-11-03T12:00:00+01:00"),
    )
    assert result["level"] == "green"
    assert result["value"] == "No warnings"


def test_a_warning_that_expired_this_morning_does_not_count():
    # Owner's decision, 2 Nov 2026: a warning already over when the feed is read is ignored.
    result = reading(green_day(), warning("yellow", "4; Fog", onset=f"{DAY}T00:00:00+01:00", expires=f"{DAY}T05:00:00+01:00"))
    assert result["level"] == "green"
    assert result["warnings"] == []


def test_a_warning_ending_exactly_when_the_feed_is_read_does_not_count():
    result = reading(green_day(), warning("yellow", "4; Fog", onset=f"{DAY}T00:00:00+01:00", expires=f"{DAY}T06:45:00+01:00"))
    assert result["level"] == "green"


def test_a_warning_starting_later_today_counts():
    result = reading(green_day(), warning("yellow", "3; Thunderstorm", onset=f"{DAY}T15:00:00+01:00", expires=f"{DAY}T21:00:00+01:00"))
    assert result["level"] == "amber"
    assert result["hazards"] == ["Thunderstorm"]


def test_a_warning_that_started_yesterday_and_is_still_running_counts():
    result = reading(green_day(), warning("orange", "1; Wind", onset="2026-11-01T18:00:00+01:00", expires=f"{DAY}T09:00:00+01:00"))
    assert result["level"] == "red"


def test_a_warning_starting_at_midnight_tonight_is_tomorrows():
    result = reading(green_day(), warning("yellow", onset="2026-11-03T00:00:00+01:00", expires="2026-11-03T06:00:00+01:00"))
    assert result["level"] == "green"


def test_a_warning_starting_late_tonight_is_todays():
    result = reading(green_day(), warning("yellow", onset=f"{DAY}T23:30:00+01:00", expires="2026-11-03T06:00:00+01:00"))
    assert result["level"] == "amber"


def test_today_is_the_amsterdam_date_not_the_utc_date():
    # 23:30 UTC on 1 Nov = 00:30 on 2 Nov in Amsterdam: today is 2 Nov.
    late = datetime(2026, 11, 1, 23, 30, tzinfo=timezone.utc)
    result = reading(green_day(), warning("yellow", onset=f"{DAY}T12:00:00+01:00", expires=f"{DAY}T18:00:00+01:00"), read_at=late)
    assert result["level"] == "amber"


def test_a_missing_expiry_counts_as_still_valid():
    result = reading(green_day(), warning("yellow", expires=None))
    assert result["level"] == "amber"


def test_a_missing_onset_falls_back_to_the_time_it_became_effective():
    # effective = sent in our builder: 1 Nov 22:10, so valid today until it expires
    result = reading(green_day(), warning("yellow", onset=None, expires=f"{DAY}T12:00:00+01:00"))
    assert result["level"] == "amber"


def test_two_hazards_at_the_highest_level_are_both_named():
    result = reading(
        green_day(),
        warning("yellow", "4; Fog", onset=f"{DAY}T03:00:00+01:00", expires=f"{DAY}T11:00:00+01:00"),
        warning("yellow", "1; Wind", onset=f"{DAY}T14:00:00+01:00", expires=f"{DAY}T20:00:00+01:00"),
        warning("yellow", "4; Fog", onset=f"{DAY}T19:00:00+01:00", expires=f"{DAY}T23:00:00+01:00"),
    )
    assert result["value"] == "Code yellow · Fog, Wind"  # onset order, each hazard once
    assert result["hazards"] == ["Fog", "Wind"]


def test_the_hazard_name_is_taken_as_knmi_writes_it_with_a_capital():
    result = reading(green_day(), warning("yellow", "2; snow-ice"))
    assert result["value"] == "Code yellow · Snow-ice"


# --- only Zuid-Holland, only real and current versions --------------------------------


def test_another_province_does_not_count():
    result = reading(green_day(), warning("red", area=("Zeeland", "NL010")))
    assert result["level"] == "green"


def test_the_hook_of_holland_coastal_area_does_not_count():
    # Owner's decision, 2 Nov 2026: Zuid-Holland only for now (spec §2.2).
    result = reading(green_day(), warning("yellow", area=("Hook of Holland", "NL802")))
    assert result["level"] == "green"


def test_zuid_holland_is_found_by_its_code_even_if_the_name_changes():
    result = reading(green_day(), warning("yellow", area=("Zuid Holland (South Holland)", "NL009")))
    assert result["level"] == "amber"


def test_a_warning_replaced_by_an_update_does_not_count():
    old = warning("orange", "1; Wind", identifier="ZH-wind-1")
    new = warning("yellow", "1; Wind", identifier="ZH-wind-2", msg_type="Update", references=["ZH-wind-1"], sent=f"{DAY}T05:00:00+01:00")
    result = reading(green_day(), old, new)
    assert result["level"] == "amber"
    assert result["issued_at"] == f"{DAY}T05:00:00+01:00"


def test_an_update_down_to_green_clears_the_warning():
    old = warning("yellow", "4; Fog", identifier="ZH-fog-1")
    new = warning("green", "4; Fog", identifier="ZH-fog-2", msg_type="Update", references=["ZH-fog-1"])
    assert reading(green_day(), old, new)["level"] == "green"


def test_a_cancelled_warning_does_not_count():
    old = warning("orange", "1; Wind", identifier="ZH-wind-1")
    cancel = warning("orange", "1; Wind", identifier="ZH-wind-cancel", msg_type="Cancel", references=["ZH-wind-1"])
    assert reading(green_day(), old, cancel)["level"] == "green"


def test_a_test_or_exercise_message_does_not_count():
    result = reading(green_day(), warning("red", status="Test"), warning("red", status="Exercise"))
    assert result["level"] == "green"


# --- what the reading holds (MeteoAlarm display requirements, spec §2.2) --------------


def test_the_reading_has_every_field_the_display_needs():
    result = reading(
        green_day(),
        warning("yellow", "1; Wind", onset=f"{DAY}T04:00:00+01:00", expires=f"{DAY}T18:00:00+01:00", sent=f"{DAY}T03:15:00+01:00"),
    )
    assert result["key"] == "weather"
    assert result["label"] == "Weather warnings"
    assert result["icon"] == "wind"
    assert result["place"] == "Zuid-Holland"
    assert result["source_name"] == "KNMI via MeteoAlarm"  # "KNMI" shown as the source
    assert result["source_url"] == "https://www.meteoalarm.org"  # link to meteoalarm.org
    assert result["issued_at"] == f"{DAY}T03:15:00+01:00"  # time of issue
    assert result["knmi_level"] == "yellow"  # original level ...
    assert result["hazards"] == ["Wind"]  # ... + hazard
    assert result["observed_at"] == f"{DAY}T06:45:00+01:00"  # when we read it, Amsterdam
    assert result["note"] == "Warnings at 06:45 · not live"
    assert result["warnings"] == [
        {
            "level": "yellow",
            "hazard": "Wind",
            "onset": f"{DAY}T04:00:00+01:00",
            "expires": f"{DAY}T18:00:00+01:00",
            "issued_at": f"{DAY}T03:15:00+01:00",
        }
    ]


def test_times_are_stored_in_amsterdam_time():
    utc_sent = warning("yellow", sent="2026-11-02T02:15:00+00:00", onset="2026-11-02T03:00:00Z", expires="2026-11-02T17:00:00Z")
    result = reading(green_day(), utc_sent)
    assert result["issued_at"] == f"{DAY}T03:15:00+01:00"
    assert result["warnings"][0]["onset"] == f"{DAY}T04:00:00+01:00"
    assert result["warnings"][0]["expires"] == f"{DAY}T18:00:00+01:00"


def test_with_no_warnings_the_time_of_issue_is_knmis_newest_entry_for_today():
    result = reading(green_day(sent="2026-10-28T03:08:43+01:00"), green_day(sent="2026-11-01T00:04:00+01:00"))
    assert result["issued_at"] == "2026-11-01T00:04:00+01:00"


def test_the_warning_text_never_reaches_the_reading():
    result = reading(green_day(), warning("orange"))
    dumped = json.dumps(result)
    assert "Invented" not in dumped
    for word in ("headline", "description", "event"):
        assert word not in dumped


def test_the_reading_can_be_stored_in_data_status(tmp_path):
    result = reading(green_day(), warning("yellow"))
    storage.write("status", date(2026, 11, 2), {"readings": [result]}, data_dir=tmp_path)


def test_the_time_the_feed_was_read_must_have_a_timezone():
    with pytest.raises(ValueError):
        weather.reading_from_feed(feed(green_day()), datetime(2026, 11, 2, 6, 45))


# --- when the feed can't be used: No data, never a guess ------------------------------


def assert_no_data(result):
    assert result["value"] is None
    assert result["level"] is None
    assert result["knmi_level"] is None
    assert result["issued_at"] is None
    assert result["hazards"] == []
    assert result["warnings"] == []
    assert result["note"] is None
    assert result["source_url"] == "https://www.meteoalarm.org"


def test_no_zuid_holland_entry_for_today_is_no_data_not_normal():
    with pytest.raises(weather.WeatherFeedError, match="no Zuid-Holland entry for today"):
        reading(green_day(area=("Zeeland", "NL010")), green_day("2026-11-03"))


def test_an_empty_feed_is_no_data():
    with pytest.raises(weather.WeatherFeedError, match="no Zuid-Holland entry for today"):
        weather.reading_from_feed({"warnings": []}, READ_AT)


def test_an_unreadable_level_in_a_zuid_holland_warning_is_no_data():
    with pytest.raises(weather.WeatherFeedError, match="awareness level"):
        reading(green_day(), warning(level_value="purple"))


def test_an_unknown_colour_is_no_data():
    with pytest.raises(weather.WeatherFeedError, match="awareness level"):
        reading(green_day(), warning(level_value="5; purple; Extreme"))


def test_an_unreadable_time_in_a_zuid_holland_warning_is_no_data():
    with pytest.raises(weather.WeatherFeedError, match="time"):
        reading(green_day(), warning(expires="tomorrow evening"))


def test_a_time_without_a_timezone_is_unreadable():
    with pytest.raises(weather.WeatherFeedError, match="time"):
        reading(green_day(), warning(expires=f"{DAY}T18:00:00"))


@pytest.mark.parametrize("data", [[], {"alerts": []}, {"warnings": "none"}, {"warnings": [{"no_alert": 1}]}])
def test_json_that_is_not_the_warnings_feed_is_no_data(data):
    with pytest.raises(weather.WeatherFeedError):
        weather.reading_from_feed(data, READ_AT)


# --- read_weather: fetch + reading, failures instead of exceptions --------------------


class FakeNet:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, headers))
        if url.endswith("/robots.txt"):
            return RawResponse(404, {}, b"")
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def fetcher(answer):
    net = FakeNet(answer)
    return Fetcher(transport=net, clock=lambda: 0.0, sleep=lambda s: None), net


def json_response(data, status=200):
    body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
    return RawResponse(status, {"content-type": "application/json; charset=utf-8"}, body)


def test_read_weather_fetches_the_netherlands_feed_politely():
    fetch, net = fetcher(json_response(feed(green_day(), warning("yellow"))))
    result = weather.read_weather(fetch, READ_AT)
    assert result.reading["level"] == "amber"
    assert result.failures == []
    urls = [url for url, _ in net.calls]
    assert urls == ["https://feeds.meteoalarm.org/robots.txt", "https://feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands"]
    assert all(headers["User-Agent"].startswith("HavenDaily/") for _, headers in net.calls)


@pytest.mark.parametrize(
    "answer, problem",
    [
        (TransportError("connection refused"), "connection refused (tried twice)"),
        (json_response({}, status=503), "HTTP 503"),
        (json_response(b"<html>Bot check</html>"), "not JSON"),
        (json_response({"warnings": []}), "no Zuid-Holland entry for today"),
    ],
)
def test_a_feed_that_fails_gives_no_data_and_a_failure_line(answer, problem):
    fetch, _ = fetcher(answer)
    result = weather.read_weather(fetch, READ_AT)
    assert_no_data(result.reading)
    assert result.reading["observed_at"] == f"{DAY}T06:45:00+01:00"
    assert len(result.failures) == 1
    assert result.failures[0]["source"] == "Weather warnings (MeteoAlarm)"
    assert problem in result.failures[0]["error"]


def test_a_robots_block_gives_no_data():
    net_answers = {
        "https://feeds.meteoalarm.org/robots.txt": RawResponse(200, {}, b"User-agent: *\nDisallow: /api/\n"),
    }

    def net(url, headers, timeout):
        if url in net_answers:
            return net_answers[url]
        raise AssertionError("a disallowed page was requested")

    fetch = Fetcher(transport=net, clock=lambda: 0.0, sleep=lambda s: None)
    result = weather.read_weather(fetch, READ_AT)
    assert_no_data(result.reading)
    assert "robots.txt" in result.failures[0]["error"]


def test_a_bug_of_ours_gives_no_data_not_a_crash(monkeypatch):
    def broken(data, read_at):
        raise KeyError("oops")

    monkeypatch.setattr(weather, "reading_from_feed", broken)
    fetch, _ = fetcher(json_response(feed(green_day())))
    result = weather.read_weather(fetch, READ_AT)
    assert_no_data(result.reading)
    assert "unexpected error (KeyError" in result.failures[0]["error"]
