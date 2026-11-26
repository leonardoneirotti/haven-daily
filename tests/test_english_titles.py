"""No Dutch titles anywhere on the site (issue #153, owner 26 Nov 2026; replaces #134's English headlines).

Every item's title on the site is in English: on the chart, the panel, the cards, the pin card, the
archive, the day pages, the link previews and the sample site.

- A Dutch item that is summarised (today: RTV Rijnmond, by its written permission) gets a short
  English title **written by Haven Daily from its own summary** (part of the summary, not a
  translation of the publisher's headline), in the same summary call: no extra call. The
  "original (Dutch)" line is gone; the card credits the source instead ("Source: RTV Rijnmond
  (in Dutch)") and keeps the link to the original article.
- A Dutch item without an English title (a headline-only Dutch source, or a Dutch item whose
  summary or title failed) is not shown. A Dutch headline-only source is not read at all until it
  gives permission for summaries.

Headlines are invented; the fake client never calls the API.
"""

import json
from pathlib import Path

import pytest

from haven import render, summarise
from haven.config import ConfigError, Permission, Source, load_sources
from test_render_real import make_brief, news, news_card, render_day, render_days, text_of
from test_summarise import GOOD, TODAY, answer, item, run, user_text
from test_cards_panel import panel_entries
from test_summarise_batch import run_batch, succeeded

ROOT = Path(__file__).resolve().parent.parent

DUTCH = "Invented: Botlekbrug weer in bedrijf na storing"
ENGLISH = "Invented: Botlek bridge back in service after a fault"

PIN = Source(id="pin-notices", name="PIN notices to shipping", verdict="use", urls=("https://pin.test/",),
             access="rss", language="en")
RIJNMOND = Source(id="rtv-rijnmond", name="RTV Rijnmond", verdict="headline-only", urls=("https://rijnmond.test/",),
                  access="rss", language="nl",
                  permission=Permission(file="docs/permissions/x.md", granted=TODAY, max_sentences=2, impact=True))
NLT = Source(id="nl-times", name="NL Times", verdict="headline-only", urls=("https://nlt.test/",),
             access="html", language="en")
NT = Source(id="nieuwsblad-transport", name="Nieuwsblad Transport", verdict="headline-only",
            urls=("https://nt.test/",), access="rss", language="nl")
SOURCES = (PIN, RIJNMOND, NLT)


def dutch(source="rtv-rijnmond", **kw):
    return item(source=source, headline=DUTCH, language="nl", **kw)


def good(**changes):
    data = json.loads(json.dumps(GOOD))
    data.update(changes)
    return answer(json.dumps(data))


def summarise_one(it, *answers):
    return run([it], *answers, sources=SOURCES)


def schema(call):
    return call["output_config"]["format"]["schema"]


# --- the summariser: every summarised Dutch item, in the same call ---------------------------------


def test_a_summarised_dutch_item_gets_an_english_title_in_the_same_call():
    result, client = summarise_one(dutch(), good(headline_en=ENGLISH))
    [call] = client.messages.calls                       # no extra call
    assert "headline_en" in schema(call)["required"]
    assert result.items[0].ai["headline_en"] == ENGLISH


def test_any_summarised_dutch_source_gets_one_with_no_setting():
    # #134 had a per-source setting, off for RTV Rijnmond; since #153 (owner, 26 Nov 2026) the title is
    # part of Haven Daily's own summary, so every summarised Dutch item gets one.
    _, client = summarise_one(dutch(source="pin-notices"), good(headline_en=ENGLISH))
    assert "headline_en" in schema(client.messages.calls[0])["properties"]


def test_the_title_is_written_after_and_from_the_summary_not_translated_from_the_headline():
    _, client = summarise_one(dutch(), good(headline_en=ENGLISH))
    [call] = client.messages.calls
    keys = list(schema(call)["properties"])
    assert keys.index("summary") < keys.index("headline_en")  # the summary comes first in the answer
    text = user_text(call)
    assert "from your summary" in text
    assert "not a translation" in text


@pytest.mark.parametrize("it", [
    item(source="pin-notices", language="en"),           # already English
    dutch(access="headline-only", text=None),            # a headline-only item: no summary to write it from
    dutch(text=None),                                    # article not read: rated from the headline only
])
def test_no_title_is_asked_for_otherwise(it):
    result, client = summarise_one(it, good() if it.article_text else answer(json.dumps(
        {"severity": "low", "place": "none", "tags": [], "strike": None})))
    [call] = client.messages.calls
    assert "headline_en" not in schema(call)["properties"]
    assert "headline_en" not in result.items[0].ai


def test_the_title_is_tidied():
    result, _ = summarise_one(dutch(), good(headline_en=f"  {ENGLISH}\n "))
    assert result.items[0].ai["headline_en"] == ENGLISH


@pytest.mark.parametrize("bad", ["", "   ", None, 42, "x" * (summarise.HEADLINE_EN_MAX + 1)])
def test_a_bad_title_is_left_out_with_a_failure_line_and_no_retry(bad):
    result, client = summarise_one(dutch(), good(headline_en=bad))
    [done] = result.items
    assert len(client.messages.calls) == 1
    assert "headline_en" not in done.ai
    assert any("English title left out" in f["error"] for f in result.failures)


def test_brief_item_carries_the_title_only_when_there_is_one():
    result, _ = summarise_one(dutch(), good(headline_en=ENGLISH))
    assert summarise.brief_item(result.items[0], SOURCES)["headline_en"] == ENGLISH
    plain, _ = summarise_one(item(source="pin-notices"), good())
    assert "headline_en" not in summarise.brief_item(plain.items[0], SOURCES)


def test_the_batch_asks_for_it_too_and_keeps_it():
    result, _, batches, _ = run_batch([dutch()], results={0: succeeded(good(headline_en=ENGLISH))})
    [requests] = batches.created
    assert "headline_en" in schema(requests[0]["params"])["properties"]
    assert result.items[0].ai["headline_en"] == ENGLISH


# --- the setting is gone: every Dutch item needs one ---------------------------------------------


def test_the_english_headline_setting_is_gone():
    assert "english_headline" not in (ROOT / "config" / "sources.toml").read_text(encoding="utf-8")
    assert not hasattr(load_sources()[0], "english_headline")


def test_an_old_english_headline_line_is_refused(tmp_path):
    path = tmp_path / "sources.toml"
    path.write_text('[[source]]\nid = "x"\nname = "X"\nverdict = "use"\nurls = ["https://x.test/"]\n'
                    'access = "rss"\nlanguage = "nl"\nenglish_headline = true\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="english_headline"):
        load_sources(path)


# --- Dutch headline-only sources: not read, not shown ------------------------------------------


def test_a_dutch_headline_only_source_is_not_read():
    assert NT.fetched is False
    assert NT.dutch_without_permission is True
    assert RIJNMOND.fetched is True and RIJNMOND.dutch_without_permission is False  # permission
    assert NLT.fetched is True and NLT.dutch_without_permission is False            # English


def test_how_it_works_says_why_it_is_not_shown():
    line = render.source_use(NT)
    assert "Dutch" in line and "permission" in line and "not shown" in line


def test_no_dutch_headline_only_source_is_read_today():
    assert [s.id for s in load_sources() if s.fetched and s.language != "en" and s.effective_verdict != "use"] == []


# --- the page -----------------------------------------------------------------------------------


def rijnmond(severity="low", **fields):
    fields.setdefault("headline_en", ENGLISH)
    return news(severity, DUTCH, source="RTV Rijnmond", language="nl", **fields)


def test_the_card_shows_the_english_title_and_credits_the_source(tmp_path):
    card = news_card(render_day(tmp_path, make_brief(items=[rijnmond()])), 1)
    title = card[card.index('class="item-title"'): card.index("</h3>")]
    assert ENGLISH in title and 'href="https://news.test/' in title   # still the link to the original
    assert DUTCH not in card                                           # no "original (Dutch)" line
    assert "item-original" not in card and "translated by AI" not in card
    assert "Source: RTV Rijnmond (in Dutch)" in text_of(card)


def test_an_english_card_has_no_credit_line(tmp_path):
    card = news_card(render_day(tmp_path, make_brief(items=[news("low", "Invented English")])), 1)
    assert "item-credit" not in card


def test_the_panel_shows_only_the_english_title(tmp_path):
    [entry] = panel_entries(render_day(tmp_path, make_brief(items=[rijnmond()])))
    assert ENGLISH in entry and DUTCH not in entry and "translated" not in entry


def test_the_pin_card_data_has_the_title_and_credit_and_no_original():
    brief = make_brief(items=[rijnmond(map={"lat": 51.87, "lon": 4.33, "label": "Botlekbrug", "side": "right"})])
    render.prepare_briefs([brief])
    [callout] = render.map_payload(brief)["callouts"]
    assert callout["title"] == ENGLISH
    assert callout["credit"] == "Source: RTV Rijnmond (in Dutch)"
    assert "original" not in callout and DUTCH not in json.dumps(callout)


def test_a_dutch_item_without_an_english_title_is_not_shown(tmp_path):
    html = render_day(tmp_path, make_brief(items=[
        news("high", DUTCH, source="Nieuwsblad Transport", language="nl", access="headline-only", summary=None,
             impact=None),
        news("low", "Invented English item"),
    ]))
    assert DUTCH not in html
    assert "Invented English item" in news_card(html, 1)               # it moves up to number 1


def test_the_archive_and_the_link_preview_use_the_english_title(tmp_path):
    brief = make_brief(items=[rijnmond("high")])
    render_days(tmp_path, brief)
    archive = (tmp_path / "site" / "archive.html").read_text(encoding="utf-8")
    day = (tmp_path / "site" / "days" / f"{brief['date']}.html").read_text(encoding="utf-8")
    assert ENGLISH in archive and DUTCH not in archive
    assert DUTCH not in day                                            # preview tags included
    assert f'content="{ENGLISH}' in day


def test_a_strike_line_never_shows_a_dutch_headline():
    link = {"headline": DUTCH, "headline_en": ENGLISH, "language": "nl", "url": "https://x.test/",
            "source": "RTV Rijnmond"}
    assert render.strike_link(link, None, "2026-11-26")["headline"] == ENGLISH
    shown = render.strike_link(dict(link, headline_en=None), None, "2026-11-26")["headline"]
    assert shown != DUTCH and "RTV Rijnmond" in shown and "Dutch" in shown
    english = dict(link, headline="Invented English", headline_en=None, language="en")
    assert render.strike_link(english, None, "2026-11-26")["headline"] == "Invented English"


def test_the_strike_record_keeps_the_title_and_language():
    from haven import strike
    source = Path(strike.__file__).read_text(encoding="utf-8")
    shown = source[source.index("def _shown("):]
    shown = shown[: shown.index("\n\n\n")]
    assert '"headline_en": record.get("headline_en")' in shown and '"language": record.get("language")' in shown


# --- the real and sample data, and How it works ---------------------------------------------------


@pytest.mark.parametrize("folder", ["data/sample/briefs", "data/briefs"])
def test_every_rated_dutch_item_has_an_english_title(folder):
    for path in sorted((ROOT / folder).glob("*.json")):
        brief = json.loads(path.read_text(encoding="utf-8"))
        for it in brief.get("items", []):
            if it.get("language", "en") != "en" and it.get("summary"):
                assert it.get("headline_en"), (path.name, it["headline"][:40])


def test_how_it_works_says_titles_are_written_in_english_from_the_summary():
    about = text_of((ROOT / "templates" / "about.html").read_text(encoding="utf-8"))
    assert "English title" in about and "translated by AI" not in about
