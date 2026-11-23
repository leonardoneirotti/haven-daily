"""MeteoAlarm's reply of 23 Nov 2026: the morning weather snapshot is allowed, on conditions (#115).

The MeteoAlarm Team agreed (docs/permissions/2026-11-23-meteoalarm.md; spec §11) to showing KNMI's
warning level for Zuid-Holland once a day, **clearly identified as a morning snapshot and not a
live warning service**, with:

1. attribution to MeteoAlarm and KNMI;
2. the relevant disclaimer with the displayed information;
3. a clear link to the official MeteoAlarm website for the latest warnings;
4. no suggestion that Haven Daily is an official MeteoAlarm or KNMI service.

These tests hold all five in place on the weather dial (with and without a reading) and on
How it works. The dial's other MeteoAlarm requirements (time of issue, KNMI's own level next to
ours) are in tests/test_render_real.py.
"""

import re
from pathlib import Path

import pytest

from haven.render import METEOALARM_DISCLAIMER
from tests.test_method_page import render_method
from tests.test_render_real import dial, make_brief, render_day, text_of, weather

ROOT = Path(__file__).resolve().parent.parent
REPLY = ROOT / "docs" / "permissions" / "2026-11-23-meteoalarm.md"
SITE = "https://www.meteoalarm.org"


# --- the saved reply ----------------------------------------------------------------------------


def test_the_reply_is_saved_with_name_role_and_date_but_no_email_address():
    text = REPLY.read_text(encoding="utf-8")
    assert "MeteoAlarm Team" in text and "23 November 2026" in text
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)


def test_the_reply_records_every_condition():
    text = REPLY.read_text(encoding="utf-8")
    for words in ("morning snapshot and not a live warning service", "Appropriate attribution to MeteoAlarm and KNMI",
                  "relevant disclaimer", "clear link to the official MeteoAlarm website",
                  "No suggestion that Haven Daily is an official MeteoAlarm or KNMI service"):
        assert words in text


# --- the weather dial ---------------------------------------------------------------------------

READINGS = {
    "a warning": weather(),
    "no warnings": weather(value="No warnings", level="green", knmi_level="green", hazards=[], issued_at=None),
    "no data": weather(value=None, level=None, knmi_level=None, hazards=[], issued_at=None, note=None),
}


@pytest.fixture(params=list(READINGS))
def weather_dial(request, tmp_path):
    return dial(render_day(tmp_path, make_brief(status=[READINGS[request.param]])), "weather")


def test_the_dial_credits_knmi_and_meteoalarm(weather_dial):
    assert "KNMI via MeteoAlarm" in text_of(weather_dial)


def test_the_dial_shows_the_disclaimer(weather_dial):
    assert METEOALARM_DISCLAIMER in text_of(weather_dial)


def test_the_dial_says_it_is_a_morning_snapshot_not_a_live_warning_service(weather_dial):
    assert "Morning snapshot, not a live warning service." in text_of(weather_dial)


def test_the_dial_says_haven_daily_is_not_a_meteoalarm_or_knmi_service(weather_dial):
    assert "Haven Daily is not a MeteoAlarm or KNMI service." in text_of(weather_dial)


def test_the_dial_links_to_meteoalarm_for_the_latest_warnings(weather_dial):
    links = dict((text_of(label), href) for href, label in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', weather_dial, re.S))
    assert links.get("Latest warnings on meteoalarm.org") == SITE


# --- How it works -------------------------------------------------------------------------------


def weather_section(page: str) -> str:
    start = page.index('id="weather"')
    return page[start : page.index("</section>", start)]


def test_how_it_works_meets_every_condition():
    part = weather_section(render_method())
    text = text_of(part)
    assert "KNMI" in text and "MeteoAlarm" in text                                       # 1 attribution
    assert METEOALARM_DISCLAIMER in text                                                  # 2 disclaimer
    assert re.search(r'<a href="https://www\.meteoalarm\.org">[^<]*latest warnings', part)  # 3 link
    assert "not a MeteoAlarm or KNMI service" in text  # 4 not official (the word itself never appears, §5.3 point 7)
    assert "a morning snapshot, not a live warning service" in text                       # snapshot


def test_how_it_works_says_meteoalarm_agreed_to_the_daily_snapshot():
    assert "MeteoAlarm agreed on 23 November 2026" in text_of(weather_section(render_method()))


# --- the spec -----------------------------------------------------------------------------------


def test_the_spec_records_the_permission_and_its_conditions():
    spec = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")
    section_11 = spec[spec.index("## 11. Open items"):spec.index("## 12. Credits")]
    assert "docs/permissions/2026-11-23-meteoalarm.md" in section_11
    assert "Until MeteoAlarm clarifies" not in spec
