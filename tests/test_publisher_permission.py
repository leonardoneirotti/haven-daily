"""RTV Rijnmond's written permission for AI summaries (issue #107; spec §3 rule 12, §4, §11).

RTV Rijnmond gave written permission on 19 Nov 2026 (docs/permissions/2026-11-19-rtv-rijnmond.md)
for AI-generated summaries of one or two sentences, on conditions. What these tests hold in place:

- a publisher's written permission overrides its robots.txt AI block, **for that publisher only**
  (owner's hard rule 12 decision, 19 Nov 2026); robots.txt Disallow rules still apply (rule 4);
- the permission is one line in config/sources.toml; deleting it makes the source headline-only
  again (withdrawal, condition 6);
- the summary is written from the lead paragraph in the RSS feed only (owner, 19 Nov 2026): no
  article page is opened;
- the summary is at most two sentences, checked in code (condition 1);
- the impact line, allowed since 23 Nov 2026 (docs/permissions/2026-11-23-rtv-rijnmond.md, #115),
  is labelled as Haven Daily's interpretation, not RTV Rijnmond's; the prompt asks for consequences
  as possible ("could", "may"), never confirmed, from the lead paragraph's facts only; and a code
  check rejects confirmed-sounding wording (one retry, then no impact line);
- next to every such summary (short note, owner's wording, PR #108 review) and on How it works
  (full wording): Haven Daily is independent and RTV Rijnmond is not responsible for the
  AI-generated summaries.

Headlines and article text are invented (hard rule 13).
"""

import json
import re
import textwrap
from datetime import date, datetime
from pathlib import Path

import pytest

from haven import collect, summarise
from haven.clock import AMSTERDAM
from haven.config import ConfigError, Permission, Source, load_sources
from haven.feeds import Item, collect_feed
from haven.fetch import RawResponse
from haven.render import permission_note
from tests.test_cards_panel import card_of, panel_entries
from tests.test_feeds import entry, fetcher_for, rss, xml
from tests.test_method_page import render_method
from tests.test_render_real import make_brief, news, render_day, text_of
from tests.test_summarise import FakeClient, answer, item as ect_item

ROOT = Path(__file__).resolve().parent.parent
SOURCES_TOML = ROOT / "config" / "sources.toml"
PERMISSION_FILE = "docs/permissions/2026-11-19-rtv-rijnmond.md"

TODAY = date(2026, 11, 20)
READ_AT = datetime(2026, 11, 20, 6, 45, tzinfo=AMSTERDAM)

RIJNMOND_FEED = "https://www.rijnmond.nl/rss/nieuws"
RIJNMOND_ROBOTS = "https://www.rijnmond.nl/robots.txt"
ARTICLE_URL = "https://www.rijnmond.nl/nieuws/1000001/invented-article"
# Like the real robots.txt (31 Oct 2026, docs/source-tests-2026-10-31.md): generic bots allowed,
# AI crawlers named and blocked.
ROBOTS_WITH_AI_BLOCK = ("User-agent: *\nAllow: /\nDisallow: /content/\n\n"
                        "User-agent: ClaudeBot\nUser-agent: anthropic-ai\nDisallow: /\n")
LEAD = ("Invented lead paragraph. Dock workers at an invented Waalhaven terminal stopped work this "
        "morning after a dispute about night shifts, the union said.")

# A permission without an impact line (RTV Rijnmond's from 19 to 23 Nov 2026): still the generic case.
PERMISSION = Permission(file=PERMISSION_FILE, granted=date(2026, 11, 19), max_sentences=2, impact=False)
# RTV Rijnmond's since 23 Nov 2026 (#115): the impact line is allowed too, on its conditions.
WITH_IMPACT = Permission(file=PERMISSION_FILE, granted=date(2026, 11, 19), max_sentences=2, impact=True)


def rijnmond(permission=PERMISSION) -> Source:
    return Source(id="rtv-rijnmond", name="RTV Rijnmond", verdict="headline-only", urls=(RIJNMOND_FEED,),
                  access="rss", language="nl", why="Invented reason.", home="https://www.rijnmond.nl/",
                  permission=permission)


def real(source_id: str) -> Source:
    return next(s for s in load_sources() if s.id == source_id)


def robots(text: str) -> RawResponse:
    return RawResponse(200, {"content-type": "text/plain"}, text.encode("utf-8"))


def write(tmp_path, text):
    path = tmp_path / "sources.toml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


SOURCE_TABLE = """
[[source]]
id = "rtv-rijnmond"
name = "RTV Rijnmond"
verdict = "{verdict}"
why = "Invented reason."
urls = ["https://www.rijnmond.nl/rss/nieuws"]
access = "rss"
language = "nl"
{permission}
"""
GOOD_LINE = ('permission = { file = "docs/permissions/2026-11-19-rtv-rijnmond.md", granted = 2026-11-19, '
             'max_sentences = 2, impact = false }')


def load_one(tmp_path, permission=GOOD_LINE, verdict="headline-only") -> Source:
    [source] = load_sources(write(tmp_path, SOURCE_TABLE.format(verdict=verdict, permission=permission)))
    return source


# --- config: the permission line --------------------------------------------------------------


def test_the_permission_line_is_read_and_lifts_headline_only_to_use(tmp_path):
    source = load_one(tmp_path)
    assert source.permission == PERMISSION
    assert source.verdict == "headline-only"  # what the source allows on its own
    assert source.effective_verdict == "use"  # what Haven Daily does with the permission


def test_without_a_permission_line_the_verdict_is_unchanged(tmp_path):
    source = load_one(tmp_path, permission="")
    assert source.permission is None
    assert source.effective_verdict == "headline-only"


@pytest.mark.parametrize("verdict", ["use", "drop"])
def test_a_permission_only_lifts_a_headline_only_source(tmp_path, verdict):
    with pytest.raises(ConfigError, match="permission.*headline-only"):
        load_one(tmp_path, verdict=verdict)


@pytest.mark.parametrize("line, problem", [
    ('permission = "yes"', "must be written as"),
    (GOOD_LINE.replace(", impact = false", ""), "missing 'impact'"),
    (GOOD_LINE.replace("impact = false", "impact = false, scope = \"all\""), "unknown field 'scope'"),
    (GOOD_LINE.replace("impact = false", 'impact = "no"'), "impact must be true or false"),
    (GOOD_LINE.replace("max_sentences = 2", "max_sentences = 0"), "max_sentences must be a whole number"),
    (GOOD_LINE.replace("max_sentences = 2", "max_sentences = true"), "max_sentences must be a whole number"),
    (GOOD_LINE.replace("granted = 2026-11-19", 'granted = "19 Nov"'), "granted must be a date"),
    (GOOD_LINE.replace("docs/permissions/2026-11-19-rtv-rijnmond.md", "permission.txt"),
     "file must be a .md file in docs/permissions/"),
])
def test_a_bad_permission_line_stops_the_run_with_a_clear_message(tmp_path, line, problem):
    with pytest.raises(ConfigError, match=re.escape(problem)):
        load_one(tmp_path, permission=line)


# --- the real config ----------------------------------------------------------------------------


def test_rijnmond_has_written_permission_in_the_real_config():
    source = real("rtv-rijnmond")
    assert source.verdict == "headline-only"  # its own robots.txt AI block and terms
    assert source.permission == WITH_IMPACT
    assert source.effective_verdict == "use"
    assert (ROOT / source.permission.file).is_file()


def test_the_permission_is_for_rijnmond_only():
    assert [s.id for s in load_sources() if s.permission] == ["rtv-rijnmond"]


def test_withdrawal_is_deleting_one_line(tmp_path):
    """Condition 6: RTV Rijnmond may withdraw its permission at any time (spec §11)."""
    lines = SOURCES_TOML.read_text(encoding="utf-8").splitlines(keepends=True)
    permission_lines = [n for n, line in enumerate(lines) if line.startswith("permission")]
    assert len(permission_lines) == 1
    withdrawn = write(tmp_path, "".join(line for n, line in enumerate(lines) if n not in permission_lines))
    source = next(s for s in load_sources(withdrawn) if s.id == "rtv-rijnmond")
    assert source.permission is None and source.effective_verdict == "headline-only"
    assert "terms" in source.why.lower() and "ai crawlers" in source.why.lower()  # still true then


@pytest.mark.parametrize("name", ["2026-11-18-rtv-rijnmond.md", "2026-11-19-rtv-rijnmond.md",
                                  "2026-11-23-rtv-rijnmond.md"])
def test_the_saved_replies_name_name_role_and_date_but_no_email_address(name):
    text = (ROOT / "docs" / "permissions" / name).read_text(encoding="utf-8")
    assert "Daan Verberne" in text and "Sales, Marketing and Communications Manager" in text
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)


def test_the_reply_of_19_november_records_all_six_conditions():
    text = (ROOT / PERMISSION_FILE).read_text(encoding="utf-8")
    assert "19 November 2026" in text
    for words in ("one or two sentences", "clearly credited", "accurately reflect",
                  "non-commercial", "discussed with us in advance", "withdraw"):
        assert words in text


# --- fetcher and feed: the AI block is overridden for this publisher only ----------------------


def test_with_permission_the_ai_block_does_not_make_the_source_headline_only():
    fetcher, _ = fetcher_for({RIJNMOND_ROBOTS: robots(ROBOTS_WITH_AI_BLOCK)})
    access = fetcher.source_access(rijnmond())
    assert access.verdict == "use" and access.note is None


def test_without_permission_the_same_ai_block_keeps_it_headline_only():
    fetcher, _ = fetcher_for({RIJNMOND_ROBOTS: robots(ROBOTS_WITH_AI_BLOCK)})
    assert fetcher.source_access(rijnmond(permission=None)).verdict == "headline-only"


def test_another_source_on_a_site_with_an_ai_block_is_not_lifted_by_rijnmonds_permission():
    other = Source(id="other", name="Other News", verdict="use", urls=("https://other.test/feed",),
                   access="rss", language="en")
    fetcher, _ = fetcher_for({"https://other.test/robots.txt": robots("User-agent: ClaudeBot\nDisallow: /\n")})
    access = fetcher.source_access(other)
    assert access.verdict == "headline-only" and "ClaudeBot" in access.note


def test_robots_disallow_rules_still_apply_with_permission():
    """The permission covers AI use, not crawling: hard rule 4 is unchanged."""
    fetcher, net = fetcher_for({RIJNMOND_ROBOTS: robots("User-agent: *\nDisallow: /rss/\n"),
                                RIJNMOND_FEED: xml(rss(entry()))})
    result = collect_feed(rijnmond(), fetcher)
    assert result.items == [] and "robots.txt" in result.failures[0]["error"]
    assert RIJNMOND_FEED not in net.calls


def test_the_lead_paragraph_in_the_feed_is_the_text_and_no_article_page_is_opened():
    body = rss(entry(title="Invented: strike at Waalhaven", link=ARTICLE_URL,
                     extra=f"<description>{LEAD}</description>"))
    fetcher, net = fetcher_for({RIJNMOND_ROBOTS: robots(ROBOTS_WITH_AI_BLOCK), RIJNMOND_FEED: xml(body)})

    result = collect_feed(real("rtv-rijnmond"), fetcher)

    assert result.failures == []
    [found] = result.items
    assert (found.access, found.article_text, found.snippet) == ("full", LEAD, LEAD)
    done = collect.add_article_text([found], load_sources(), fetcher)
    assert done.items == [found] and done.failures == []
    assert ARTICLE_URL not in net.calls


def test_an_item_with_no_lead_paragraph_is_rated_from_its_headline_and_no_page_is_opened():
    no_lead = Item(source="rtv-rijnmond", headline="Invented headline", url=ARTICLE_URL,
                   published="2026-11-20T05:00:00+01:00", language="nl", access="full")
    fetcher, net = fetcher_for({})
    done = collect.add_article_text([no_lead], load_sources(), fetcher)
    assert done.items == [no_lead]
    assert done.failures == [{"source": "RTV Rijnmond", "error": f"{ARTICLE_URL}: {collect.NO_LEAD}"}]
    assert net.calls == []


# --- summariser: at most two sentences, no impact -----------------------------------------------


def rijnmond_item(**changes) -> Item:
    fields = dict(source="rtv-rijnmond", headline="Invented: strike at Waalhaven terminal", url=ARTICLE_URL,
                  published="2026-11-20T05:00:00+01:00", language="nl", access="full", snippet=LEAD,
                  article_text=LEAD, filter={"kept": True, "stage": "ai", "reason": "invented"})
    fields.update(changes)
    return Item(**fields)


TWO = "Staff at a Waalhaven terminal walked out this morning. The row is about night shifts."
# Impacts as the prompt asks for them (consequences as possible), and as it doesn't (confirmed).
HEDGED = "Container pickups at the terminal could be delayed today. Planners may want to check slots."
CONFIRMED = "Container pickups at the terminal will be delayed today. Planners should rebook slots."
THREE = TWO + " Talks are planned."


def rijnmond_answer(summary=TWO, **changes):
    data = {"summary": summary, "severity": "high", "place": "none", "tags": ["Labour"], "strike": None}
    data.update(changes)
    return answer(json.dumps(data))


def run(items, *answers, sources=None):
    client = FakeClient(*answers)
    kw = {} if sources is None else {"sources": sources}
    result = summarise.summarise(list(items), client, known=[], today=TODAY, read_at=READ_AT, **kw)
    return result, client


@pytest.mark.parametrize("text, count", [
    ("One sentence.", 1),
    ("One sentence without a full stop", 1),
    (TWO, 2),
    (THREE, 3),
    ("Is it over? Not yet! Work stops.", 3),
    ("The water is 3.5 metres deep. Barges wait.", 2),
    ('The union said "no." Work stopped.', 2),
    ("", 0),
])
def test_sentences_are_counted(text, count):
    assert summarise.sentence_count(text) == count


def test_the_request_asks_for_a_summary_but_no_impact_and_names_the_limit():
    request = summarise._request(rijnmond_item(), summarise.SUMMARY_MODEL, "invented system prompt", [],
                                 TODAY, READ_AT, permission=PERMISSION)
    properties = request["output_config"]["format"]["schema"]["properties"]
    assert "summary" in properties and "impact" not in properties
    content = request["messages"][0]["content"]
    assert f"<article>{LEAD}</article>" in content
    assert "at most 2 sentences" in content and "no impact" in content


def test_a_two_sentence_summary_is_accepted_with_no_impact():
    result, client = run([rijnmond_item()], rijnmond_answer(), sources=(rijnmond(),))
    [done] = result.items
    assert done.ai["summary"] == TWO and done.ai["impact"] is None
    assert result.failures == [] and len(client.messages.calls) == 1


def test_the_real_config_applies_rijnmonds_limits():
    result, client = run([rijnmond_item()], rijnmond_answer(impact=HEDGED))
    assert "impact" in client.messages.calls[0]["output_config"]["format"]["schema"]["properties"]
    assert "Haven Daily's own interpretation" in client.messages.calls[0]["messages"][0]["content"]
    assert result.items[0].ai["summary"] == TWO and result.items[0].ai["impact"] == HEDGED


def test_three_sentences_get_one_retry_then_the_shorter_answer_is_used():
    result, client = run([rijnmond_item()], rijnmond_answer(THREE), rijnmond_answer(), sources=(rijnmond(),))
    assert result.items[0].ai["summary"] == TWO
    assert len(client.messages.calls) == 2
    assert "more than 2 sentences" in client.messages.calls[1]["messages"][-1]["content"]


def test_three_sentences_twice_make_the_item_unrated():
    result, _ = run([rijnmond_item()], rijnmond_answer(THREE), rijnmond_answer(THREE), sources=(rijnmond(),))
    assert result.items[0].ai == summarise.unrated()
    assert result.failures == [{"source": summarise.SUMMARISER,
                                "error": f"{ARTICLE_URL}: summary has more than 2 sentences (after a retry)"}]


def test_an_impact_the_ai_sends_anyway_is_never_kept():
    result, _ = run([rijnmond_item()], rijnmond_answer(impact="Invented impact."), sources=(rijnmond(),))
    assert result.items[0].ai["impact"] is None


def test_the_sentence_limit_is_for_the_permission_source_only():
    """Other `use` sources keep the prompt's guidance only; nothing else changes for them (#107)."""
    data = {"summary": THREE, "impact": "Invented impact that could follow.", "severity": "low", "place": "none",
            "tags": [], "strike": None}
    result, _ = run([ect_item()], answer(json.dumps(data)), sources=(rijnmond(),))
    assert result.items[0].ai["summary"] == THREE


# --- the brief records the permission ------------------------------------------------------------


def test_the_brief_item_records_the_permission_it_was_written_under():
    result, _ = run([rijnmond_item()], rijnmond_answer(), sources=(rijnmond(),))
    stored = summarise.brief_item(result.items[0], (rijnmond(),))
    assert stored["permission"] == {"granted": "2026-11-19", "max_sentences": 2, "impact": False}
    assert stored["source"] == "RTV Rijnmond" and stored["url"] == ARTICLE_URL  # credit and link


def test_an_item_without_a_summary_or_from_another_source_records_no_permission():
    headline_rated = rijnmond_item(access="full", article_text=None, snippet=None)
    result, _ = run([headline_rated], answer(json.dumps({"severity": "low", "place": "none", "tags": [],
                                                         "strike": None})), sources=(rijnmond(),))
    assert summarise.brief_item(result.items[0], (rijnmond(),))["permission"] is None
    assert summarise.brief_item(ect_item(), (rijnmond(),))["permission"] is None


# --- the page: the note next to every summary, and no impact block -------------------------------

# The owner's short wording for card and panel (PR #108 review, 19 Nov 2026); How it works keeps
# the full sentence (test_how_it_works_says_haven_daily_is_independent_and_rijnmond_not_responsible).
NOTE = "AI summary, with RTV Rijnmond's permission. Haven Daily is independent; RTV Rijnmond is not responsible for it."


def rijnmond_news(**fields):
    base = dict(source="RTV Rijnmond", language="nl", summary=TWO, impact=None, affects=["Labour"],
                permission={"granted": "2026-11-19", "max_sentences": 2, "impact": False})
    base.update(fields)
    return news("high", "Invented Rijnmond story", **base)


def test_the_note_names_the_publisher():
    assert permission_note({"source": "RTV Rijnmond", "permission": {"impact": False}}) == NOTE


def test_the_card_shows_the_note_and_no_impact_block(tmp_path):
    text = text_of(card_of(tmp_path, rijnmond_news()))
    assert TWO in text and NOTE in text
    assert "Impact for planners" not in text and "Not enough information" not in text
    assert "Affects Labour" in text and "Read original" in text


def test_the_panel_shows_the_note_next_to_the_summary(tmp_path):
    [entry_html] = panel_entries(render_day(tmp_path, make_brief(items=[rijnmond_news()])))
    text = text_of(entry_html)
    assert TWO in text and NOTE in text


def test_an_impact_allowed_by_a_later_permission_is_shown(tmp_path):
    item = rijnmond_news(impact="Invented impact.",
                         permission={"granted": "2026-11-19", "max_sentences": 2, "impact": True})
    text = text_of(card_of(tmp_path, item))
    assert "Impact for planners" in text and "Invented impact." in text
    assert NOTE in text


def test_cards_without_a_permission_have_no_note(tmp_path):
    html = render_day(tmp_path, make_brief(items=[news("high")]))  # older briefs have no such field
    assert "Haven Daily is independent" not in text_of(html[html.index('class="panel-items"'):])


# --- How it works -------------------------------------------------------------------------------


def method_groups(page):
    return dict(re.findall(r'<div class="source-group" id="sources-([\w-]+)">(.*?)</div>', page, re.S))


def test_how_it_works_lists_rijnmond_under_use_with_its_limits():
    page = render_method(sources=load_sources())
    groups = method_groups(page)
    assert "RTV Rijnmond" in groups["use"] and "RTV Rijnmond" not in groups["headline-only"]
    line = text_of(groups["use"][groups["use"].index("RTV Rijnmond"):])
    for words in ("written permission", "lead paragraph", "at most two sentences",
                  "impact for planners is Haven Daily's own interpretation", "written as possible"):
        assert words in line
    assert "no impact for planners" not in line


def test_how_it_works_says_haven_daily_is_independent_and_rijnmond_not_responsible():
    text = text_of(render_method(sources=load_sources()))
    assert "RTV Rijnmond gave Haven Daily written permission on 19 November 2026" in text
    assert "Haven Daily is an independent project; RTV Rijnmond is not responsible for the AI-generated summaries." in text


def test_after_withdrawal_how_it_works_lists_it_as_headline_only_again():
    sources = tuple(rijnmond(permission=None) if s.id == "rtv-rijnmond" else s for s in load_sources())
    page = render_method(sources=sources)
    assert "RTV Rijnmond" in method_groups(page)["headline-only"]
    assert "not responsible for the AI-generated summaries" not in text_of(page)


# --- the impact line, allowed since 23 Nov 2026 (#115) -------------------------------------------
# RTV Rijnmond's conditions (Daan Verberne, 23 Nov 2026; docs/permissions/2026-11-23-rtv-rijnmond.md):
# the line is clearly Haven Daily's own interpretation, not a statement or conclusion from RTV
# Rijnmond; any impact rests on the facts in the article; possible consequences are not presented
# as confirmed facts.

IMPACT_REPLY = "docs/permissions/2026-11-23-rtv-rijnmond.md"


def test_the_reply_of_23_november_records_the_three_conditions():
    text = (ROOT / IMPACT_REPLY).read_text(encoding="utf-8")
    assert "23 November 2026" in text
    for words in ("Haven Daily's own interpretation", "based on the facts in the article",
                  "not presented as confirmed facts"):
        assert words in text


def test_the_request_asks_for_a_hedged_impact_from_the_lead_paragraph_only():
    request = summarise._request(rijnmond_item(), summarise.SUMMARY_MODEL, "invented system prompt", [],
                                 TODAY, READ_AT, permission=WITH_IMPACT)
    assert "impact" in request["output_config"]["format"]["schema"]["properties"]
    content = request["messages"][0]["content"]
    assert "at most 2 sentences" in content
    assert "Haven Daily's own interpretation" in content
    assert "only on the facts in the text above" in content
    assert '"could" or "may"' in content and "never as certain or confirmed" in content


@pytest.mark.parametrize("impact", [
    HEDGED,
    "Barge slots might be tight on Thursday.",
    "Possibly fewer pickups at Waalhaven today.",
    "Trucks may face longer waits. Planners should check their bookings.",  # advice needs no hedge
    "May cause delays at the gate.",
])
def test_impacts_written_as_possible_pass_the_check(impact):
    assert summarise.sounds_confirmed(impact) is None


@pytest.mark.parametrize("impact, word", [
    (CONFIRMED, "will"),
    ("Pickups could slip and won't recover today.", "won't"),
    ("Slots could be tight; carriers are going to reroute.", "going to"),
    ("Delays may follow, and the closure is confirmed.", "confirmed"),
    ("Barges could wait. Delays are certain.", "certain"),
    ("Pickups could definitely slip.", "definitely"),
    ("Pickups WILL slip but may recover.", "will"),
    ("Terminals could close and they'll reroute.", "'ll"),
])
def test_confirmed_sounding_words_fail_the_check(impact, word):
    assert summarise.sounds_confirmed(impact) == f'states a consequence as certain ("{word}")'


@pytest.mark.parametrize("impact", [
    "Container pickups at the terminal are delayed today.",
    "Barges wait until 5 May.",  # a month is not a hedge
    "Expect delays from May 5.",
])
def test_an_impact_with_no_could_may_or_might_fails_the_check(impact):
    assert summarise.sounds_confirmed(impact) == 'states consequences as certain (no "could", "may" or "might")'


def test_a_hedged_impact_is_kept():
    result, client = run([rijnmond_item()], rijnmond_answer(impact=HEDGED), sources=(rijnmond(WITH_IMPACT),))
    assert result.items[0].ai["impact"] == HEDGED
    assert result.failures == [] and len(client.messages.calls) == 1


def test_a_confirmed_sounding_impact_gets_one_retry_then_the_hedged_answer_is_used():
    result, client = run([rijnmond_item()], rijnmond_answer(impact=CONFIRMED), rijnmond_answer(impact=HEDGED),
                         sources=(rijnmond(WITH_IMPACT),))
    assert result.items[0].ai["impact"] == HEDGED and result.failures == []
    retry = client.messages.calls[1]["messages"][-1]["content"]
    assert 'impact states a consequence as certain ("will")' in retry
    assert 'write each consequence as possible, with "could" or "may"' in retry


def test_confirmed_twice_leaves_out_the_impact_line_and_keeps_the_rest():
    result, client = run([rijnmond_item()], rijnmond_answer(impact=CONFIRMED), rijnmond_answer(impact=CONFIRMED),
                         sources=(rijnmond(WITH_IMPACT),))
    [done] = result.items
    assert len(client.messages.calls) == 2  # one retry, no more
    assert done.ai["summary"] == TWO and done.ai["severity"] == "high"  # still rated
    assert done.ai["impact"] is None and done.ai["impact_left_out"] is True
    assert result.failures == [{"source": summarise.SUMMARISER, "error": f"{ARTICLE_URL}: impact left out: "
                                'impact states a consequence as certain ("will") (after a retry)'}]
    stored = summarise.brief_item(done, (rijnmond(WITH_IMPACT),))
    assert stored["impact"] is None
    assert stored["permission"] == {"granted": "2026-11-19", "max_sentences": 2, "impact": True,
                                    "impact_left_out": True}


def test_the_one_retry_is_shared_with_the_other_checks():
    """A retry already spent on a three-sentence summary leaves no second one for the impact."""
    result, client = run([rijnmond_item()], rijnmond_answer(THREE, impact=HEDGED),
                         rijnmond_answer(impact=CONFIRMED), sources=(rijnmond(WITH_IMPACT),))
    assert len(client.messages.calls) == 2
    assert result.items[0].ai["summary"] == TWO and result.items[0].ai["impact"] is None


def test_not_enough_information_stays_possible():
    result, _ = run([rijnmond_item()], rijnmond_answer(impact=None), sources=(rijnmond(WITH_IMPACT),))
    assert result.items[0].ai["impact"] is None and "impact_left_out" not in result.items[0].ai
    assert summarise.brief_item(result.items[0], (rijnmond(WITH_IMPACT),))["permission"] == {
        "granted": "2026-11-19", "max_sentences": 2, "impact": True}


def test_the_wording_check_applies_to_other_sources_too():
    """Since #123 (owner, 24 Nov 2026): every source's impact is checked, not only Rijnmond's."""
    data = {"summary": "Invented summary.", "impact": CONFIRMED, "severity": "low", "place": "none",
            "tags": [], "strike": None}
    hedged = dict(data, impact=HEDGED)
    result, client = run([ect_item()], answer(json.dumps(data)), answer(json.dumps(hedged)),
                         sources=(rijnmond(WITH_IMPACT),))
    assert result.items[0].ai["impact"] == HEDGED and len(client.messages.calls) == 2


def test_the_batch_route_gets_the_same_retry_and_leaves_the_impact_out():
    """A batch answer that sounds confirmed is retried once through the standard API, like a long one."""
    from tests.test_summarise_batch import BatchClient, Clock, FakeBatches, succeeded

    clock = Clock()
    batches = FakeBatches(clock, results={0: succeeded(rijnmond_answer(impact=CONFIRMED))})
    client = BatchClient(batches, rijnmond_answer(impact=CONFIRMED))
    result = summarise.summarise_batch([rijnmond_item()], client, known=[], today=TODAY, read_at=READ_AT,
                                       clock=clock, sleep=clock.sleep, sources=(rijnmond(WITH_IMPACT),))
    [done] = result.items
    assert len(client.messages.calls) == 1  # the one retry, through the standard API
    assert done.ai["summary"] == TWO and done.ai["impact"] is None and done.ai["impact_left_out"] is True


# The page: the label says whose interpretation it is.
LABEL = "Impact for planners Haven Daily's interpretation, not RTV Rijnmond's"


def rijnmond_news_with_impact(**fields):
    fields.setdefault("impact", HEDGED)
    return rijnmond_news(permission={"granted": "2026-11-19", "max_sentences": 2, "impact": True}, **fields)


def test_the_card_labels_the_impact_as_haven_dailys_interpretation(tmp_path):
    text = text_of(card_of(tmp_path, rijnmond_news_with_impact()))
    assert LABEL in text and HEDGED in text and NOTE in text


def test_other_cards_keep_the_plain_interpretation_label(tmp_path):
    text = text_of(card_of(tmp_path, news("high", impact="Invented impact.")))
    assert "Impact for planners interpretation" in text and "Haven Daily's interpretation" not in text


def test_an_impact_left_out_shows_no_impact_block(tmp_path):
    item = rijnmond_news(impact=None, permission={"granted": "2026-11-19", "max_sentences": 2, "impact": True,
                                                  "impact_left_out": True})
    text = text_of(card_of(tmp_path, item))
    assert "Impact for planners" not in text and "Not enough information" not in text
    assert TWO in text and "Affects Labour" in text


def test_not_enough_information_is_also_labelled_as_haven_dailys(tmp_path):
    text = text_of(card_of(tmp_path, rijnmond_news_with_impact(impact=None)))
    assert LABEL in text and "Not enough information" in text


def test_how_it_works_says_the_impact_is_haven_dailys_not_rijnmonds():
    text = text_of(render_method(sources=load_sources()))
    assert "The impact for planners on its items is Haven Daily's own interpretation, not RTV Rijnmond's." in text


def test_the_spec_records_the_impact_permission():
    spec = (ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")
    section_11 = spec[spec.index("## 11. Open items"):spec.index("## 12. Credits")]
    assert IMPACT_REPLY in section_11
    assert "Open: the impact line for Rijnmond items" not in section_11
