"""Weather status: KNMI warnings for the Port of Rotterdam area via MeteoAlarm (spec §2.2, §4, §5.11;
issues #18 and #121).

Every feed here is written by us in the structure of the real MeteoAlarm feed as it is since
November 2026 (`feeds-netherlands`, checked 23 Nov 2026): a few regional warnings, one entry per
warning version, each with an `alert` (identifier, msgType, status, sent, references) and `info`
blocks (nl-NL and en-GB) carrying the **area as free text plus a CAP polygon** ("lat,lon lat,lon
…", no geocode), onset/expires and the `awareness_level` / `awareness_type` parameters. There is no
entry at all for an area without a warning. Headlines and descriptions are invented, and the
tests check that none of them reaches the reading. The network is a fake.

The rule (owner, 23 Nov 2026, #121):
- a warning counts when its polygon contains **any of the 41 places** in config/places.toml, never
  by its free-text area name;
- no entry for our area means **No warnings** only if the feed loaded, parsed in the expected shape
  and is fresh; otherwise **No data**. Never Normal on doubt.

"Today" is the Amsterdam date of the moment the feed was read. On 2 Nov 2026 Amsterdam is on
winter time (UTC+1), so 06:45 Amsterdam = 05:45 UTC.
"""

import json
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from haven import storage, weather
from haven.config import load_places
from haven.fetch import Fetcher, RawResponse, TransportError

READ_AT = datetime(2026, 11, 2, 5, 45, tzinfo=timezone.utc)  # 06:45 Amsterdam
DAY = "2026-11-02"
INVENTED_HEADLINE = "Invented headline about squalls over the polder"
INVENTED_TEXT = "Invented warning text that must never be stored anywhere"
PLACES = load_places()


def box(south, west, north, east):
    """A closed CAP polygon, "lat,lon" pairs separated by spaces."""
    return f"{south},{west} {south},{east} {north},{east} {north},{west} {south},{west}"


# Areas, as polygons. The 41 places lie between 51.85 and 52.15 N, 3.50 and 4.50 E.
PORT = box(51.80, 3.45, 52.20, 4.60)                  # all of the port area
LEIDEN = box(52.20, 4.40, 52.30, 4.60)                # in South Holland, but none of our places
GRONINGEN = box(53.10, 6.40, 53.30, 6.80)             # far away
SEA = min(PLACES, key=lambda p: p.lon)                # the westernmost place: out at sea
COASTAL = box(SEA.lat - 0.02, SEA.lon - 0.02, SEA.lat + 0.02, SEA.lon + 0.02)


# --- building feeds in the new structure -----------------------------------------------------

_counter = iter(range(1, 10_000))


def warning(
    level="yellow",
    hazard="1; Wind",
    onset=f"{DAY}T00:00:00+01:00",
    expires=f"{DAY}T23:59:59+01:00",
    sent="2026-11-01T22:10:00+01:00",
    area=("South Holland and Utrecht and parts of: North Holland", PORT),
    msg_type="Alert",
    status="Actual",
    identifier=None,
    references=(),
    level_value=None,
    polygons=None,
):
    """One feed entry. `area` = (free text, polygon); `polygons` overrides the polygon list."""
    identifier = identifier or f"2.49.0.0.528.0.NL.test.{next(_counter)}"
    level_number = {"green": 1, "yellow": 2, "orange": 3, "red": 4}.get(level, 9)
    level_value = level_value or f"{level_number}; {level}; Moderate"
    area_desc, polygon = area
    area_block = {"areaDesc": area_desc, "polygon": [polygon] if polygons is None else polygons}

    def info(language):
        block = {
            "area": [dict(area_block)],
            "category": ["Met"],
            "certainty": "Likely",
            "contact": "procesbewaker@knmi.nl",
            "description": INVENTED_TEXT,
            "event": "Invented event name",
            "headline": INVENTED_HEADLINE,
            "instruction": "Invented instruction",
            "language": language,
            "parameter": [
                {"valueName": "awareness_type", "value": hazard},
                {"valueName": "awareness_level", "value": level_value},
            ],
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
        "info": [info("nl-NL"), info("en-GB")],
        "msgType": msg_type,
        "scope": "Public",
        "sender": "procesbewaker@knmi.nl",
        "sent": sent,
        "status": status,
    }
    if references:
        alert["references"] = " ".join(f"procesbewaker@knmi.nl,{ref},2026-11-01T20:00:00+01:00" for ref in references)
    return {"alert": alert, "uuid": f"uuid-{identifier}"}


def feed(*entries):
    return {"warnings": list(entries)}


def reading(*entries, read_at=READ_AT):
    return weather.reading_from_feed(feed(*entries), read_at)


# --- which warnings count: the polygon contains one of our places ----------------------------


def test_a_warning_over_the_port_counts():
    result = reading(warning("yellow", "1; Wind"))
    assert result["level"] == "amber"
    assert result["value"] == "Code yellow · Wind"


def test_a_polygon_containing_just_one_of_the_41_places_counts():
    place = next(p for p in PLACES if p.id == "waalhaven")
    tiny = box(place.lat - 0.003, place.lon - 0.003, place.lat + 0.003, place.lon + 0.003)
    assert sum(weather.contains(weather.parse_polygon(tiny), p.lat, p.lon) for p in PLACES) == 1
    assert reading(warning("orange", area=("Parts of: South Holland", tiny)))["level"] == "red"


def test_a_coastal_warning_over_the_anchorages_counts():
    # Owner's rule, 23 Nov 2026: any of the 41 places, so places at sea too (replaces the
    # 2 Nov decision to leave the Hook of Holland coastal warnings out, spec §11).
    assert reading(warning("yellow", area=("Coastal waters", COASTAL)))["level"] == "amber"


def test_a_warning_elsewhere_in_south_holland_does_not_count():
    # The free-text name says South Holland; the polygon covers none of our places.
    result = reading(warning("red", area=("South Holland and Utrecht", LEIDEN)))
    assert result["level"] == "green" and result["value"] == "No warnings"


def test_the_area_name_is_never_used_only_the_polygon():
    assert reading(warning("red", area=("Zuid-Holland", GRONINGEN)))["level"] == "green"


def test_an_area_with_several_polygons_counts_if_any_contains_a_place():
    assert reading(warning("yellow", polygons=[GRONINGEN, PORT]))["level"] == "amber"


def test_a_polygon_given_without_its_closing_point_still_works():
    open_ring = " ".join(PORT.split()[:-1])
    assert reading(warning("yellow", area=("Port", open_ring)))["level"] == "amber"


def test_polygon_points_are_latitude_then_longitude():
    # CAP order is "lat,lon". Swapped, the port box lands in the sea off Somalia: no place inside.
    swapped = " ".join(",".join(reversed(pair.split(","))) for pair in PORT.split())
    assert reading(warning("red", area=("Swapped", swapped)))["level"] == "green"


@pytest.mark.parametrize("lat, lon, inside", [
    (52.0, 4.0, True), (51.7, 4.0, False), (52.0, 4.7, False), (52.25, 4.0, False),
])
def test_the_point_in_polygon_check(lat, lon, inside):
    assert weather.contains(weather.parse_polygon(PORT), lat, lon) is inside


# --- the level: highest warning for the port area valid during the rest of today ------------


def test_no_entry_for_our_area_is_no_warnings():
    result = reading(warning("orange", area=("Groningen", GRONINGEN)))
    assert result["level"] == "green"
    assert result["value"] == "No warnings"
    assert result["knmi_level"] == "green"
    assert result["hazards"] == [] and result["warnings"] == []


def test_an_empty_feed_is_no_warnings():
    # Calm weather: KNMI has nothing out, so the feed lists nothing. Read fresh, that's Normal.
    result = weather.reading_from_feed({"warnings": []}, READ_AT)
    assert result["level"] == "green" and result["value"] == "No warnings"


def test_yellow_and_orange_is_alert_and_orange_decides():
    result = reading(
        warning("yellow", "4; Fog", onset=f"{DAY}T03:00:00+01:00", expires=f"{DAY}T11:00:00+01:00"),
        warning("orange", "1; Wind", onset=f"{DAY}T12:00:00+01:00", expires=f"{DAY}T22:00:00+01:00"),
    )
    assert result["level"] == "red"
    assert result["value"] == "Code orange · Wind"
    assert result["knmi_level"] == "orange"
    assert [(w["level"], w["hazard"]) for w in result["warnings"]] == [("orange", "Wind"), ("yellow", "Fog")]


def test_red_is_alert():
    result = reading(warning("red", "1; Wind"))
    assert result["level"] == "red"
    assert result["value"] == "Code red · Wind"


def test_a_warning_valid_only_tomorrow_does_not_count():
    result = reading(warning("orange", "1; Wind", onset="2026-11-03T00:00:00+01:00", expires="2026-11-03T12:00:00+01:00"))
    assert result["level"] == "green"
    assert result["value"] == "No warnings"


def test_a_warning_that_expired_this_morning_does_not_count():
    # Owner's decision, 2 Nov 2026: a warning already over when the feed is read is ignored.
    result = reading(warning("yellow", "4; Fog", onset=f"{DAY}T00:00:00+01:00", expires=f"{DAY}T05:00:00+01:00"))
    assert result["level"] == "green"
    assert result["warnings"] == []


def test_a_warning_ending_exactly_when_the_feed_is_read_does_not_count():
    assert reading(warning("yellow", "4; Fog", onset=f"{DAY}T00:00:00+01:00", expires=f"{DAY}T06:45:00+01:00"))["level"] == "green"


def test_a_warning_starting_later_today_counts():
    result = reading(warning("yellow", "3; Thunderstorm", onset=f"{DAY}T15:00:00+01:00", expires=f"{DAY}T21:00:00+01:00"))
    assert result["level"] == "amber"
    assert result["hazards"] == ["Thunderstorm"]


def test_a_warning_that_started_yesterday_and_is_still_running_counts():
    assert reading(warning("orange", "1; Wind", onset="2026-11-01T18:00:00+01:00", expires=f"{DAY}T09:00:00+01:00"))["level"] == "red"


def test_a_warning_starting_at_midnight_tonight_is_tomorrows():
    assert reading(warning("yellow", onset="2026-11-03T00:00:00+01:00", expires="2026-11-03T06:00:00+01:00"))["level"] == "green"


def test_a_warning_starting_late_tonight_is_todays():
    assert reading(warning("yellow", onset=f"{DAY}T23:30:00+01:00", expires="2026-11-03T06:00:00+01:00"))["level"] == "amber"


def test_today_is_the_amsterdam_date_not_the_utc_date():
    late = datetime(2026, 11, 1, 23, 30, tzinfo=timezone.utc)  # 00:30 on 2 Nov in Amsterdam
    result = reading(warning("yellow", onset=f"{DAY}T12:00:00+01:00", expires=f"{DAY}T18:00:00+01:00"), read_at=late)
    assert result["level"] == "amber"


def test_a_missing_expiry_counts_as_still_valid():
    assert reading(warning("yellow", expires=None))["level"] == "amber"


def test_a_missing_onset_falls_back_to_the_time_it_was_sent():
    # The new entries have no "effective": sent is 1 Nov 22:10, so valid today until it expires.
    assert reading(warning("yellow", onset=None, expires=f"{DAY}T12:00:00+01:00"))["level"] == "amber"


def test_two_hazards_at_the_highest_level_are_both_named():
    result = reading(
        warning("yellow", "4; Fog", onset=f"{DAY}T03:00:00+01:00", expires=f"{DAY}T11:00:00+01:00"),
        warning("yellow", "1; Wind", onset=f"{DAY}T14:00:00+01:00", expires=f"{DAY}T20:00:00+01:00"),
        warning("yellow", "4; Fog", onset=f"{DAY}T19:00:00+01:00", expires=f"{DAY}T23:00:00+01:00"),
    )
    assert result["value"] == "Code yellow · Fog, Wind"  # onset order, each hazard once
    assert result["hazards"] == ["Fog", "Wind"]


def test_the_hazard_name_is_taken_as_knmi_writes_it_with_a_capital():
    assert reading(warning("yellow", "2; snow-ice"))["value"] == "Code yellow · Snow-ice"


# --- only real and current versions ----------------------------------------------------------


def test_a_warning_replaced_by_an_update_does_not_count():
    old = warning("orange", "1; Wind", identifier="ZH-wind-1")
    new = warning("yellow", "1; Wind", identifier="ZH-wind-2", msg_type="Update", references=["ZH-wind-1"], sent=f"{DAY}T05:00:00+01:00")
    result = reading(old, new)
    assert result["level"] == "amber"
    assert result["issued_at"] == f"{DAY}T05:00:00+01:00"


def test_an_update_down_to_green_clears_the_warning():
    old = warning("yellow", "4; Fog", identifier="ZH-fog-1")
    new = warning("green", "4; Fog", identifier="ZH-fog-2", msg_type="Update", references=["ZH-fog-1"])
    result = reading(old, new)
    assert result["level"] == "green" and result["issued_at"] is None


def test_a_cancelled_warning_does_not_count():
    old = warning("orange", "1; Wind", identifier="ZH-wind-1")
    cancel = warning("orange", "1; Wind", identifier="ZH-wind-cancel", msg_type="Cancel", references=["ZH-wind-1"])
    assert reading(old, cancel)["level"] == "green"


def test_a_test_or_exercise_message_does_not_count():
    assert reading(warning("red", status="Test"), warning("red", status="Exercise"))["level"] == "green"


# --- what the reading holds (MeteoAlarm display requirements, spec §2.2) ---------------------


def test_the_reading_has_every_field_the_display_needs():
    result = reading(
        warning("yellow", "1; Wind", onset=f"{DAY}T04:00:00+01:00", expires=f"{DAY}T18:00:00+01:00", sent=f"{DAY}T03:15:00+01:00"),
    )
    assert result["key"] == "weather"
    assert result["label"] == "Weather warnings"
    assert result["icon"] == "wind"
    assert result["place"] == "Port of Rotterdam area"
    assert result["source_name"] == "KNMI via MeteoAlarm"
    assert result["source_url"] == "https://www.meteoalarm.org"
    assert result["issued_at"] == f"{DAY}T03:15:00+01:00"
    assert result["knmi_level"] == "yellow"
    assert result["hazards"] == ["Wind"]
    assert result["observed_at"] == f"{DAY}T06:45:00+01:00"
    assert result["note"] == "Warnings at 06:45 · not live"
    assert result["warnings"] == [{"level": "yellow", "hazard": "Wind", "onset": f"{DAY}T04:00:00+01:00",
                                   "expires": f"{DAY}T18:00:00+01:00", "issued_at": f"{DAY}T03:15:00+01:00"}]


def test_times_are_stored_in_amsterdam_time():
    result = reading(warning("yellow", sent="2026-11-02T02:15:00+00:00", onset="2026-11-02T03:00:00Z", expires="2026-11-02T17:00:00Z"))
    assert result["issued_at"] == f"{DAY}T03:15:00+01:00"
    assert result["warnings"][0]["onset"] == f"{DAY}T04:00:00+01:00"
    assert result["warnings"][0]["expires"] == f"{DAY}T18:00:00+01:00"


def test_with_no_warnings_there_is_no_time_of_issue_only_the_read_time():
    result = reading()
    assert result["value"] == "No warnings"
    assert result["issued_at"] is None
    assert result["observed_at"] == f"{DAY}T06:45:00+01:00"
    assert result["note"] == "Warnings at 06:45 · not live"


def test_with_warnings_the_time_of_issue_is_the_earliest_starting_ones():
    result = reading(
        warning("yellow", "1; Wind", onset=f"{DAY}T14:00:00+01:00", expires=f"{DAY}T20:00:00+01:00", sent=f"{DAY}T05:30:00+01:00"),
        warning("yellow", "4; Fog", onset=f"{DAY}T03:00:00+01:00", expires=f"{DAY}T11:00:00+01:00", sent=f"{DAY}T01:10:00+01:00"),
    )
    assert result["issued_at"] == f"{DAY}T01:10:00+01:00"


def test_the_warning_text_never_reaches_the_reading():
    dumped = json.dumps(reading(warning("orange")))
    assert "Invented" not in dumped
    for word in ("headline", "description", "event", "instruction"):
        assert word not in dumped


def test_the_reading_can_be_stored_in_data_status(tmp_path):
    storage.write("status", date(2026, 11, 2), {"readings": [reading(warning("yellow"))]}, data_dir=tmp_path)


def test_the_time_the_feed_was_read_must_have_a_timezone():
    with pytest.raises(ValueError):
        weather.reading_from_feed(feed(), datetime(2026, 11, 2, 6, 45))


# --- the expected shape, or No data --------------------------------------------------------------


def test_an_entry_without_a_polygon_is_no_data():
    # e.g. the old shape (a province code, no polygon): we can't tell whether it covers the port.
    old_shape = warning("yellow", polygons=[])
    old_shape["alert"]["info"][1]["area"][0]["geocode"] = [{"value": "NL009", "valueName": "EMMA_ID"}]
    with pytest.raises(weather.WeatherFeedError, match="polygon"):
        reading(old_shape)


@pytest.mark.parametrize("polygon", [
    "52.0,4.0 52.1,4.1",                    # fewer than 3 points
    "52.0;4.0 52.1,4.1 52.2,4.0",           # not "lat,lon"
    "north,west 52.1,4.1 52.2,4.0",          # not numbers
    "152.0,4.0 52.1,4.1 52.2,4.0",           # latitude out of range
    "",
])
def test_an_unreadable_polygon_is_no_data(polygon):
    with pytest.raises(weather.WeatherFeedError, match="polygon"):
        reading(warning("yellow", area=("Somewhere", polygon)))


def test_an_unreadable_polygon_elsewhere_is_no_data_too():
    # We can't tell whether a warning covers the port without reading its polygon.
    with pytest.raises(weather.WeatherFeedError, match="polygon"):
        reading(warning("yellow"), warning("orange", area=("Groningen", "not a polygon")))


def test_an_area_that_is_not_a_list_of_areas_is_no_data():
    broken = warning("yellow")
    for info in broken["alert"]["info"]:
        info["area"] = "South Holland"
    with pytest.raises(weather.WeatherFeedError, match="area"):
        reading(broken)


def test_an_unreadable_level_in_a_port_warning_is_no_data():
    with pytest.raises(weather.WeatherFeedError, match="awareness level"):
        reading(warning(level_value="purple"))


def test_an_unknown_colour_is_no_data():
    with pytest.raises(weather.WeatherFeedError, match="awareness level"):
        reading(warning(level_value="5; purple; Extreme"))


def test_an_unreadable_time_in_a_port_warning_is_no_data():
    with pytest.raises(weather.WeatherFeedError, match="time"):
        reading(warning(expires="tomorrow evening"))


def test_a_time_without_a_timezone_is_unreadable():
    with pytest.raises(weather.WeatherFeedError, match="time"):
        reading(warning(expires=f"{DAY}T18:00:00"))


@pytest.mark.parametrize("data", [[], {"alerts": []}, {"warnings": "none"}, {"warnings": [{"no_alert": 1}]}])
def test_json_that_is_not_the_warnings_feed_is_no_data(data):
    with pytest.raises(weather.WeatherFeedError):
        weather.reading_from_feed(data, READ_AT)


# --- read_weather: fetch, freshness, reading; failures instead of exceptions --------------------


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


SERVER_NOW = READ_AT + timedelta(seconds=20)  # the server's clock when it answered


def json_response(data, status=200, served=SERVER_NOW, age=None):
    body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
    headers = {"content-type": "application/json; charset=utf-8",
               "cache-control": "max-age=0, private, must-revalidate"}
    if served is not None:
        headers["date"] = format_datetime(served, usegmt=True)
    if age is not None:
        headers["age"] = str(age)
    return RawResponse(status, headers, body)


def test_read_weather_fetches_the_netherlands_feed_politely():
    fetch, net = fetcher(json_response(feed(warning("yellow"))))
    result = weather.read_weather(fetch, READ_AT)
    assert result.reading["level"] == "amber"
    assert result.failures == []
    urls = [url for url, _ in net.calls]
    assert urls == ["https://feeds.meteoalarm.org/robots.txt", "https://feeds.meteoalarm.org/api/v1/warnings/feeds-netherlands"]
    assert all(headers["User-Agent"].startswith("HavenDaily/") for _, headers in net.calls)


def test_a_fresh_feed_with_nothing_for_the_port_is_normal():
    fetch, _ = fetcher(json_response(feed(warning("red", area=("Groningen", GRONINGEN)))))
    result = weather.read_weather(fetch, READ_AT)
    assert result.reading["level"] == "green" and result.reading["value"] == "No warnings"
    assert result.failures == []


def test_a_fresh_empty_feed_is_normal():
    fetch, _ = fetcher(json_response({"warnings": []}))
    assert weather.read_weather(fetch, READ_AT).reading["value"] == "No warnings"


@pytest.mark.parametrize("served, age, problem", [
    (None, None, "no Date"),                                             # can't tell how old it is
    (READ_AT - timedelta(minutes=16), None, "not fresh"),                # answered too long ago
    (READ_AT + timedelta(minutes=16), None, "not fresh"),                # a clock we can't trust
    (SERVER_NOW, 960, "not fresh"),                                      # a cache's copy, 16 min old
])
def test_a_feed_that_is_not_fresh_is_no_data_even_with_nothing_for_the_port(served, age, problem):
    fetch, _ = fetcher(json_response({"warnings": []}, served=served, age=age))
    result = weather.read_weather(fetch, READ_AT)
    assert_no_data(result.reading)
    assert problem in result.failures[0]["error"]


def test_a_feed_that_is_not_fresh_is_no_data_with_a_warning_too():
    fetch, _ = fetcher(json_response(feed(warning("orange")), served=READ_AT - timedelta(hours=3)))
    assert_no_data(weather.read_weather(fetch, READ_AT).reading)


def test_fifteen_minutes_either_way_is_still_fresh():
    for served in (READ_AT - timedelta(minutes=15), READ_AT + timedelta(minutes=15)):
        fetch, _ = fetcher(json_response({"warnings": []}, served=served, age=900))
        assert weather.read_weather(fetch, READ_AT).reading["value"] == "No warnings", served


def assert_no_data(result):
    assert result["value"] is None
    assert result["level"] is None
    assert result["knmi_level"] is None
    assert result["issued_at"] is None
    assert result["hazards"] == []
    assert result["warnings"] == []
    assert result["note"] is None
    assert result["source_url"] == "https://www.meteoalarm.org"


@pytest.mark.parametrize(
    "answer, problem",
    [
        (TransportError("connection refused"), "connection refused (tried twice)"),
        (json_response({}, status=503), "HTTP 503"),
        (json_response(b"<html>Bot check</html>"), "not JSON"),
        (json_response({"warnings": [{"no_alert": 1}]}), "not a MeteoAlarm warnings feed"),
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
    def net(url, headers, timeout):
        if url == "https://feeds.meteoalarm.org/robots.txt":
            return RawResponse(200, {}, b"User-agent: *\nDisallow: /api/\n")
        raise AssertionError("a disallowed page was requested")

    fetch = Fetcher(transport=net, clock=lambda: 0.0, sleep=lambda s: None)
    result = weather.read_weather(fetch, READ_AT)
    assert_no_data(result.reading)
    assert "robots.txt" in result.failures[0]["error"]


def test_a_bug_of_ours_gives_no_data_not_a_crash(monkeypatch):
    def broken(data, read_at, places=None):
        raise KeyError("oops")

    monkeypatch.setattr(weather, "reading_from_feed", broken)
    fetch, _ = fetcher(json_response(feed(warning("yellow"))))
    result = weather.read_weather(fetch, READ_AT)
    assert_no_data(result.reading)
    assert "unexpected error (KeyError" in result.failures[0]["error"]
