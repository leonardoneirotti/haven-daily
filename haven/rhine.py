"""Rhine status: Kaub shown, Lobith stored (spec §2.2, §4; issue #20).

Two readings a morning, from two public APIs with no key:

- **Kaub** (PEGELONLINE, WSV; DL-DE->Zero-2.0): the gauge on the Middle Rhine that barge
  operators use for their low-water surcharges. One GET of `currentmeasurement.json`: the
  latest value (cm on the gauge board, every 15 minutes) and its time. **Shown** on the
  status line, with a level from the thresholds in `config/rhine.toml`:
  Alert at 80 cm or below or above 640, Watch at 150 or below or above 460, Normal between.
  A reading below the record low (21 cm on 2 Nov 2026, under NNW 25) is a valid Alert.
- **Lobith** (Rijkswaterstaat; CC0): where the Rhine enters the Netherlands. One POST to
  `OphalenWaarnemingen` for the last 24 hours, newest *measurement* taken (`meting`; the
  answer also holds a forecast, `verwachting`, which is never used). **Stored** in
  `data/status/` for later trend charts, **not shown**, so it has no thresholds and no level.

Either API failing gives `null` = No data for that reading only, plus one failure line;
the other reading is unaffected (hard rule 9). Any doubt is No data, never a guess (§2.2).

`python -m haven.rhine` reads both once and prints the readings; it writes nothing.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from haven.clock import AMSTERDAM
from haven.config import RhineThresholds, load_rhine
from haven.fetch import Fetcher, FetchError

KAUB_URL = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/KAUB/W/currentmeasurement.json"
KAUB_PAGE = "https://pegelonline.wsv.de/gast/stammdaten?pegelnr=25700100"  # the gauge's public page
KAUB_FAILURE_SOURCE = "Rhine level, Kaub (PEGELONLINE)"
KAUB_MAX_AGE = timedelta(hours=6)  # the gauge reports every 15 minutes; older = stuck
GAUGE_MAX = 300  # top of the little river-gauge graphic, in cm (display only, as in the samples)

LOBITH_URL = "https://ddapi20-waterwebservices.rijkswaterstaat.nl/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
LOBITH_PAGE = "https://rijkswaterstaatdata.nl/waterdata/"
LOBITH_FAILURE_SOURCE = "Rhine level, Lobith (Rijkswaterstaat)"
LOBITH_LOCATION = "lobith.bovenrijn.tolkamer"
LOBITH_WINDOW = timedelta(hours=24)  # measurements arrive ~3 h late (live check, 2 Nov 2026)
NORMAL_VALUE = "00"  # Kwaliteitswaardecode of a normal measurement


class RhineDataError(Exception):
    """An answer can't be used safely. One line, naming the kind of problem only."""


@dataclass
class RhineResult:
    kaub: dict
    lobith: dict
    failures: list[dict] = field(default_factory=list)

    @property
    def shown(self) -> list[dict]:
        """The readings for the brief's status line: Kaub only."""
        return [self.kaub]

    @property
    def stored(self) -> list[dict]:
        """The readings for data/status/: Kaub and Lobith."""
        return [self.kaub, self.lobith]


# --- Kaub ------------------------------------------------------------------------------


def kaub_level(value: float, thresholds: RhineThresholds) -> str:
    """green / amber / red for a Kaub value in cm. At the low edges counts as below them."""
    if value <= thresholds.alert_at_or_below or value > thresholds.alert_above:
        return "red"
    if value <= thresholds.watch_at_or_below or value > thresholds.watch_above:
        return "amber"
    return "green"


def kaub_from_answer(data, read_at: datetime, thresholds: RhineThresholds) -> dict:
    """The Kaub reading from PEGELONLINE's answer. Raises RhineDataError on any doubt."""
    read_at = _amsterdam(read_at)
    if not isinstance(data, dict):
        raise RhineDataError("not a PEGELONLINE measurement (no JSON object)")
    value = _number(data.get("value"))
    if value is None:
        raise RhineDataError("no readable value in the answer")
    observed = _time(data.get("timestamp"))
    if observed is None:
        raise RhineDataError("no readable time in the answer")
    if read_at - observed > KAUB_MAX_AGE:
        raise RhineDataError(f"latest reading is from {_iso(observed)}, older than 6 h (gauge stuck?)")
    reading = kaub_no_data()
    reading.update(value=value, level=kaub_level(value, thresholds), observed_at=_iso(observed))
    return reading


def kaub_no_data() -> dict:
    return {
        "key": "rhine",
        "label": "Rhine water level",
        "icon": "waves",
        "value": None,
        "unit": "cm",
        "place": "Kaub gauge",
        "level": None,
        "gauge_max": GAUGE_MAX,
        "observed_at": None,
        "source_name": "WSV via PEGELONLINE",
        "source_url": KAUB_PAGE,
        "note": None,
    }


# --- Lobith ----------------------------------------------------------------------------


def lobith_request(read_at: datetime) -> dict:
    """The query: water height (WATHTE) in surface water (OW), measurements only, last 24 h."""
    read_at = _amsterdam(read_at)
    return {
        "Locatie": {"Code": LOBITH_LOCATION},
        "AquoPlusWaarnemingMetadata": {
            "AquoMetadata": {"Compartiment": {"Code": "OW"}, "Grootheid": {"Code": "WATHTE"}, "ProcesType": "meting"}
        },
        "Periode": {
            "Begindatumtijd": (read_at - LOBITH_WINDOW).isoformat(timespec="milliseconds"),
            "Einddatumtijd": read_at.isoformat(timespec="milliseconds"),
        },
    }


def lobith_from_answer(data, read_at: datetime) -> dict:
    """The Lobith reading: the newest normal measurement of the last 24 h. Raises RhineDataError."""
    read_at = _amsterdam(read_at)
    if not isinstance(data, dict) or not isinstance(data.get("WaarnemingenLijst"), list):
        raise RhineDataError("not a Rijkswaterstaat answer (no 'WaarnemingenLijst' list)")
    if data.get("Succesvol") is not True:
        raise RhineDataError("the API says the query was not successful")

    newest: tuple[datetime, float] | None = None
    for item in data["WaarnemingenLijst"]:
        if not _is_water_height_measurement(item):
            continue
        for entry in item.get("MetingenLijst") or []:
            if not isinstance(entry, dict):
                raise RhineDataError("unreadable measurement in the answer")
            meta = entry.get("WaarnemingMetadata") or {}
            if meta.get("Kwaliteitswaardecode") != NORMAL_VALUE:
                continue
            value = _number((entry.get("Meetwaarde") or {}).get("Waarde_Numeriek"))
            at = _time(entry.get("Tijdstip"))
            if value is None or at is None:
                raise RhineDataError("unreadable value or time in a measurement")
            if read_at - at > LOBITH_WINDOW:
                continue
            if newest is None or at > newest[0]:
                newest = (at, value)

    if newest is None:
        raise RhineDataError("no measurement in the last 24 h")
    reading = lobith_no_data()
    reading.update(value=newest[1], observed_at=_iso(newest[0]))
    return reading


def lobith_no_data() -> dict:
    return {
        "key": "rhine-lobith",
        "label": "Rhine water level, Lobith",
        "icon": "waves",
        "value": None,
        "unit": "cm NAP",
        "place": "Lobith gauge (Tolkamer)",
        "observed_at": None,
        "source_name": "Rijkswaterstaat",
        "source_url": LOBITH_PAGE,
        "note": None,
    }


def _is_water_height_measurement(item) -> bool:
    """A measured (not forecast) water height in cm against NAP."""
    if not isinstance(item, dict):
        return False
    meta = item.get("AquoMetadata") or {}

    def code(name):
        part = meta.get(name)
        return part.get("Code") if isinstance(part, dict) else None

    return (
        meta.get("ProcesType") == "meting"
        and code("Grootheid") == "WATHTE"
        and code("Eenheid") == "cm"
        and code("Hoedanigheid") == "NAP"
    )


# --- both ------------------------------------------------------------------------------


def read_rhine(fetcher: Fetcher, read_at: datetime, thresholds: RhineThresholds | None = None) -> RhineResult:
    """Read Kaub and Lobith once each. Never raises for an API problem (hard rule 9)."""
    read_at = _amsterdam(read_at)
    thresholds = thresholds or load_rhine()
    failures: list[dict] = []

    def attempt(source, url, get_answer, parse, no_data, if_empty):
        try:
            response = get_answer()
            if not response.body.strip():
                raise RhineDataError(if_empty)
            try:
                data = json.loads(response.text())
            except ValueError:
                raise RhineDataError("not JSON (a bot-check or error page?)") from None
            return parse(data)
        except FetchError as error:
            problem = str(error)
        except RhineDataError as error:
            problem = f"{url}: {error}"
        except Exception as error:  # a bug of ours must not stop the morning run
            problem = f"{url}: unexpected error ({type(error).__name__}: {error})"
        failures.append({"source": source, "error": problem})
        return no_data()

    kaub = attempt(
        KAUB_FAILURE_SOURCE,
        KAUB_URL,
        lambda: fetcher.fetch(KAUB_URL),
        lambda data: kaub_from_answer(data, read_at, thresholds),
        kaub_no_data,
        "empty answer",
    )
    lobith = attempt(
        LOBITH_FAILURE_SOURCE,
        LOBITH_URL,
        lambda: fetcher.post_json(LOBITH_URL, lobith_request(read_at)),
        lambda data: lobith_from_answer(data, read_at),
        lobith_no_data,
        "no measurement in the last 24 h",  # the API answers an empty window with HTTP 204, no body
    )
    return RhineResult(kaub=kaub, lobith=lobith, failures=failures)


# --- helpers ---------------------------------------------------------------------------


def _amsterdam(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("The time the gauges were read has no timezone; it must be timezone-aware.")
    return moment.astimezone(AMSTERDAM)


def _iso(moment: datetime) -> str:
    return moment.astimezone(AMSTERDAM).isoformat(timespec="seconds")


def _number(value) -> int | float | None:
    """A finite number (whole cm as int), else None. True/False and text are not numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return int(value) if float(value).is_integer() else value


def _time(value) -> datetime | None:
    """An ISO 8601 time with a timezone, else None (a zone-less time is unreadable, as in weather)."""
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None or moment.utcoffset() is None:
        return None
    return moment


def main() -> int:
    from haven.clock import now

    sys.stdout.reconfigure(encoding="utf-8")
    result = read_rhine(Fetcher(), now())
    print(json.dumps(result.stored, indent=2, ensure_ascii=False))
    for failure in result.failures:
        print(f"FAILURE {failure['source']}: {failure['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
