"""The whole brief job, offline, through storage (issue #168, owner 28 Nov 2026).

After #166 (a new field's name was refused by the hard rule 13 storage guard at the very last step of
a dry run), the owner asked for one test that runs `haven.run.run` with the **real steps**: collect
through the real `Fetcher` (recorded feeds, every other source unreachable), the rules and the AI
check, the summary batch with its retries through the standard API, weather and Rhine, the brief,
**`storage.write_day` into a temporary data/**, then the site rendered from what was written.

Nothing touches the network and no AI is called: every answer is recorded here. The feeds and the
"articles" in them are invented (hard rule 13); the AI answers are Haven Daily's own kind of output.

What it covers, each at least once: the place fallback (`place_named`), the impact retry for a High or
Medium item (`written_by.why`), an impact left out after sounding confirmed twice
(`impact_left_out`), the English title and its fallback, a place and a tag off the lists
(`unlisted`), a strike with its dates, a headline-only item, items dropped by the rules and by the AI
check, sources that can't be reached, and the three dials.
"""

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from haven import filter as relevance
from haven import render, rhine, storage, weather
from haven import run as runner
from haven.clock import AMSTERDAM
from haven.fetch import Fetcher, RawResponse, TransportError
from haven.summarise import finish_batch
from test_rhine import kaub_answer, lobith_answer, measurement, series

ROOT = Path(__file__).resolve().parent.parent
RUN_AT = datetime(2026, 11, 30, 5, 50, tzinfo=timezone.utc)  # 06:50 in Amsterdam, a Monday
TODAY = "2026-11-30"
HTTP_DATE = "Mon, 30 Nov 2026 05:50:00 GMT"

# --- the recorded feeds (invented) -------------------------------------------------------------

PIN_FEED = "https://pin.portofrotterdam.com/rss.xml"
RIJNMOND_FEED = "https://www.rijnmond.nl/rss/nieuws"
LOADSTAR_FEED = "https://theloadstar.com/feed/"

LOW_WATER = "Invented notice - extreme low water"
ENDED = "Invented notice - buoy maintenance"
ROADWORKS = "Invented: wegwerkzaamheden op de A15 dit weekend"
STRIKE = "Invented: staking aangekondigd bij containerterminal"
FOOTBALL = "Invented: Feyenoord wint van Ajax"
HARBOUR = "Invented: nieuwe regels voor binnenvaart in een haven"
LOADSTAR_KEEP = "Invented: carrier adds a Rotterdam call to its Asia loop"
LOADSTAR_DROP = "Invented: air cargo rates rise in Asia"

# Text that may only ever be in memory (hard rule 13): none of it may reach data/.
LOW_WATER_TEXT = ("Invented notice text. Extreme low water is expected at low tide near the Botlek and the "
                  "Europoort in the coming days. End Date 2 Dec 2026 12:00")
ENDED_TEXT = "Invented notice text about buoy work. End Date 29 Nov 2026 08:00"
ROADWORKS_LEAD = "Invented lead. Door werkzaamheden is de A15 bij de Botlek dit weekend dicht in de richting van de Maasvlakte."
STRIKE_LEAD = "Invented lead. Havenwerkers bij een terminal op de Maasvlakte leggen op 3 december het werk neer."
FOOTBALL_LEAD = "Invented lead about a football match."
HARBOUR_LEAD = "Invented lead. Voor binnenvaartschippers gelden vanaf volgende maand nieuwe regels in een haven."
ARTICLE_TEXTS = (LOW_WATER_TEXT, ENDED_TEXT, ROADWORKS_LEAD, STRIKE_LEAD, FOOTBALL_LEAD, HARBOUR_LEAD)


def entry(title, link, description, date="Mon, 30 Nov 2026 05:00:00 +0000"):
    return (f"<item><title>{html.escape(title)}</title><link>{link}</link><pubDate>{date}</pubDate>"
            f"<description>{html.escape(description)}</description></item>")


def rss(*entries):
    body = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Invented feed</title>'
            "<link>https://feed.test/</link>" + "".join(entries) + "</channel></rss>")
    return RawResponse(200, {"content-type": "application/rss+xml; charset=utf-8"}, body.encode("utf-8"))


def json_answer(data, date=None):
    headers = {"content-type": "application/json; charset=utf-8"}
    if date:
        headers["date"] = date
    return RawResponse(200, headers, json.dumps(data).encode("utf-8"))


ROUTES = {
    PIN_FEED: rss(entry(LOW_WATER, "https://pin.portofrotterdam.com/pin-90001", LOW_WATER_TEXT),
                  entry(ENDED, "https://pin.portofrotterdam.com/pin-90002", ENDED_TEXT)),
    RIJNMOND_FEED: rss(entry(ROADWORKS, "https://www.rijnmond.nl/nieuws/1/wegwerkzaamheden", ROADWORKS_LEAD),
                       entry(STRIKE, "https://www.rijnmond.nl/nieuws/2/staking", STRIKE_LEAD),
                       entry(FOOTBALL, "https://www.rijnmond.nl/nieuws/3/voetbal", FOOTBALL_LEAD),
                       entry(HARBOUR, "https://www.rijnmond.nl/nieuws/4/binnenvaart", HARBOUR_LEAD)),
    LOADSTAR_FEED: rss(entry(LOADSTAR_KEEP, "https://theloadstar.com/invented-asia-loop/", "Invented teaser."),
                       entry(LOADSTAR_DROP, "https://theloadstar.com/invented-air-cargo/", "Invented teaser.")),
    weather.FEED_URL: json_answer({"warnings": []}, date=HTTP_DATE),
    rhine.KAUB_URL: json_answer(kaub_answer(value=176.0, timestamp="2026-11-30T06:30:00+01:00")),
    rhine.LOBITH_URL: json_answer(lobith_answer(series(measurement("2026-11-30T03:50:00.000+01:00", 900.0)))),
}


class RecordedNet:
    """The transport: recorded answers; robots.txt missing everywhere; every other address unreachable
    (those sources fail, and the brief must still be built: hard rule 9)."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, headers, timeout, data=None):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return RawResponse(404, {}, b"")
        if url in ROUTES:
            return ROUTES[url]
        raise TransportError("unreachable in this test")


# --- the recorded AI answers ----------------------------------------------------------------------


def response(data, input_tokens=1500, output_tokens=200):
    content = [SimpleNamespace(type="thinking", thinking="", signature="sig"),
               SimpleNamespace(type="text", text=json.dumps(data))]
    return SimpleNamespace(content=content, stop_reason="end_turn", stop_details=None,
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens))


# The AI check: kept or not (headlines the rules already decided never reach it).
FILTER = {LOW_WATER: True, ROADWORKS: True, STRIKE: True, HARBOUR: True, LOADSTAR_KEEP: True, LOADSTAR_DROP: False}

HEDGED_ROAD = "Trucks to and from the Maasvlakte could face detours this weekend; planners may want to check routes."
CONFIRMED = "Container moves at the terminal will stop on the day; planners must rebook pickups."
STRIKE_TAGS = ["Containers", "Labour"]
NO_STRIKE = None


def summary(summary_text, severity, place, tags, impact=None, strike=NO_STRIKE, headline_en=None):
    data = {"summary": summary_text, "impact": impact, "severity": severity, "place": place, "tags": tags,
            "strike": strike}
    if headline_en is not None:
        data["headline_en"] = headline_en
    return data


# First answer of each item, from the batch.
BATCH = {
    # No place picked, but the summary names Botlek: the place fallback (#164).
    LOW_WATER: summary("A PIN notice warns of extreme low water at low tide near Botlek and Europoort in the "
                       "coming days.", "high", "none", ["Sea access"],
                       impact="Deep-draught vessels could face restrictions around low tide; planners may want "
                              "to check timing."),
    # Medium with no impact: retried once through the standard API (#164).
    ROADWORKS: summary("Roadworks close the A15 near the Botlek this weekend towards the Maasvlakte.", "medium",
                       "a15", ["Truck pickups"], headline_en="A15 near the Botlek closed this weekend for roadworks"),
    # Sounds confirmed: retried; still confirmed: impact left out (#115). No English title: fallback (#155).
    STRIKE: summary("Dock workers at a Maasvlakte terminal plan to stop work on 3 December.", "high",
                    "maasvlakte", STRIKE_TAGS, impact=CONFIRMED,
                    strike={"state": "announced", "location": "Maasvlakte terminal", "affects_rotterdam": True,
                            "start_phrase": "3 december", "end_phrase": "3 december", "match": "new",
                            "strike_id": None}),
    # A place and a tag off the lists: kept in `unlisted`, nothing pinned (the text names no listed place).
    HARBOUR: summary("New rules for inland barge skippers start next month in an unnamed harbour.", "low",
                     "invented-harbour", ["Barge", "Invented tag"],
                     headline_en="New rules for inland barge skippers from next month"),
    # Headline-only: no summary or impact.
    LOADSTAR_KEEP: {"severity": "low", "place": "none", "tags": ["Shipping lines"], "strike": None},
}
# The retries, through the standard API.
STANDARD = {
    ROADWORKS: [summary("Roadworks close the A15 near the Botlek this weekend towards the Maasvlakte.", "medium",
                        "a15", ["Truck pickups"], impact=HEDGED_ROAD,
                        headline_en="A15 near the Botlek closed this weekend for roadworks")],
    STRIKE: [summary("Dock workers at a Maasvlakte terminal plan to stop work on 3 December.", "high",
                     "maasvlakte", STRIKE_TAGS, impact=CONFIRMED,
                     strike={"state": "announced", "location": "Maasvlakte terminal", "affects_rotterdam": True,
                             "start_phrase": "3 december", "end_phrase": "3 december", "match": "new",
                             "strike_id": None})],
}


def headline_of(request: dict) -> str:
    content = request["messages"][-1]["content"]
    text = content if isinstance(content, str) else json.dumps(content)
    return html.unescape(re.search(r"<headline>(.*?)</headline>", text, re.S).group(1))


class RecordedMessages:
    def __init__(self):
        self.calls = []
        self.standard = {headline: list(answers) for headline, answers in STANDARD.items()}
        self.batches = RecordedBatches()

    def create(self, **request):
        self.calls.append(request)
        headline = headline_of(request)
        if request.get("system") == relevance.SYSTEM_PROMPT:  # the AI check
            return response({"kept": FILTER[headline], "reason": "Invented reason."}, 300, 40)
        answers = self.standard.get(headline)
        if not answers:
            raise AssertionError(f"no recorded standard answer left for {headline!r}")
        return response(answers.pop(0))


class RecordedBatches:
    def __init__(self):
        self.requests = []

    def create(self, requests):
        self.requests = list(requests)
        return SimpleNamespace(id="msgbatch_recorded", processing_status="in_progress")

    def retrieve(self, batch_id):
        return SimpleNamespace(id=batch_id, processing_status="ended")

    def results(self, batch_id):
        for request in self.requests:
            answer = response(BATCH[headline_of(request["params"])])
            yield SimpleNamespace(custom_id=request["custom_id"],
                                  result=SimpleNamespace(type="succeeded", message=answer))


class RecordedAI:
    def __init__(self):
        self.messages = RecordedMessages()


# --- the run ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def job(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    net, ai = RecordedNet(), RecordedAI()
    fetcher = Fetcher(transport=net, clock=lambda: 0.0, sleep=lambda s: None)
    steps = runner.Steps(finish_summary=lambda pending: finish_batch(pending, sleep=lambda s: None))
    outcome = runner.run(data_dir=data_dir, utc_now=lambda: RUN_AT, client=ai, fetcher=fetcher, steps=steps)
    site = tmp_path_factory.mktemp("site")
    if outcome.result == runner.WRITTEN:
        render.render_site(data_dir / "briefs", site)
    return SimpleNamespace(outcome=outcome, data_dir=data_dir, site=site, net=net, ai=ai)


def brief_item(job, headline):
    brief = storage.read("briefs", datetime.fromisoformat(TODAY).date(), job.data_dir)
    return next(i for i in brief["items"] if i["headline"] == headline)


def test_the_job_writes_its_three_files_through_storage(job):
    assert job.outcome.result == runner.WRITTEN, job.outcome.message
    day = datetime.fromisoformat(TODAY).date()
    for kind in ("items", "status", "briefs"):
        assert storage.read(kind, day, job.data_dir) is not None, kind


def test_no_article_text_reaches_the_files(job):
    stored = "".join(p.read_text(encoding="utf-8") for p in job.data_dir.rglob("*") if p.is_file())
    for text in ARTICLE_TEXTS:
        assert text not in stored


def test_the_rules_and_the_ai_check_decide(job):
    rows = storage.read("items", datetime.fromisoformat(TODAY).date(), job.data_dir)
    decided = {r["headline"]: (r["filter"]["kept"], r["filter"]["stage"]) for r in rows}
    assert decided[ENDED] == (False, "rules")  # the notice ended
    assert decided[FOOTBALL] == (False, "rules")  # an off-topic word
    assert decided[LOADSTAR_DROP] == (False, "ai")
    assert decided[LOW_WATER] == decided[ROADWORKS] == decided[LOADSTAR_KEEP] == (True, "ai")


def test_the_place_fallback_is_stored_and_logged(job):
    item = brief_item(job, LOW_WATER)
    assert item["map"]["label"] == "Botlek" and item["place_named"] == "Botlek"
    assert any(line.startswith("Place from the item's text: https://pin.portofrotterdam.com/pin-90001: Botlek")
               for line in runner.log_lines(job.outcome.brief))


def test_an_empty_impact_on_a_medium_item_was_retried(job):
    item = brief_item(job, ROADWORKS)
    assert item["impact"] == HEDGED_ROAD
    assert item["written_by"]["api"] == "standard"
    assert item["written_by"]["why"].startswith("rephrase retry: no impact for an item rated medium")
    assert item["map"]["label"] == "Botlek"  # the AI's road, and the item names a more specific place (#138)


def test_an_impact_confirmed_twice_is_left_out_and_the_title_falls_back(job):
    item = brief_item(job, STRIKE)
    assert item["impact"] is None and item["impact_left_out"] is True
    assert item["headline_en"] == "Dock workers at a Maasvlakte terminal plan to stop work on 3 December"
    assert item["strike"] is not None and item["strike"]["start"] == "2026-12-03"


def test_places_and_tags_off_the_lists_stay_in_the_items_file(job):
    rows = storage.read("items", datetime.fromisoformat(TODAY).date(), job.data_dir)
    row = next(r for r in rows if r["headline"] == HARBOUR)
    assert row["unlisted"] == {"places": ["invented-harbour"], "tags": ["Invented tag"]}
    assert row["map"] is None and "place_named" not in row


def test_a_headline_only_item_has_no_summary_or_impact(job):
    item = brief_item(job, LOADSTAR_KEEP)
    assert item["summary"] is None and item["impact"] is None and item["severity"] == "low"


def test_unreachable_sources_are_failure_lines_and_the_brief_is_still_built(job):
    failures = job.outcome.brief["build"]["failures"]
    unreachable = {f["source"] for f in failures if "unreachable in this test" in f["error"]}
    assert unreachable == {"Port of Rotterdam Authority news & press releases", "Contargo business news", "ECT news",
                           "PortsEurope", "Kuehne+Nagel SeaNews"}
    assert job.outcome.brief["build"]["items_kept"] == 5
    # Every line the run log prints about the items, in order (#143, #164).
    assert [line for line in runner.log_lines(job.outcome.brief) if not line.startswith("FAILURE")] == [
        "Place from the item's text: https://pin.portofrotterdam.com/pin-90001: Botlek (the AI picked no listed place)",
        "Outside the batch: https://www.rijnmond.nl/nieuws/1/wegwerkzaamheden: rephrase retry: no impact for an item "
        "rated medium: write one, based only on what the item says",
        'Outside the batch: https://www.rijnmond.nl/nieuws/2/staking: rephrase retry: impact states a consequence as '
        'certain ("will")',
    ]


def test_every_ai_answer_and_page_came_from_the_recordings(job):
    # The run was handed the recorded AI and the recorded transport, so nothing can go out. What it asked:
    # 6 AI checks and 2 standard retries; one batch with the 5 kept items; every recorded feed.
    assert len(job.ai.messages.calls) == 8 and len(job.ai.messages.batches.requests) == 5
    assert {PIN_FEED, RIJNMOND_FEED, LOADSTAR_FEED, weather.FEED_URL, rhine.KAUB_URL, rhine.LOBITH_URL} <= set(job.net.calls)


def test_the_three_dials_are_read(job):
    status = {s["key"]: s for s in job.outcome.brief["status"]}
    assert status["weather"]["value"] == "No warnings"
    assert status["rhine"]["value"] == 176
    assert status["strike"]["level"] in ("amber", "red")  # the announced strike


def test_the_page_built_from_the_files(job):
    page = (job.site / "days" / f"{TODAY}.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r'<script[^>]*id="map-data"[^>]*>(.*?)</script>', page, re.S).group(1))
    assert ("Botlek", "high") in {(c["label"], c["severity"]) for c in data["callouts"]}
    for dutch in (ROADWORKS, STRIKE, HARBOUR):  # every title is English (#153)
        assert html.escape(dutch, quote=False) not in page
    assert "No earlier reading" in page and "yesterday" not in page.lower()
