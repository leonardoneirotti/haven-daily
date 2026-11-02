"""Renderer with real briefs (spec §2.1, §2.2, §2.3, §5.7, §5.11, §5.13; issue #23).

The text helpers (weather mapping, time of issue, item time, strike links, failures per
source) are tested on their own; then fixture briefs in the real §6 shapes are rendered
and the page text is checked. One brief comes straight from the runner (`haven.run`,
every step faked as in tests/test_run.py), so the page is tested on what the morning
job really writes. Headlines are invented.
"""

import json
import re

import pytest

import test_run
from haven import render, storage

BUILT = "2026-11-20T06:52:00+01:00"
DAY = "2026-11-20"
METEOALARM_DISCLAIMER = (
    "Time delays between this website and the www.meteoalarm.org website are possible. For the most "
    "up-to-date awareness information as published by the participating National Meteorological and "
    "Hydrological Services, please refer to www.meteoalarm.org."
)


# --- helpers for building and reading pages ---------------------------------------------


def make_brief(day=DAY, **fields):
    brief = {
        "date": day,
        "sample": False,
        "built_at": f"{day}T06:52:00+01:00",
        "corrections": [],
        "status": [],
        "items": [],
        "build": {"sources_checked": 9, "items_collected": 41, "items_kept": 0, "failures": []},
        "ships": None,
    }
    brief.update(fields)
    return brief


def render_days(tmp_path, *briefs):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir(parents=True)
    for brief in briefs:
        (briefs_dir / f"{brief['date']}.json").write_text(json.dumps(brief), encoding="utf-8")
    render.render_site(briefs_dir, tmp_path / "site")
    return {b["date"]: (tmp_path / "site" / "days" / f"{b['date']}.html").read_text(encoding="utf-8")
            for b in briefs}


def render_day(tmp_path, brief):
    return render_days(tmp_path, brief)[brief["date"]]


def text_of(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def dial(html, key):
    """One status dial in the full "Port status" section."""
    start = html.index(f'data-key="{key}"')
    return html[start : html.index("</li>\n", start)]


def section(html, title_id):
    start = html.index(f'id="{title_id}"')
    return html[start : html.index("</section>", start)]


def weather(**fields):
    reading = {
        "key": "weather", "label": "Weather warnings", "icon": "wind", "value": "Code yellow · Wind",
        "level": "amber", "place": "Zuid-Holland", "knmi_level": "yellow", "hazards": ["Wind"],
        "issued_at": "2026-11-20T05:12:00+01:00", "warnings": [],
        "observed_at": "2026-11-20T06:46:05+01:00", "source_name": "KNMI via MeteoAlarm",
        "source_url": "https://www.meteoalarm.org", "note": "Warnings at 06:46 · not live",
    }
    reading.update(fields)
    return reading


def kaub(value, day=DAY, level="red"):
    return {"key": "rhine", "label": "Rhine water level", "icon": "waves", "value": value, "unit": "cm",
            "place": "Kaub gauge", "level": level, "gauge_max": 700, "observed_at": f"{day}T06:30:00+01:00",
            "source_name": "WSV via PEGELONLINE", "source_url": "https://www.pegelonline.wsv.de/gast/stammdaten?pegelnr=2510",
            "note": None}


def link(n=1, role="decides", state="announced", match="new", day=DAY, published="2026-11-20T05:10:00+01:00",
         source="NL Times"):
    return {"headline": f"Invented strike headline {n}", "url": f"https://nlt.test/{n}", "source": source,
            "published": published, "day": day, "day_page": None if day == DAY else f"days/{day}.html",
            "role": role, "state": state, "match": match}


def strike(value, level, links=(), note=None):
    first = links[0] if links else None
    return {"key": "strike", "label": "Strike flag", "icon": "megaphone", "value": value, "level": level,
            "place": "Derived from kept items", "items": list(links), "observed_at": "2026-11-20T06:46:05+01:00",
            "source_name": first["source"] if first else "Kept items of the last 14 days",
            "source_url": first["url"] if first else None, "note": note}


def news(severity="medium", headline="Invented headline", **fields):
    base = {"severity": severity, "headline": headline, "url": f"https://news.test/{headline.replace(' ', '-')}",
            "source": "ECT news", "language": "en", "published": "2026-11-20T05:10:00+01:00",
            "summary": None if severity is None else "Own-words summary.",
            "impact": None if severity is None else "Something follows for planners.",
            "affects": [] if severity is None else ["Containers"], "access": "full",
            "written_by": None, "map": None, "strike": None}
    base.update(fields)
    return base


# --- weather: KNMI's level next to ours, time of issue (spec §2.2, §5.11) -----------------


def test_weather_mapping_shows_knmi_level_and_hazard_next_to_ours():
    assert render.weather_mapping(weather()) == "KNMI: Code yellow · Wind → Watch"


def test_weather_mapping_names_every_hazard_at_the_deciding_level():
    reading = weather(knmi_level="orange", hazards=["Wind", "Rain"], level="red")
    assert render.weather_mapping(reading) == "KNMI: Code orange · Wind, Rain → Alert"


def test_weather_mapping_red_is_alert():
    assert render.weather_mapping(weather(knmi_level="red", hazards=["Wind"], level="red")) == \
        "KNMI: Code red · Wind → Alert"


def test_weather_mapping_with_no_warnings_is_code_green_normal():
    reading = weather(value="No warnings", level="green", knmi_level="green", hazards=[], issued_at=None)
    assert render.weather_mapping(reading) == "KNMI: Code green → Normal"


def test_weather_mapping_is_absent_on_no_data_and_on_old_readings():
    assert render.weather_mapping(weather(value=None, level=None, knmi_level=None, hazards=[])) is None
    old = {k: v for k, v in weather().items() if k not in ("knmi_level", "hazards")}
    assert render.weather_mapping(old) is None


def test_time_of_issue_same_day_shows_the_clock_time():
    assert render.issue_time("2026-11-20T05:12:00+01:00", "2026-11-20") == "Issued 05:12"


def test_time_of_issue_on_an_earlier_day_shows_the_date():
    assert render.issue_time("2026-11-19T21:30:00+01:00", "2026-11-20") == "Issued 19 Nov 21:30"


def test_time_of_issue_is_shown_in_amsterdam_time():
    assert render.issue_time("2026-11-20T04:12:00Z", "2026-11-20") == "Issued 05:12"


def test_no_time_of_issue_when_there_are_no_warnings():
    assert render.issue_time(None, "2026-11-20") is None


# --- item time: Amsterdam, with the date when it isn't the brief's day ---------------------


@pytest.mark.parametrize("published, shown", [
    ("2026-11-20T05:10:00+01:00", "05:10"),
    ("2026-11-20T04:10:00Z", "05:10"),          # UTC → Amsterdam
    ("2026-11-19T17:20:00+01:00", "19 Nov 17:20"),  # yesterday's article
    ("2026-11-19T23:30:00Z", "00:30"),          # UTC yesterday = Amsterdam today
    ("2026-11-19", "19 Nov"),                   # a page that gives a date only
    ("2026-11-20T05:10:00", "05:10"),           # no zone: Amsterdam time, as in the filter (§5.4)
    (None, None),
    ("yesterday", None),                        # unreadable: nothing shown, never a guess
])
def test_published_label(published, shown):
    assert render.published_label(published, "2026-11-20") == shown


# --- strike line: the linked items (spec §5.7 point 6, §5.7 point 10) -----------------------


def test_deciding_item_of_today_has_no_role_and_no_day_page():
    shown = render.strike_link(link(), ranks=None, today=DAY)
    assert shown["role_label"] is None
    assert shown["meta"] == "NL Times · 20 Nov"
    assert shown["day_link"] is None


def test_unsure_cancellation_says_possibly_called_off():
    shown = render.strike_link(link(role="unsure", state="cancelled", match="unsure"), ranks=None, today=DAY)
    assert shown["role_label"] == "Possibly called off"


def test_unsure_item_that_is_not_a_cancellation_says_possibly_the_same_strike():
    shown = render.strike_link(link(role="unsure", state="ongoing", match="unsure"), ranks=None, today=DAY)
    assert shown["role_label"] == "Possibly the same strike"


def test_named_strike_next_to_a_higher_unsure_item_says_possibly_the_same_as():
    shown = render.strike_link(link(role="possibly the same as"), ranks=None, today=DAY)
    assert shown["role_label"] == "Possibly the same as"


def test_item_date_comes_from_published_in_amsterdam_time():
    shown = render.strike_link(link(published="2026-11-17T23:30:00Z", day="2026-11-18"), ranks=None, today=DAY)
    assert shown["meta"] == "NL Times · 18 Nov"


def test_item_with_a_date_only_published_uses_that_date():
    shown = render.strike_link(link(published="2026-11-16", day="2026-11-17"), ranks=None, today=DAY)
    assert shown["meta"] == "NL Times · 16 Nov"


def test_item_without_a_published_date_uses_its_collection_day():
    shown = render.strike_link(link(published=None, day="2026-11-17"), ranks=None, today=DAY)
    assert shown["meta"] == "NL Times · 17 Nov"


def test_item_from_an_earlier_day_links_to_its_card_on_that_day_page():
    item = link(day="2026-11-17", published="2026-11-17T08:00:00+01:00")
    shown = render.strike_link(item, ranks={item["url"]: 3}, today=DAY)
    assert shown["day_link"] == {"href": "days/2026-11-17.html#item-3", "label": "In the 17 Nov brief"}


def test_item_not_shown_on_its_day_page_links_only_the_original():
    # Kept but not among that day's 5 shown items, or the day has no brief: the day page
    # wouldn't show it, so only the original article is linked.
    item = link(day="2026-11-17")
    assert render.strike_link(item, ranks={"https://other.test/x": 1}, today=DAY)["day_link"] is None
    assert render.strike_link(item, ranks=None, today=DAY)["day_link"] is None


# --- failures per source ------------------------------------------------------------------


def test_failures_are_grouped_per_source_in_first_seen_order():
    failures = [
        {"source": "Strike flag", "error": "item 3 of 17 Nov: unreadable state"},
        {"source": "NL Times", "error": "HTTP 503"},
        {"source": "Strike flag", "error": "item 5 of 18 Nov: unreadable match"},
    ]
    assert render.failure_groups(failures) == [
        {"source": "Strike flag", "errors": ["item 3 of 17 Nov: unreadable state",
                                             "item 5 of 18 Nov: unreadable match"]},
        {"source": "NL Times", "errors": ["HTTP 503"]},
    ]


# --- change since yesterday ---------------------------------------------------------------


def test_rhine_change_is_against_yesterdays_brief(tmp_path):
    pages = render_days(tmp_path, make_brief("2026-11-19", status=[kaub(24, "2026-11-19")]),
                        make_brief(DAY, status=[kaub(21)]))
    assert "−3 cm since yesterday" in text_of(dial(pages[DAY], "rhine"))


def test_no_change_is_claimed_across_a_missing_day(tmp_path):
    pages = render_days(tmp_path, make_brief("2026-11-18", status=[kaub(24, "2026-11-18")]),
                        make_brief(DAY, status=[kaub(21)]))
    card = text_of(dial(pages[DAY], "rhine"))
    assert "No reading yesterday" in card
    assert "since yesterday" not in card


def test_kaub_dial_shows_the_gauge(tmp_path):
    card = dial(render_day(tmp_path, make_brief(status=[kaub(21)])), "rhine")
    assert 'class="gauge"' in card
    assert "21" in text_of(card) and "Kaub gauge" in text_of(card)


# --- the weather dial on the page (MeteoAlarm requirements, spec §2.2) ----------------------


def test_weather_dial_shows_every_meteoalarm_requirement(tmp_path):
    card = dial(render_day(tmp_path, make_brief(status=[weather()])), "weather")
    text = text_of(card)
    assert "KNMI: Code yellow · Wind → Watch" in text          # original level + hazard → ours
    assert "Issued 05:12" in text                              # time of issue
    assert "KNMI via MeteoAlarm" in text                       # KNMI as the source
    assert 'href="https://www.meteoalarm.org"' in card         # link to meteoalarm.org
    assert "Warnings at 06:46 · not live" in text              # not live
    assert METEOALARM_DISCLAIMER in text                       # the disclaimer, verbatim


def test_weather_dial_with_no_warnings_shows_no_time_of_issue(tmp_path):
    reading = weather(value="No warnings", level="green", knmi_level="green", hazards=[], issued_at=None)
    text = text_of(dial(render_day(tmp_path, make_brief(status=[reading])), "weather"))
    assert "KNMI: Code green → Normal" in text
    assert "Issued" not in text
    assert "Read at 06:46" in text
    assert METEOALARM_DISCLAIMER in text


def test_weather_dial_on_no_data_keeps_the_link_and_disclaimer(tmp_path):
    reading = weather(value=None, level=None, knmi_level=None, hazards=[], issued_at=None, note=None)
    card = dial(render_day(tmp_path, make_brief(status=[reading])), "weather")
    assert "No data" in text_of(card)
    assert "KNMI:" not in text_of(card)
    assert 'href="https://www.meteoalarm.org"' in card
    assert METEOALARM_DISCLAIMER in text_of(card)


# --- the strike dial on the page -------------------------------------------------------------


def test_strike_alert_links_the_deciding_item(tmp_path):
    reading = strike("Strike today · Maasvlakte", "red", [link()])
    card = dial(render_day(tmp_path, make_brief(status=[reading])), "strike")
    text = text_of(card)
    assert "Strike today · Maasvlakte" in text
    assert 'href="https://nlt.test/1"' in card
    assert "Invented strike headline 1" in text and "NL Times · 20 Nov" in text


def test_strike_watch_from_an_earlier_day_links_its_day_page(tmp_path):
    earlier = make_brief("2026-11-17", items=[news("high", "Other"), news("medium", "Invented strike headline 1",
                                                                        url="https://nlt.test/1")])
    reading = strike("Strike announced for 25 Nov · Maasvlakte", "amber",
                     [link(day="2026-11-17", published="2026-11-17T08:00:00+01:00")])
    pages = render_days(tmp_path, earlier, make_brief(status=[reading]))
    card = dial(pages[DAY], "strike")
    assert "Strike announced for 25 Nov · Maasvlakte" in text_of(card)
    assert 'href="../days/2026-11-17.html#item-2"' in card
    assert "In the 17 Nov brief" in text_of(card)


def test_strike_unsure_pair_shows_both_items(tmp_path):
    reading = strike("Strike announced for 25 Nov · Maasvlakte", "amber", [
        link(1, published="2026-11-18T08:00:00+01:00", day="2026-11-18"),
        link(2, role="unsure", state="cancelled", match="unsure"),
    ])
    text = text_of(dial(render_day(tmp_path, make_brief(status=[reading])), "strike"))
    assert "Invented strike headline 1" in text and "NL Times · 18 Nov" in text
    assert "Possibly called off" in text and "Invented strike headline 2" in text


def test_strike_normal_after_cancellation_links_the_cancellation(tmp_path):
    reading = strike("Strike called off · Maasvlakte", "green", [link(state="cancelled", match="same")])
    card = dial(render_day(tmp_path, make_brief(status=[reading])), "strike")
    assert "Strike called off · Maasvlakte" in text_of(card)
    assert 'href="https://nlt.test/1"' in card


def test_strike_with_nothing_linked_renders_without_a_link(tmp_path):
    # The crash found in #22: source_url null (Normal with no strike).
    card = dial(render_day(tmp_path, make_brief(status=[strike("No active strike", "green")])), "strike")
    assert "No active strike" in text_of(card)
    assert 'href="None"' not in card and "href=\"\"" not in card


def test_strike_no_data_when_the_ai_was_unavailable_renders(tmp_path):
    reading = strike(None, None, note="Can't be judged without the AI step.")
    card = dial(render_day(tmp_path, make_brief(status=[reading])), "strike")
    assert "No data" in text_of(card) and "Can't be judged without the AI step." in text_of(card)


# --- briefs written by the runner (#22) render ----------------------------------------------


def test_a_brief_written_by_the_runner_renders(tmp_path):
    data = tmp_path / "data"
    outcome, _ = test_run.go(data)
    assert outcome.exit_code == 0
    render.render_site(data / "briefs", tmp_path / "site")
    html = (tmp_path / "site" / "days" / f"{test_run.TODAY.isoformat()}.html").read_text(encoding="utf-8")
    assert "Invented headline 1" in html
    assert "No active strike" in text_of(dial(html, "strike"))


def test_a_reduced_brief_written_by_the_runner_renders(tmp_path):
    data = tmp_path / "data"
    outcome, _ = test_run.go(data, test_run.Fake(filter_down=True), last_trigger=True)
    assert outcome.exit_code == 0
    render.render_site(data / "briefs", tmp_path / "site")
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "No data" in text_of(dial(html, "strike"))
    assert "The AI step was unavailable this morning" in text_of(html)


# --- items ----------------------------------------------------------------------------------


def news_card(html, rank):
    start = html.index(f'id="item-{rank}"')
    return html[start : html.index("</li>", start)]


def test_headline_only_item_with_a_severity_says_rated_from_headline_only(tmp_path):
    item = news("medium", "Invented headline-only story", source="NL Times", access="headline-only",
                summary=None, impact=None)
    card = text_of(news_card(render_day(tmp_path, make_brief(items=[item])), 1))
    assert re.search(r"medium rated from headline only", card)
    assert "Not enough information" in card
    assert "Headline only: this source is paywalled or its terms don't allow a summary." in card


def test_unrated_headline_only_item_is_not_called_rated(tmp_path):
    item = news(None, "Invented headline-only story", access="headline-only")
    card = text_of(news_card(render_day(tmp_path, make_brief(items=[item])), 1))
    assert "rated from headline only" not in card
    assert "The AI step failed for this item" in card


def test_full_item_is_not_called_headline_only(tmp_path):
    card = text_of(news_card(render_day(tmp_path, make_brief(items=[news()])), 1))
    assert "headline only" not in card.lower()


def test_item_from_yesterday_shows_its_date(tmp_path):
    item = news(published="2026-11-19T17:20:00+01:00")
    card = text_of(news_card(render_day(tmp_path, make_brief(items=[item])), 1))
    assert "19 Nov 17:20" in card


def test_item_with_no_published_time_renders(tmp_path):
    card = news_card(render_day(tmp_path, make_brief(items=[news(published=None)])), 1)
    assert "<time" not in card


# --- ships in v1 -------------------------------------------------------------------------------


def test_ships_dial_in_v1_says_no_data_and_that_ships_are_not_collected_yet(tmp_path):
    html = render_day(tmp_path, make_brief())
    text = text_of(dial(html, "ships"))
    assert "No data" in text
    assert "Ship positions are not collected yet" in text
    assert "The AIS snapshot failed" not in text_of(html)


def test_chart_legend_has_no_ship_symbols_when_there_are_no_ships(tmp_path):
    html = render_day(tmp_path, make_brief())
    legend = html[html.index('class="chart-legend"') : html.index("</div>", html.index('class="chart-legend"'))]
    assert "Container" not in legend and "At anchor" not in legend


# --- how this brief was made --------------------------------------------------------------------


def test_build_notes_show_counts_summaries_and_grouped_failures(tmp_path):
    build = {"sources_checked": 9, "items_collected": 41, "items_kept": 7, "summaries": {"batch": 5, "fallback": 1},
             "failures": [{"source": "Strike flag", "error": "first problem"},
                          {"source": "NL Times", "error": "HTTP 503"},
                          {"source": "Strike flag", "error": "second problem"}]}
    items = [news("low", f"Item {n}") for n in range(7)]
    notes = section(render_day(tmp_path, make_brief(items=items, build=build)), "build-title")
    text = text_of(notes)
    assert "Sources checked 9" in text and "Items collected 41" in text
    assert "Kept as relevant 7" in text and "Shown (max 5) 5" in text
    assert "Summaries in the batch 5" in text and "Summaries by the fallback 1" in text
    assert text.count("Strike flag") == 1
    assert "first problem" in text and "second problem" in text and "HTTP 503" in text


def test_build_notes_without_summaries_field_still_render(tmp_path):
    notes = text_of(section(render_day(tmp_path, make_brief()), "build-title"))
    assert "Summaries in the batch" not in notes


def test_build_notes_list_corrections(tmp_path):
    brief = make_brief(corrections=[{"at": "2026-11-20T09:14:00+01:00", "note": "Item 2: wrong terminal."}])
    assert "Corrected 09:14 Item 2: wrong terminal." in text_of(section(render_day(tmp_path, brief), "build-title"))


# --- the sample briefs use the real status shapes ----------------------------------------------


def test_sample_weather_and_strike_readings_have_the_real_fields():
    for path in sorted(render.PROJECT_DIR.joinpath("data", "sample", "briefs").glob("*.json")):
        brief = json.loads(path.read_text(encoding="utf-8"))
        by_key = {s["key"]: s for s in brief["status"]}
        assert {"knmi_level", "hazards", "issued_at"} <= set(by_key["weather"]), path.name
        assert by_key["weather"]["source_url"] == "https://www.meteoalarm.org", path.name
        assert isinstance(by_key["strike"]["items"], list), path.name
