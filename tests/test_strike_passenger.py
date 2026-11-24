"""Strike flag: passenger transport strikes never turn it red (issue #130; spec §5.4 rule E, §5.7).

The dry run of 24 Nov 2026 (run 45371906608) turned the flag red for a public-transport strike
("ov-staking") mentioned in an RTV Rijnmond traffic item. Fixed in two layers (owner, 24 Nov 2026):

1. the summariser's prompt: a passenger public-transport strike is `affects_rotterdam: false`;
2. a code check: a strike can be **Alert (red)** only when the item's own text (its summary, or
   its headline when it has none) names a strike **and** the port or freight transport, **and no**
   passenger public transport. Otherwise it is capped at **Watch (amber)**: still shown and
   linked, never red (owner's choices, 24 Nov 2026).

The Maastunnel headline and its stored summary are the dry run's own record (a headline, and our
own words). The other headlines are invented.
"""

from datetime import date, timedelta

import pytest

from haven import strike, summarise
from haven.config import Source, load_places, load_tag_list

TODAY = date(2026, 11, 24)
SOURCES = (Source(id="rtv-rijnmond", name="RTV Rijnmond", verdict="use"),
           Source(id="nltimes", name="NL Times", verdict="headline-only"))
PLACES = load_places()

MAASTUNNEL_HEADLINE = "Enorme vertraging bij Maastunnel door storing, te hoge vrachtwagens en ov-staking"
MAASTUNNEL_SUMMARY = ("On Monday morning the Maastunnel in Rotterdam saw hours of extreme congestion. "
                      "A malfunction combined with other problems caused delays of more than an hour "
                      "for drivers.")


def record(headline, summary=None, *, state="ongoing", start=None, end=None, published=None,
           source="nltimes", n=1):
    return {
        "source": source,
        "headline": headline,
        "summary": summary,
        "url": f"https://example.org/strike/{n}",
        "published": published or f"{TODAY.isoformat()}T07:00:00+01:00",
        "access": "headline-only" if summary is None else "full",
        "filter": {"kept": True, "stage": "ai", "reason": "invented"},
        "strike": {"state": state, "location": "Rotterdam", "affects_rotterdam": True,
                   "start": start.isoformat() if start else None,
                   "end": end.isoformat() if end else None,
                   "match": "new", "strike_id": f"strike-2026-11-24-{n}"},
    }


def flag(*records):
    return strike.flag_from_items([(TODAY, list(records))], TODAY, SOURCES, places=PLACES)


# --- the code check -------------------------------------------------------------------------------


@pytest.mark.parametrize("headline", [
    "Dockers strike at ECT Delta today",                                      # en, port workers
    "Staking bij containerterminals op de Maasvlakte",                        # nl, terminals
    "Loodsen leggen werk neer: staking legt scheepvaart Rotterdam stil",      # nl, pilots
    "Streik bei der Güterbahn: Containerzüge nach Rotterdam fallen aus",       # de, rail freight
    "Barge skippers strike on the Rhine, inland shipping to Rotterdam halted",
    "Staking van sluiswachters bij de Rozenburgsesluis",                      # lock staff, a place name
    "Truck drivers' strike blocks access to Waalhaven terminals",
])
def test_a_port_or_freight_strike_headline_can_go_red(headline):
    assert strike.port_or_freight_strike(record(headline), PLACES) is True


@pytest.mark.parametrize("headline", [
    MAASTUNNEL_HEADLINE,                                                      # the dry run (#130)
    "Let op: veel bussen rijden niet door staking in streekvervoer",          # dropped by the filter that day
    "RET-staking: metro's en trams rijden niet in Rotterdam",
    "Bus strike in the Rotterdam region cuts services to the port area",      # passenger, even near the port
    "Public transport strike: no trams or buses in Rotterdam on Thursday",
    "Air traffic controllers strike at Liège and Brussels airports",          # no port or freight word
    "ECT Delta closes early because of the storm",                            # no strike word
])
def test_a_passenger_or_unclear_strike_headline_cannot_go_red(headline):
    assert strike.port_or_freight_strike(record(headline), PLACES) is False


def test_the_summary_is_checked_when_there_is_one_not_the_headline():
    # The Maastunnel item as stored on 24 Nov: its summary mentions no strike at all.
    assert strike.port_or_freight_strike(record(MAASTUNNEL_HEADLINE, MAASTUNNEL_SUMMARY), PLACES) is False
    # A port strike headline doesn't help when the item's own summary says nothing of a strike...
    quiet = record("Dockers strike at ECT Delta today", "Container handling at ECT Delta was slow on Monday.")
    assert strike.port_or_freight_strike(quiet, PLACES) is False
    # ...and a summary that says it is enough, whatever the headline.
    said = record("Actie bij de Maasvlakte", "Lashing crews at Euromax went on strike for 24 hours on Monday.")
    assert strike.port_or_freight_strike(said, PLACES) is True


def test_place_names_from_the_place_list_count_as_the_port():
    euromax = record("Euromax workers strike for 24 hours")  # "workers" alone isn't freight
    assert strike.port_or_freight_strike(euromax, PLACES) is True
    assert strike.port_or_freight_strike(euromax, ()) is False


def test_words_match_whole_words_only():
    # "port" must not match "transport", "airport" or "passport"; "bus" must not match "business".
    airport = record("Strike at the airport hits passport checks and transport links")
    assert strike.port_or_freight_strike(airport, PLACES) is False
    business = record("Business as usual: strike at ECT Delta ends")
    assert strike.port_or_freight_strike(business, PLACES) is True


def test_an_item_with_no_text_is_not_a_confirmed_port_strike():
    assert strike.port_or_freight_strike(record(None), PLACES) is False
    assert strike.port_or_freight_strike(record("", "  "), PLACES) is False


# --- the flag: capped at Watch, never dropped -----------------------------------------------------


def test_the_dry_run_case_is_watch_not_alert():
    maastunnel = record(MAASTUNNEL_HEADLINE, MAASTUNNEL_SUMMARY, source="rtv-rijnmond",
                        published="2026-11-23T14:27:50+01:00")
    result = flag(maastunnel)
    assert result.level == "amber"                       # never red without a port or freight strike
    assert result.value == "Strike ongoing · Rotterdam"  # the same words, at Watch
    assert [shown["url"] for shown in result.items] == [maastunnel["url"]]  # still linked


@pytest.mark.parametrize("headline", [MAASTUNNEL_HEADLINE,
                                      "Let op: veel bussen rijden niet door staking in streekvervoer"])
def test_a_headline_only_passenger_strike_is_watch(headline):
    assert flag(record(headline)).level == "amber"


def test_a_port_strike_still_goes_red():
    assert flag(record("Dockers strike at ECT Delta today")).level == "red"
    assert flag(record("Staking bij ECT Delta", state="announced", start=TODAY, end=TODAY)).level == "red"


def test_a_passenger_strike_announced_for_today_is_watch():
    bus = record("Busstaking in de regio Rotterdam vandaag", state="announced", start=TODAY, end=TODAY)
    result = flag(bus)
    assert result.level == "amber"
    assert result.value == "Strike today · Rotterdam"


def test_watch_levels_are_unchanged_by_the_check():
    later = TODAY + timedelta(days=3)
    assert flag(record("Busstaking aangekondigd", state="announced", start=later, end=later)).level == "amber"
    assert flag(record("Dockers announce a strike at ECT Delta", state="announced",
                       start=later, end=later)).level == "amber"


def test_a_port_strike_outranks_a_capped_passenger_strike():
    bus = record(MAASTUNNEL_HEADLINE, n=1)
    port = record("Dockers strike at ECT Delta today", n=2, published=f"{TODAY.isoformat()}T06:00:00+01:00")
    result = flag(bus, port)
    assert result.level == "red"
    assert result.items[0]["url"] == port["url"]


def test_flag_from_items_reads_the_place_list_itself_when_none_is_given():
    euromax = record("Euromax workers strike for 24 hours")
    assert strike.flag_from_items([(TODAY, [euromax])], TODAY, SOURCES).level == "red"


# --- the summariser's instruction -----------------------------------------------------------------


def test_the_prompt_says_a_passenger_transport_strike_does_not_affect_rotterdam():
    prompt = summarise.system_prompt(load_places(), load_tag_list())
    line = next(line for line in prompt.splitlines() if line.startswith("- affects_rotterdam:"))
    rule = line + prompt.split(line, 1)[1].split("\n- ", 1)[0]  # the line and its continuation
    assert "passenger public transport" in rule
    for word in ("bus", "tram", "metro", '"ov"'):
        assert word in rule
    assert "false" in rule
