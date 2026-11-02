"""Rhine status: Kaub shown, Lobith stored (spec §2.2, §4; issue #20).

Every API answer here is written by us in the structure of the real ones (checked
2 Nov 2026): PEGELONLINE's `currentmeasurement.json` for Kaub, and Rijkswaterstaat's
`OphalenWaarnemingen` answer for Lobith (one series per ProcesType, `meting` =
measurement, `verwachting` = forecast, each with a `MetingenLijst`). The network is a
fake: no test touches the internet.

On 2 Nov 2026 Amsterdam is on winter time (UTC+1), so 06:45 Amsterdam = 05:45 UTC.
"""

import json
import math
from datetime import date, datetime, timedelta, timezone

import pytest

from haven import rhine, storage
from haven.config import RhineThresholds, load_rhine
from haven.fetch import Fetcher, RawResponse, TransportError

READ_AT = datetime(2026, 11, 2, 5, 45, tzinfo=timezone.utc)  # 06:45 Amsterdam
THRESHOLDS = load_rhine()  # the repo's config/rhine.toml: the decided numbers are tested


# --- the thresholds: every boundary (issue #20 acceptance criteria) --------------------


@pytest.mark.parametrize(
    "value, level",
    [
        (79, "red"), (80, "red"), (81, "amber"),  # Alert at 80 cm or below
        (149, "amber"), (150, "amber"), (151, "green"),  # Watch at 150 cm or below
        (459, "green"), (460, "green"), (461, "amber"),  # Watch above Marke I 460
        (639, "amber"), (640, "amber"), (641, "red"),  # Alert above Marke II 640
    ],
)
def test_level_at_and_around_every_boundary(value, level):
    assert rhine.kaub_level(value, THRESHOLDS) == level


def test_a_reading_below_the_record_low_is_a_valid_alert():
    # Owner, 2 Nov 2026 (PR #71): Kaub read 21 cm, under the record low NNW 25 cm. Not bad data.
    assert rhine.kaub_level(21, THRESHOLDS) == "red"
    assert rhine.kaub_level(0, THRESHOLDS) == "red"
    assert rhine.kaub_level(-3, THRESHOLDS) == "red"


@pytest.mark.parametrize("value, level", [(80.5, "amber"), (150.5, "green"), (460.5, "amber"), (640.5, "red")])
def test_a_value_between_whole_centimetres_falls_on_the_right_side(value, level):
    assert rhine.kaub_level(value, THRESHOLDS) == level


def test_thresholds_come_from_the_config_not_from_the_api():
    other = RhineThresholds(alert_at_or_below=10, watch_at_or_below=20, watch_above=900, alert_above=950)
    assert rhine.kaub_level(21, other) == "green"
    reading = rhine.kaub_from_answer(kaub_answer(value=21.0), READ_AT, other)
    assert reading["level"] == "green"


# --- Kaub: parsing PEGELONLINE's answer ------------------------------------------------


def kaub_answer(value=21.0, timestamp="2026-11-02T06:30:00+01:00"):
    """Like the real currentmeasurement.json (2 Nov 2026)."""
    answer = {"stateMnwMhw": "low", "stateNswHsw": "normal"}
    if timestamp is not None:
        answer["timestamp"] = timestamp
    if value is not None:
        answer["value"] = value
    return answer


def test_kaub_reading_has_the_shape_the_page_uses():
    reading = rhine.kaub_from_answer(kaub_answer(value=94.0), READ_AT, THRESHOLDS)
    assert reading == {
        "key": "rhine",
        "label": "Rhine water level",
        "icon": "waves",
        "value": 94,
        "unit": "cm",
        "place": "Kaub gauge",
        "level": "amber",
        "gauge_max": 300,
        "observed_at": "2026-11-02T06:30:00+01:00",
        "source_name": "WSV via PEGELONLINE",
        "source_url": "https://pegelonline.wsv.de/gast/stammdaten?pegelnr=25700100",
        "note": None,
    }


def test_kaub_whole_centimetres_are_stored_as_a_whole_number():
    assert rhine.kaub_from_answer(kaub_answer(value=21.0), READ_AT, THRESHOLDS)["value"] == 21
    assert isinstance(rhine.kaub_from_answer(kaub_answer(value=21.0), READ_AT, THRESHOLDS)["value"], int)
    assert rhine.kaub_from_answer(kaub_answer(value=21.4), READ_AT, THRESHOLDS)["value"] == 21.4


def test_kaub_time_is_stored_in_amsterdam_time():
    reading = rhine.kaub_from_answer(kaub_answer(timestamp="2026-11-02T05:30:00+00:00"), READ_AT, THRESHOLDS)
    assert reading["observed_at"] == "2026-11-02T06:30:00+01:00"


def test_kaub_reading_up_to_six_hours_old_counts():
    six_hours = (READ_AT - timedelta(hours=6)).isoformat()
    assert rhine.kaub_from_answer(kaub_answer(timestamp=six_hours), READ_AT, THRESHOLDS)["value"] == 21


def test_kaub_reading_older_than_six_hours_is_no_data():
    # The gauge reports every 15 minutes: a reading this old means the gauge or the API is stuck.
    stale = (READ_AT - timedelta(hours=6, seconds=1)).isoformat()
    with pytest.raises(rhine.RhineDataError, match="older than 6 h"):
        rhine.kaub_from_answer(kaub_answer(timestamp=stale), READ_AT, THRESHOLDS)


@pytest.mark.parametrize(
    "answer",
    [
        kaub_answer(value=None),
        kaub_answer(value="21"),
        kaub_answer(value=True),
        kaub_answer(value=math.nan),
        kaub_answer(value=math.inf),
        kaub_answer(timestamp=None),
        kaub_answer(timestamp="yesterday"),
        kaub_answer(timestamp="2026-11-02T06:30:00"),  # no timezone: unreadable
        [],
        "not an object",
    ],
)
def test_kaub_anything_unreadable_is_no_data_never_a_guess(answer):
    with pytest.raises(rhine.RhineDataError):
        rhine.kaub_from_answer(answer, READ_AT, THRESHOLDS)


# --- Lobith: the request and parsing Rijkswaterstaat's answer --------------------------


def test_lobith_request_asks_for_measurements_of_the_last_24_hours():
    # Measurements arrive about 3 h late (live check 2 Nov 2026: newest 10:10 at 13:20),
    # and a short window can hold only the forecast, so the window is a whole day.
    assert rhine.lobith_request(READ_AT) == {
        "Locatie": {"Code": "lobith.bovenrijn.tolkamer"},
        "AquoPlusWaarnemingMetadata": {
            "AquoMetadata": {"Compartiment": {"Code": "OW"}, "Grootheid": {"Code": "WATHTE"}, "ProcesType": "meting"}
        },
        "Periode": {
            "Begindatumtijd": "2026-11-01T06:45:00.000+01:00",
            "Einddatumtijd": "2026-11-02T06:45:00.000+01:00",
        },
    }


def measurement(at, value, code="00"):
    return {
        "Meetwaarde": {"Waarde_Alfanumeriek": str(value), "Waarde_Numeriek": value},
        "Tijdstip": at,
        "WaarnemingMetadata": {
            "Bemonsteringshoogte": "0",
            "Kwaliteitswaardecode": code,
            "OpdrachtgevendeInstantie": "RIKZMON_WAT",
            "Referentievlak": "NVT",
            "Statuswaarde": "Ongecontroleerd",
        },
    }


def series(*measurements, process="meting", unit="cm", datum="NAP", quantity="WATHTE"):
    return {
        "AquoMetadata": {
            "Compartiment": {"Code": "OW", "Omschrijving": "Oppervlaktewater"},
            "Eenheid": {"Code": unit, "Omschrijving": "centimeter"},
            "Grootheid": {"Code": quantity, "Omschrijving": "Waterhoogte"},
            "Hoedanigheid": {"Code": datum, "Omschrijving": "t.o.v. Normaal Amsterdams Peil"},
            "ProcesType": process,
        },
        "Locatie": {"Code": "lobith.bovenrijn.tolkamer", "Naam": "Lobith, Bovenrijn, Tolkamer", "Lat": 51.8495, "Lon": 6.1024},
        "MetingenLijst": list(measurements),
    }


def lobith_answer(*all_series, ok=True):
    return {"Succesvol": ok, "WaarnemingenLijst": list(all_series)}


def test_lobith_reading_takes_the_newest_measurement():
    answer = lobith_answer(
        series(
            measurement("2026-11-02T03:30:00.000+01:00", 671.0),
            measurement("2026-11-02T03:50:00.000+01:00", 669.0),
            measurement("2026-11-02T03:40:00.000+01:00", 670.0),
        )
    )
    reading = rhine.lobith_from_answer(answer, READ_AT)
    assert reading == {
        "key": "rhine-lobith",
        "label": "Rhine water level, Lobith",
        "icon": "waves",
        "value": 669,
        "unit": "cm NAP",
        "place": "Lobith gauge (Tolkamer)",
        "observed_at": "2026-11-02T03:50:00+01:00",
        "source_name": "Rijkswaterstaat",
        "source_url": "https://rijkswaterstaatdata.nl/waterdata/",
        "note": None,
    }


def test_lobith_has_no_level_because_it_has_no_thresholds_and_is_not_shown():
    reading = rhine.lobith_from_answer(lobith_answer(series(measurement("2026-11-02T03:50:00.000+01:00", 669.0))), READ_AT)
    assert "level" not in reading


def test_lobith_forecast_is_never_taken_for_a_measurement():
    answer = lobith_answer(
        series(measurement("2026-11-02T03:50:00.000+01:00", 669.0)),
        series(measurement("2026-11-02T06:40:00.000+01:00", 700.0), process="verwachting"),
    )
    assert rhine.lobith_from_answer(answer, READ_AT)["value"] == 669


def test_lobith_only_forecast_is_no_data():
    answer = lobith_answer(series(measurement("2026-11-02T06:40:00.000+01:00", 700.0), process="verwachting"))
    with pytest.raises(rhine.RhineDataError, match="no measurement"):
        rhine.lobith_from_answer(answer, READ_AT)


def test_lobith_values_not_marked_normal_are_skipped():
    # Kwaliteitswaardecode "00" = normal value, the only code in the live answer (2 Nov 2026).
    answer = lobith_answer(
        series(
            measurement("2026-11-02T03:40:00.000+01:00", 670.0),
            measurement("2026-11-02T03:50:00.000+01:00", 999999999.0, code="99"),
        )
    )
    assert rhine.lobith_from_answer(answer, READ_AT)["value"] == 670


def test_lobith_measurements_older_than_24_hours_are_not_used():
    old = (READ_AT - timedelta(hours=24, minutes=10)).astimezone(timezone(timedelta(hours=1)))
    answer = lobith_answer(series(measurement(old.isoformat(timespec="milliseconds"), 650.0)))
    with pytest.raises(rhine.RhineDataError, match="no measurement"):
        rhine.lobith_from_answer(answer, READ_AT)


@pytest.mark.parametrize(
    "bad_series",
    [
        series(measurement("2026-11-02T03:50:00.000+01:00", 669.0), unit="m"),
        series(measurement("2026-11-02T03:50:00.000+01:00", 669.0), datum="MSL"),
        series(measurement("2026-11-02T03:50:00.000+01:00", 669.0), quantity="Q"),
    ],
)
def test_lobith_a_series_in_another_unit_or_quantity_is_not_used(bad_series):
    with pytest.raises(rhine.RhineDataError, match="no measurement"):
        rhine.lobith_from_answer(lobith_answer(bad_series), READ_AT)


@pytest.mark.parametrize(
    "answer",
    [
        lobith_answer(series(measurement("2026-11-02T03:50:00.000+01:00", 669.0)), ok=False),
        {"WaarnemingenLijst": "not a list", "Succesvol": True},
        {"Succesvol": True},
        [],
        lobith_answer(series(measurement("2026-11-02T03:50:00", 669.0))),  # no timezone
        lobith_answer(series(measurement("not a time", 669.0))),
        lobith_answer(series(measurement("2026-11-02T03:50:00.000+01:00", "669"))),
        lobith_answer(series(measurement("2026-11-02T03:50:00.000+01:00", math.nan))),
    ],
)
def test_lobith_anything_unreadable_is_no_data(answer):
    with pytest.raises(rhine.RhineDataError):
        rhine.lobith_from_answer(answer, READ_AT)


# --- read_rhine: both APIs, failures instead of exceptions -----------------------------


class FakeNet:
    """url -> answer (a RawResponse or an exception). robots.txt is missing on both hosts, as in reality."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, headers, timeout, data=None):
        self.calls.append({"url": url, "headers": headers, "data": data})
        if url.endswith("/robots.txt"):
            return RawResponse(404, {}, b"")
        answer = self.routes[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def json_response(data, status=200):
    body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
    return RawResponse(status, {"content-type": "application/json; charset=utf-8"}, body)


GOOD_KAUB = json_response(kaub_answer(value=21.0))
GOOD_LOBITH = json_response(lobith_answer(series(measurement("2026-11-02T03:50:00.000+01:00", 669.0))))


def run(kaub=GOOD_KAUB, lobith=GOOD_LOBITH):
    net = FakeNet({rhine.KAUB_URL: kaub, rhine.LOBITH_URL: lobith})
    fetcher = Fetcher(transport=net, clock=lambda: 0.0, sleep=lambda s: None)
    return rhine.read_rhine(fetcher, READ_AT, THRESHOLDS), net


def test_both_readings_on_a_good_morning():
    result, net = run()
    assert result.failures == []
    assert result.kaub["value"] == 21 and result.kaub["level"] == "red"
    assert result.lobith["value"] == 669
    posted = [c for c in net.calls if c["url"] == rhine.LOBITH_URL][0]
    assert json.loads(posted["data"]) == rhine.lobith_request(READ_AT)
    assert all(c["headers"]["User-Agent"].startswith("HavenDaily/") for c in net.calls)


def test_lobith_is_stored_but_not_shown():
    result, _ = run()
    assert [r["key"] for r in result.shown] == ["rhine"]  # what goes into the brief's status line
    assert [r["key"] for r in result.stored] == ["rhine", "rhine-lobith"]  # what goes into data/status/


def test_the_stored_readings_pass_the_storage_rules(tmp_path):
    result, _ = run()
    storage.write("status", date(2026, 11, 2), result.stored, data_dir=tmp_path)
    assert storage.read("status", date(2026, 11, 2), data_dir=tmp_path) == result.stored


@pytest.mark.parametrize(
    "answer, problem",
    [
        (TransportError("connection refused"), "connection refused (tried twice)"),
        (json_response({}, status=503), "HTTP 503"),
        (json_response(b"<html>Bot check</html>"), "not JSON"),
        (json_response(kaub_answer(value=None)), "no readable value"),
    ],
)
def test_kaub_down_is_no_data_for_kaub_only(answer, problem):
    result, _ = run(kaub=answer)
    assert result.kaub["value"] is None and result.kaub["level"] is None
    assert result.kaub["observed_at"] is None
    assert result.kaub["key"] == "rhine" and result.kaub["source_url"].startswith("https://pegelonline")
    assert result.lobith["value"] == 669
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure["source"] == "Rhine level, Kaub (PEGELONLINE)"
    assert problem in failure["error"] and "\n" not in failure["error"]


@pytest.mark.parametrize(
    "answer, problem",
    [
        (TransportError("connection refused"), "connection refused (tried twice)"),
        (json_response({}, status=500), "HTTP 500"),
        (RawResponse(204, {}, b""), "no measurement in the last 24 h"),  # what the real API sends for an empty window
        (json_response(lobith_answer(ok=False)), "not successful"),
    ],
)
def test_lobith_down_is_no_data_for_lobith_only(answer, problem):
    result, _ = run(lobith=answer)
    assert result.lobith["value"] is None and result.lobith["observed_at"] is None
    assert result.kaub["value"] == 21 and result.kaub["level"] == "red"
    assert len(result.failures) == 1
    assert result.failures[0]["source"] == "Rhine level, Lobith (Rijkswaterstaat)"
    assert problem in result.failures[0]["error"]


def test_both_down_gives_two_failure_lines():
    result, _ = run(kaub=TransportError("down"), lobith=TransportError("down"))
    assert result.kaub["value"] is None and result.lobith["value"] is None
    assert [f["source"] for f in result.failures] == [
        "Rhine level, Kaub (PEGELONLINE)",
        "Rhine level, Lobith (Rijkswaterstaat)",
    ]


def test_a_bug_of_ours_becomes_a_failure_line_not_a_crash(monkeypatch):
    def broken(*args):
        raise KeyError("oops")

    monkeypatch.setattr(rhine, "kaub_from_answer", broken)
    result, _ = run()
    assert result.kaub["value"] is None
    assert "unexpected error (KeyError" in result.failures[0]["error"]
    assert result.lobith["value"] == 669


def test_the_time_read_must_have_a_timezone():
    with pytest.raises(ValueError, match="timezone"):
        rhine.read_rhine(Fetcher(transport=FakeNet({})), datetime(2026, 11, 2, 6, 45), THRESHOLDS)


def test_default_thresholds_are_the_repo_config():
    net = FakeNet({rhine.KAUB_URL: json_response(kaub_answer(value=150.0)), rhine.LOBITH_URL: GOOD_LOBITH})
    fetcher = Fetcher(transport=net, clock=lambda: 0.0, sleep=lambda s: None)
    assert rhine.read_rhine(fetcher, READ_AT).kaub["level"] == "amber"
