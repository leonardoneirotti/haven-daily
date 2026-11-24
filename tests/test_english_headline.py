"""English headlines for Dutch items (issue #134, part 1; spec §2.1, §4, §5.5, §6, §7.5).

For an item with a Dutch headline from a source whose `english_headline` setting is on, the
summariser writes an English headline in the same call (no extra call). The page shows it as
the main headline; the Dutch original goes below it, smaller, labelled "translated by AI".
On for PIN notices and Port Authority news; off for RTV Rijnmond (until the publisher agrees)
and for every headline-only source (owner, 24 Nov 2026).

Headlines are invented; the fake client never calls the API.
"""

import json
from pathlib import Path

import pytest

from haven import render, summarise
from haven.config import ConfigError, Permission, Source, load_sources
from test_render_real import make_brief, news, news_card, render_day, text_of
from test_summarise import GOOD, FakeClient, READ_AT, TODAY, answer, item, run, user_text
from test_cards_panel import panel_entries
from test_summarise_batch import run_batch, succeeded

ROOT = Path(__file__).resolve().parent.parent

DUTCH = "Invented: Botlekbrug weer in bedrijf na storing"
ENGLISH = "Invented: Botlek bridge back in service after a fault"

PIN = Source(id="pin-notices", name="PIN notices to shipping", verdict="use", urls=("https://pin.test/",),
             access="rss", language="en", english_headline=True)
RIJNMOND = Source(id="rtv-rijnmond", name="RTV Rijnmond", verdict="headline-only", urls=("https://rijnmond.test/",),
                  access="rss", language="nl",
                  permission=Permission(file="docs/permissions/x.md", granted=TODAY, max_sentences=2, impact=True))
NLT = Source(id="nl-times", name="NL Times", verdict="headline-only", urls=("https://nlt.test/",),
             access="html", language="en")
SOURCES = (PIN, RIJNMOND, NLT)


def dutch(source="pin-notices", **kw):
    return item(source=source, headline=DUTCH, language="nl", **kw)


def good(**changes):
    data = json.loads(json.dumps(GOOD))
    data.update(changes)
    return answer(json.dumps(data))


def summarise_one(it, *answers):
    return run([it], *answers, sources=SOURCES)


def schema_keys(call):
    return call["output_config"]["format"]["schema"]["properties"].keys()


# --- the setting in config/sources.toml ------------------------------------------------------


def test_the_real_setting_is_on_for_pin_and_port_authority_and_off_for_everything_else():
    on = {s.id for s in load_sources() if s.english_headline}
    assert on == {"pin-notices", "port-authority-news"}  # RTV Rijnmond off until the publisher agrees


def toml(tmp_path, body):
    path = tmp_path / "sources.toml"
    path.write_text(body, encoding="utf-8")
    return path


SOURCE = """
[[source]]
id = "{id}"
name = "Invented"
verdict = "{verdict}"
urls = ["https://invented.test/"]
access = "rss"
language = "nl"
english_headline = {value}
"""


def test_a_headline_only_source_cannot_have_english_headlines(tmp_path):
    path = toml(tmp_path, SOURCE.format(id="x", verdict="headline-only", value="true"))
    with pytest.raises(ConfigError, match="english_headline"):
        load_sources(path)


def test_a_headline_only_source_with_written_permission_may_have_them(tmp_path):
    body = SOURCE.format(id="x", verdict="headline-only", value="true") + (
        'permission = { file = "docs/permissions/x.md", granted = 2026-11-19, max_sentences = 2, impact = true }\n')
    [source] = load_sources(toml(tmp_path, body))
    assert source.english_headline is True


def test_the_setting_must_be_true_or_false(tmp_path):
    with pytest.raises(ConfigError, match="english_headline"):
        load_sources(toml(tmp_path, SOURCE.format(id="x", verdict="use", value='"yes"')))


def test_the_setting_is_off_when_left_out(tmp_path):
    body = SOURCE.format(id="x", verdict="use", value="false").replace("english_headline = false\n", "")
    [source] = load_sources(toml(tmp_path, body))
    assert source.english_headline is False


# --- the summariser: asked only when the setting is on and the item is Dutch -------------------


def test_a_dutch_item_from_a_source_with_the_setting_on_is_asked_for_an_english_headline():
    result, client = summarise_one(dutch(), good(headline_en=ENGLISH))
    [call] = client.messages.calls  # the same call: no extra one
    assert "headline_en" in schema_keys(call)
    assert "headline_en" in call["output_config"]["format"]["schema"]["required"]
    assert "English headline" in user_text(call)
    assert result.items[0].ai["headline_en"] == ENGLISH


@pytest.mark.parametrize("it", [
    item(source="pin-notices", language="en"),           # already English
    dutch(source="rtv-rijnmond"),                        # setting off (Rijnmond, until the publisher agrees)
    dutch(access="headline-only", text=None),            # a headline-only item: never (hard rule 12)
    dutch(text=None),                                    # article not read: rated from the headline only
])
def test_no_english_headline_is_asked_for_otherwise(it):
    result, client = summarise_one(it, good() if it.article_text else answer(json.dumps(
        {"severity": "low", "place": "none", "tags": [], "strike": None})))
    [call] = client.messages.calls
    assert "headline_en" not in schema_keys(call)
    assert "English headline" not in user_text(call)
    assert "headline_en" not in result.items[0].ai


def test_the_english_headline_is_tidied():
    result, _ = summarise_one(dutch(), good(headline_en=f"  {ENGLISH}\n "))
    assert result.items[0].ai["headline_en"] == ENGLISH


@pytest.mark.parametrize("bad", ["", "   ", None, 42, "x" * (summarise.HEADLINE_EN_MAX + 1)])
def test_a_bad_english_headline_is_left_out_and_the_item_stays_rated(bad):
    result, client = summarise_one(dutch(), good(headline_en=bad))
    [done] = result.items
    assert len(client.messages.calls) == 1   # no retry for a headline
    assert done.ai["severity"] == "high"     # the rest of the item stays
    assert "headline_en" not in done.ai
    assert any("English headline left out" in f["error"] for f in result.failures)


def test_brief_item_carries_the_english_headline_only_when_there_is_one():
    result, _ = summarise_one(dutch(), good(headline_en=ENGLISH))
    assert summarise.brief_item(result.items[0], SOURCES)["headline_en"] == ENGLISH
    plain, _ = summarise_one(item(source="pin-notices"), good())
    assert "headline_en" not in summarise.brief_item(plain.items[0], SOURCES)


def test_the_batch_asks_for_it_too_and_keeps_it():
    # The real config: PIN notices have the setting on.
    result, _, batches, _ = run_batch([dutch()], results={0: succeeded(good(headline_en=ENGLISH))})
    [requests] = batches.created
    assert "headline_en" in schema_keys(requests[0]["params"])
    assert result.items[0].ai["headline_en"] == ENGLISH
    assert result.items[0].ai["written_by"]["api"] == "batch"


# --- the page ---------------------------------------------------------------------------------


def translated(**fields):
    return news("low", DUTCH, source="PIN notices to shipping", language="nl", headline_en=ENGLISH, **fields)


def test_the_card_shows_the_english_headline_and_the_dutch_original_below_it(tmp_path):
    card = news_card(render_day(tmp_path, make_brief(items=[translated()])), 1)
    title = card[card.index('class="item-title"'): card.index("</h3>")]
    assert ENGLISH in title and DUTCH not in title          # the English one is the main headline
    assert 'href="https://news.test/' in title              # still the link to the original
    below = card[card.index("</h3>"):]
    assert 'class="item-original"' in below
    assert f'<span lang="nl">{DUTCH}</span>' in below     # the original, marked as Dutch
    assert "translated by AI" in text_of(below)


def test_a_card_without_an_english_headline_is_unchanged(tmp_path):
    card = news_card(render_day(tmp_path, make_brief(items=[news("low", DUTCH, language="nl")])), 1)
    assert "translated by AI" not in card
    assert "item-original" not in card
    assert DUTCH in card[card.index('class="item-title"'): card.index("</h3>")]


def test_the_panel_shows_the_english_headline_and_says_it_was_translated(tmp_path):
    html = render_day(tmp_path, make_brief(items=[translated()]))
    [entry] = panel_entries(html)
    title = entry[entry.index('class="panel-title"'):]
    assert title.split("</span>")[0].endswith(ENGLISH)
    assert "translated by AI" in text_of(entry)


def test_the_map_names_the_item_by_its_english_headline():
    brief = make_brief(items=[translated(map={"lat": 51.87, "lon": 4.33, "label": "Botlekbrug", "side": "right"})])
    render.prepare_briefs([brief])
    [callout] = render.map_payload(brief)["callouts"]
    assert callout["title"] == ENGLISH


def test_an_english_headline_is_escaped(tmp_path):
    card = news_card(render_day(tmp_path, make_brief(items=[translated(headline_en="<b>Invented</b>")])), 1)
    assert "<b>Invented</b>" not in card and "&lt;b&gt;Invented&lt;/b&gt;" in card


def test_how_it_works_says_dutch_headlines_are_translated_by_ai():
    about = (ROOT / "templates" / "about.html").read_text(encoding="utf-8")
    assert "translated by AI" in about
