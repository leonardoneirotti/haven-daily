"""Port status: each value with its meaning, Watch/Alert marks on the Rhine gauge (issue #83;
design review S6, S7; spec §2.2, §5.12, §7.8).

- S6: next to each level a short line saying what it means for a planner, built from config or
  one constant, never written per day: the Rhine's from config/rhine.toml (next to the
  thresholds), weather and strike from their level. Shown in the full dial and as a second small
  line in the panel's mini status. No data shows only "No data".
- S7: lines on the Rhine gauge at the Watch and Alert thresholds from config/rhine.toml;
  gauge_max stays 700 cm.

Headlines are invented.
"""

import re
from pathlib import Path

import pytest

from haven import render, rhine, strike
from haven.config import ConfigError, RhineMeanings, RhineThresholds, load_rhine, load_rhine_meanings
from test_render_real import METEOALARM_DISCLAIMER, dial, kaub, link, make_brief, text_of, weather
from test_render_real import strike as strike_reading

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")

THRESHOLDS = RhineThresholds(alert_at_or_below=80, watch_at_or_below=150, watch_above=460, alert_above=640)
MEANINGS = load_rhine_meanings()

# Claude's default wording (issue #83, not yet confirmed by the owner).
RHINE_MEANINGS = {
    "normal": "no low-water surcharge or high-water restriction at Kaub",
    "watch_low": "low-water surcharges on barge transport",
    "alert_low": "barge transport no longer guaranteed",
    "watch_high": "high-water shipping restrictions",
    "alert_high": "high water: shipping stops",
}
WEATHER_MEANINGS = {
    "green": "no KNMI warning for the rest of today",
    "amber": "weather may slow port operations and road transport today",
    "red": "weather likely to disrupt port operations and road transport today",
}
STRIKE_MEANINGS = {
    "green": "no active Rotterdam strike found in the last 14 days",
    "amber": "no strike confirmed for today; check the dates",
    "red": "a strike is on today",
}

MEANINGS_TOML = """
[kaub.meaning]
normal = "{normal}"
watch_low = "{watch_low}"
alert_low = "{alert_low}"
watch_high = "{watch_high}"
alert_high = "{alert_high}"
"""
THRESHOLDS_TOML = """
[kaub]
alert_at_or_below = {0}
watch_at_or_below = {1}
watch_above = {2}
alert_above = {3}
"""


def rhine_toml(tmp_path, thresholds=(80, 150, 460, 640), **meanings):
    texts = dict(RHINE_MEANINGS, **meanings)
    path = tmp_path / "rhine.toml"
    path.write_text(THRESHOLDS_TOML.format(*thresholds) + MEANINGS_TOML.format(**texts), encoding="utf-8")
    return path


def render_with(tmp_path, brief, rhine_path=None):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir(parents=True)
    import json
    (briefs_dir / f"{brief['date']}.json").write_text(json.dumps(brief), encoding="utf-8")
    render.render_site(briefs_dir, tmp_path / "site", rhine_path=rhine_path)
    return (tmp_path / "site" / "days" / f"{brief['date']}.html").read_text(encoding="utf-8")


def mini(html, label):
    """One cell of the panel's mini status, by its label."""
    start = html.index('class="panel-status"')
    block = html[start : html.index("</ul>", start)]
    for cell in re.findall(r"<li>.*?</li>", block, flags=re.S):
        if label in cell:
            return cell
    raise AssertionError(f"no mini status cell {label!r}")


def meaning_of(indicator, thresholds=THRESHOLDS, meanings=MEANINGS):
    return render.status_meaning(indicator, thresholds, meanings)


# --- the texts: config and constants ----------------------------------------------------------


def test_the_repo_file_has_a_meaning_for_every_rhine_level():
    assert MEANINGS == RhineMeanings(**RHINE_MEANINGS)


def test_the_thresholds_still_load_from_the_file_with_meanings():
    assert load_rhine() == THRESHOLDS


@pytest.mark.parametrize("change, problem", [
    (lambda text: text.replace('alert_high = "high water: shipping stops"\n', ""), "missing 'alert_high'"),
    (lambda text: text + 'extra = "x"\n', "unknown field 'extra'"),
    (lambda text: text.replace('"high water: shipping stops"', '""'), "alert_high must be one line of text"),
    (lambda text: text.replace('"high water: shipping stops"', '"two\\nlines"'), "alert_high must be one line"),
    (lambda text: text.replace('"high water: shipping stops"', "7"), "alert_high must be one line"),
])
def test_a_bad_meaning_is_refused(tmp_path, change, problem):
    path = rhine_toml(tmp_path)
    path.write_text(change(path.read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(ConfigError, match=re.escape(problem)):
        load_rhine_meanings(path)


def test_a_file_without_meanings_is_refused_for_the_page(tmp_path):
    path = tmp_path / "rhine.toml"
    path.write_text(THRESHOLDS_TOML.format(80, 150, 460, 640), encoding="utf-8")
    assert load_rhine(path) == THRESHOLDS  # the morning pipeline only needs the numbers
    with pytest.raises(ConfigError, match=re.escape("missing [kaub.meaning]")):
        load_rhine_meanings(path)


def test_an_unknown_part_of_kaub_is_still_refused(tmp_path):
    path = rhine_toml(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + "\n[kaub.extra]\nx = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown field 'extra'"):
        load_rhine(path)


def test_the_rhine_meanings_are_not_written_into_the_code_or_templates():
    code = (ROOT / "haven" / "render.py").read_text(encoding="utf-8")
    templates = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "templates").glob("*.html"))
    for text in RHINE_MEANINGS.values():
        assert text not in code and text not in templates


# --- the meaning per level --------------------------------------------------------------------


@pytest.mark.parametrize("value, level, key", [
    (300, "green", "normal"),
    (151, "green", "normal"),
    (460, "green", "normal"),
    (150, "amber", "watch_low"),
    (94, "amber", "watch_low"),
    (461, "amber", "watch_high"),
    (640, "amber", "watch_high"),
    (80, "red", "alert_low"),
    (16, "red", "alert_low"),
    (0, "red", "alert_low"),
    (641, "red", "alert_high"),
    (700, "red", "alert_high"),
])
def test_every_rhine_level_has_its_meaning(value, level, key):
    assert meaning_of(kaub(value, level=level)) == RHINE_MEANINGS[key]


def test_rhine_no_data_has_no_meaning():
    assert meaning_of(kaub(None, level=None)) is None


def test_the_side_comes_from_the_value_even_if_the_thresholds_changed_since():
    # A Watch stored under older thresholds still gets the low or high side's text.
    moved = RhineThresholds(alert_at_or_below=60, watch_at_or_below=100, watch_above=500, alert_above=650)
    assert meaning_of(kaub(140, level="amber"), thresholds=moved) == RHINE_MEANINGS["watch_low"]
    assert meaning_of(kaub(480, level="amber"), thresholds=moved) == RHINE_MEANINGS["watch_high"]


def test_the_rhine_text_comes_from_config(tmp_path):
    meanings = load_rhine_meanings(rhine_toml(tmp_path, alert_low="invented alert text"))
    assert meaning_of(kaub(16, level="red"), meanings=meanings) == "invented alert text"


@pytest.mark.parametrize("level", ["green", "amber", "red"])
def test_every_weather_level_has_its_meaning(level):
    assert meaning_of(weather(level=level)) == WEATHER_MEANINGS[level]


@pytest.mark.parametrize("level", ["green", "amber", "red"])
def test_every_strike_level_has_its_meaning(level):
    assert meaning_of(strike_reading("Strike today · Maasvlakte", level, [link()])) == STRIKE_MEANINGS[level]


def test_the_strike_window_in_the_text_is_the_flags_window():
    assert f"last {strike.WINDOW_DAYS} days" in STRIKE_MEANINGS["green"]


@pytest.mark.parametrize("reading", [
    weather(value=None, level=None, knmi_level=None, hazards=[], issued_at=None, note=None),
    strike_reading(None, None, note="Can't be judged without the AI step."),
])
def test_no_data_has_no_meaning(reading):
    assert meaning_of(reading) is None


def test_an_indicator_without_meanings_has_none():
    assert meaning_of({"key": "ships", "level": "green", "value": 40}) is None


# --- shown on the page: the full dial ---------------------------------------------------------


def test_the_rhine_dial_shows_value_level_and_meaning(tmp_path):
    html = render_with(tmp_path, make_brief(status=[kaub(16, level="red")]))
    text = text_of(dial(html, "rhine"))
    assert "16 cm" in text
    assert "Alert: barge transport no longer guaranteed" in text


@pytest.mark.parametrize("value, level, label, key", [
    (300, "green", "Normal", "normal"), (120, "amber", "Watch", "watch_low"), (500, "amber", "Watch", "watch_high"),
    (40, "red", "Alert", "alert_low"), (660, "red", "Alert", "alert_high"),
])
def test_every_rhine_level_is_shown_with_its_meaning(tmp_path, value, level, label, key):
    html = render_with(tmp_path, make_brief(status=[kaub(value, level=level)]))
    assert f"{label}: {RHINE_MEANINGS[key]}" in text_of(dial(html, "rhine"))
    assert RHINE_MEANINGS[key] in text_of(mini(html, "Rhine water level"))


def test_weather_dial_meaning_and_meteoalarm_requirements_unchanged(tmp_path):
    html = render_with(tmp_path, make_brief(status=[weather()]))
    text = text_of(dial(html, "weather"))
    assert f"Watch: {WEATHER_MEANINGS['amber']}" in text
    assert "KNMI: Code yellow · Wind → Watch" in text          # our mapping next to KNMI's level
    assert "Issued 05:12" in text                              # time of issue
    assert "KNMI via MeteoAlarm" in text                       # KNMI as the source
    assert 'href="https://www.meteoalarm.org"' in dial(html, "weather")
    assert "Warnings at 06:46 · not live" in text
    assert METEOALARM_DISCLAIMER in text                       # verbatim


def test_strike_dial_meaning(tmp_path):
    html = render_with(tmp_path, make_brief(status=[strike_reading("Strike announced for 25 Nov · Maasvlakte",
                                                                   "amber", [link()])]))
    text = text_of(dial(html, "strike"))
    assert f"Watch: {STRIKE_MEANINGS['amber']}" in text
    assert "Invented strike headline 1" in text                # the deciding item is still linked


@pytest.mark.parametrize("reading, key, label", [
    (kaub(None, level=None), "rhine", "Rhine water level"),
    (weather(value=None, level=None, knmi_level=None, hazards=[], issued_at=None, note=None), "weather",
     "Weather warnings"),
    (strike_reading(None, None, note="Can't be judged without the AI step."), "strike", "Strike flag"),
])
def test_no_data_shows_only_no_data(tmp_path, reading, key, label):
    html = render_with(tmp_path, make_brief(status=[reading]))
    assert 'class="lvl-meaning"' not in dial(html, key)
    assert "No data:" not in text_of(dial(html, key))
    cell = mini(html, label)
    assert 'class="mini-meaning"' not in cell
    assert "No data" in text_of(cell)


# --- shown on the page: the panel's mini status -----------------------------------------------


def test_the_mini_status_has_the_meaning_as_a_second_line(tmp_path):
    html = render_with(tmp_path, make_brief(status=[weather(), kaub(16, level="red"),
                                                    strike_reading("Strike today · Maasvlakte", "red", [link()])]))
    for label, meaning in (("Weather warnings", WEATHER_MEANINGS["amber"]),
                           ("Rhine water level", RHINE_MEANINGS["alert_low"]),
                           ("Strike flag", STRIKE_MEANINGS["red"])):
        cell = mini(html, label)
        value_at = cell.index('class="mini-value')
        meaning_at = cell.index('class="mini-meaning"')
        assert value_at < meaning_at                           # under the value
        assert meaning in text_of(cell[meaning_at:])


def test_the_mini_meaning_is_small_and_grey():
    rule = re.search(r"\.mini-meaning\s*\{([^}]*)\}", CSS).group(1)
    assert "var(--ink-2)" in rule
    assert "0.8125rem" in rule  # 13 px, like the panel's other small text (#82)


# --- S7: Watch and Alert marks on the gauge ---------------------------------------------------


def test_gauge_max_stays_700():
    assert rhine.GAUGE_MAX == 700


def test_gauge_marks_sit_at_the_thresholds():
    marks = render.gauge_marks(kaub(16, level="red"), THRESHOLDS)
    assert [(m["cm"], m["level_key"], m["percent"]) for m in marks] == [
        (80, "alert", 11.4), (150, "watch", 21.4), (460, "watch", 65.7), (640, "alert", 91.4),
    ]


def test_a_mark_above_the_gauge_is_left_out():
    marks = render.gauge_marks(dict(kaub(16, level="red"), gauge_max=500), THRESHOLDS)
    assert [m["cm"] for m in marks] == [80, 150, 460]


def test_no_marks_without_a_gauge():
    assert render.gauge_marks(kaub(None, level=None), THRESHOLDS) == []
    assert render.gauge_marks(weather(), THRESHOLDS) == []


def test_the_gauge_draws_its_marks_with_labels(tmp_path):
    html = dial(render_with(tmp_path, make_brief(status=[kaub(16, level="red")])), "rhine")
    for cm, key, percent in ((80, "alert", 11.4), (150, "watch", 21.4), (460, "watch", 65.7), (640, "alert", 91.4)):
        assert re.search(rf'class="gauge-mark mark-{key}" style="bottom: {percent}%"', html)
        assert re.search(rf'class="gauge-tick tick-{key}" style="bottom: {percent}%"[^>]*>{cm}<', html)
    label = re.search(r'class="gauge-board" role="img" aria-label="([^"]*)"', html).group(1)
    assert label == ("Gauge: 16 cm on a scale of 0 to 700 cm. Watch at 150 cm or below and above 460 cm; "
                     "Alert at 80 cm or below and above 640 cm.")


def test_a_changed_threshold_changes_both_the_text_and_the_marks(tmp_path):
    path = rhine_toml(tmp_path / "config", thresholds=(70, 140, 500, 620), watch_low="invented watch text")
    html = render_with(tmp_path, make_brief(status=[kaub(120, level="amber")]), rhine_path=path)
    text = text_of(dial(html, "rhine"))
    assert "Watch: invented watch text" in text
    assert re.search(r'class="gauge-mark mark-watch" style="bottom: 20.0%"', html)   # 140 of 700
    assert re.search(r'class="gauge-mark mark-alert" style="bottom: 88.6%"', html)   # 620 of 700
    assert "invented watch text" in text_of(mini(html, "Rhine water level"))


def test_the_marks_are_told_apart_by_shape_not_only_colour():
    # Spec §2.2: colour is always paired with a shape. Watch = dashed line, Alert = solid.
    watch = re.search(r"\.gauge-mark\.mark-watch\s*\{([^}]*)\}", CSS).group(1)
    alert = re.search(r"\.gauge-mark\.mark-alert\s*\{([^}]*)\}", CSS).group(1)
    assert "dashed" in watch and "solid" in alert


@pytest.fixture(params=["data/sample/briefs"])
def sample_site(tmp_path, request):
    render.render_site(ROOT / request.param, tmp_path / "site")
    return tmp_path / "site"


def test_the_sample_site_shows_meanings_and_marks(sample_site):
    html = (sample_site / "days" / "2026-10-29.html").read_text(encoding="utf-8")
    assert f"Watch: {RHINE_MEANINGS['watch_low']}" in text_of(dial(html, "rhine"))
    assert html.count('class="gauge-mark ') == 4
