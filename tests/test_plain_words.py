"""Plain words on the public pages and an archive legend (issue #84; design review S8, S9;
spec §7.5 "Plain words", §7.8).

- S8: internal terms ("No AIS", "Summaries in the batch / by the fallback", "Derived from kept
  items", "Kept items of the last 14 days", the PIN gap-check line, code names) never show in a
  rendered page's visible text. Failure lines are still shown (hard rule 9): only the words
  change, in the code that writes them.
- S9: the archive has one legend line above the list, and its status icons get short text
  labels on phones (a mouse-over `title` alone is not enough).

Headlines are invented.
"""

import html as html_lib
import re
from pathlib import Path

import pytest

import test_run
from haven import collect, feeds, filter as haven_filter, pages, render, strike, summarise
from test_first_screen import css_rules
from test_render_real import kaub, make_brief, news, render_days, section, strike as strike_reading, text_of, weather

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")

# Words for parts of the pipeline that a visitor can't know (design review P12). None may
# appear in what a page shows. The Method page explains the pipeline, so it may name the
# Batch API; on it only the terms in METHOD_INTERNAL are checked.
INTERNAL = (
    "No AIS", "fallback", "standard API", "Derived from kept items", "Kept items", "kept items",
    "gap check", "rolled over", "ANTHROPIC_API_KEY", ".py", "affects_rotterdam", "is not an object",
    "are not a list", "Summaries in the batch",
)
METHOD_INTERNAL = ("No AIS", "Kept items of the last 14 days", "Derived from kept items", "gap check")

GAP_LINE = ("couldn't check whether any notices were missed since the last run: "
            "there is no earlier run in the last 14 days")


def visible_text(page: str) -> str:
    """What a reader sees: no scripts, styles, tags or attributes (so `title` and the map
    data are left out; screen-reader text is kept, it is read out)."""
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return html_lib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))).strip()


def internal_words(text: str, words=INTERNAL) -> list[str]:
    return [word for word in words if word in text]


def site_pages(site: Path) -> dict[str, str]:
    return {str(path.relative_to(site)): path.read_text(encoding="utf-8") for path in site.rglob("*.html")}


def check_site(site: Path) -> None:
    for name, page in site_pages(site).items():
        words = METHOD_INTERNAL if name == "about.html" else INTERNAL
        assert internal_words(visible_text(page), words) == [], name


# --- no internal term on any page --------------------------------------------------------


def test_the_sample_site_shows_no_internal_terms(tmp_path):
    render.render_site(ROOT / "data" / "sample" / "briefs", tmp_path / "site")
    check_site(tmp_path / "site")


def test_a_site_from_runner_briefs_shows_no_internal_terms(tmp_path):
    """A normal brief written by the runner (every step faked); the reduced one is next."""
    data = tmp_path / "data"
    outcome, _ = test_run.go(data)
    assert outcome.exit_code == 0
    render.render_site(data / "briefs", tmp_path / "site")
    check_site(tmp_path / "site")


def test_a_reduced_runner_brief_shows_no_internal_terms(tmp_path):
    data = tmp_path / "data"
    outcome, _ = test_run.go(data, test_run.Fake(filter_down=True), last_trigger=True)
    assert outcome.exit_code == 0
    render.render_site(data / "briefs", tmp_path / "site")
    check_site(tmp_path / "site")


# Every failure line the pipeline writes as a fixed text: the words a reader sees under
# "How this brief was made". (Lines built around an error kind, "HTTP 503" or "timeout", keep
# that kind: it is the failure itself.)
FAILURE_TEXTS = {
    "collect.GAP_CHECK_SKIPPED": collect.GAP_CHECK_SKIPPED,
    "collect.NO_READER": collect.NO_READER,
    "collect.NO_ARTICLE_TEXT": collect.NO_ARTICLE_TEXT,
    "collect.KN_QUIET": collect.KN_QUIET,
    "feeds.GAP_MESSAGE": feeds.GAP_MESSAGE,
    "pages.NO_PARSER": pages.NO_PARSER,
    "pages.NO_ITEMS": pages.NO_ITEMS,
    "pages.NO_PARAGRAPH": pages.NO_PARAGRAPH,
    "filter.NO_KEY": haven_filter.NO_KEY,
    "summarise.BATCH_NOT_CREATED": summarise.BATCH_NOT_CREATED.format(problem="HTTP 500"),
    "summarise.BATCH_NOT_ENDED": summarise.BATCH_NOT_ENDED,
    "summarise.BATCH_UNREADABLE": summarise.BATCH_UNREADABLE.format(problem="HTTP 500"),
    "strike.UNREADABLE_DETAILS": strike.UNREADABLE_DETAILS,
    "strike.NO_AI_NOTE": strike.NO_AI_NOTE,
}


@pytest.mark.parametrize("name", sorted(FAILURE_TEXTS))
def test_no_failure_text_uses_internal_terms(name):
    assert internal_words(FAILURE_TEXTS[name]) == []
    assert "\n" not in FAILURE_TEXTS[name]


# The summariser's check lines that named data types or fields ("tags are not a list",
# "strike affects_rotterdam is not true/false", ...) are tested with the new words in
# tests/test_summarise.py, where every check line is.


# --- the PIN gap-check line: still recorded and shown, in plain words ----------------------


def test_the_gap_check_line_is_plain_english():
    assert collect.GAP_CHECK_SKIPPED == GAP_LINE


def test_the_skipped_gap_check_is_still_recorded_and_shown(tmp_path):
    """Hard rule 9: the failure stays (tests/test_collect.py checks the collect step records it);
    here it goes through the runner into the brief and onto the page."""
    data = tmp_path / "data"
    fake = test_run.Fake(collect_failures=[{"source": "PIN notices to shipping", "error": collect.GAP_CHECK_SKIPPED}])
    outcome, _ = test_run.go(data, fake)
    assert outcome.exit_code == 0
    render.render_site(data / "briefs", tmp_path / "site")
    page = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    notes = visible_text(section(page, "build-title"))
    assert f"PIN notices to shipping: {GAP_LINE}" in notes


# --- strike dial: "From the news of the last 14 days" -------------------------------------


def test_the_strike_reading_says_where_it_comes_from_in_plain_words():
    flag = strike.flag_from_items([], test_run.TODAY, (), ai_unavailable=False)
    reading = strike.reading(flag, test_run.START)
    assert reading["place"] == "From the news of the last 14 days"
    assert reading["source_name"] == "Haven Daily's news sources"


def test_the_method_page_strike_row_has_no_internal_term(tmp_path):
    render.render_site(ROOT / "data" / "sample" / "briefs", tmp_path / "site")
    about = (tmp_path / "site" / "about.html").read_text(encoding="utf-8")
    row = about[about.index('id="threshold-strike"') : about.index("</tr>", about.index('id="threshold-strike"'))]
    assert "The news of the last 14 days" in visible_text(row)


# --- summaries: model names, not "batch" and "fallback" -----------------------------------


def written(model, api="batch"):
    return {"model": model, "api": api}


def test_summaries_line_names_the_models():
    items = [news("medium", f"Item {n}", written_by=written("claude-sonnet-5-5")) for n in range(10)]
    line = render.summaries_line(items, {"batch": 10, "fallback": 0})
    assert line == "10 by Claude Sonnet 5.5, 0 by the backup model"


def test_summaries_line_names_the_backup_model_when_it_wrote_some():
    items = [news("medium", "A", written_by=written("claude-sonnet-5-5")),
             news("low", "B", written_by=written("claude-haiku-5-5", "standard")),
             news("low", "C", written_by=written("claude-haiku-5-5", "standard"))]
    line = render.summaries_line(items, {"batch": 1, "fallback": 2})
    assert line == "1 by Claude Sonnet 5.5, 2 by the backup model (Claude Haiku 5.5)"


def test_a_rephrase_retry_by_the_main_model_counts_for_that_model():
    """A copied answer is rephrased by the same model through the standard API (§5.5 point 4): its
    count says "fallback", but the words are the main model's, so the line credits that model."""
    items = [news("medium", "A", written_by=written("claude-sonnet-5-5")),
             news("medium", "B", written_by=written("claude-sonnet-5-5", "standard"))]
    assert render.summaries_line(items, {"batch": 1, "fallback": 1}) == "2 by Claude Sonnet 5.5, 0 by the backup model"


def test_unrated_items_are_not_counted():
    items = [news("medium", "A", written_by=written("claude-sonnet-5-5")), news(None, "B")]
    assert render.summaries_line(items, {"batch": 1, "fallback": 0}) == "1 by Claude Sonnet 5.5, 0 by the backup model"


def test_no_summaries_line_without_the_field():
    assert render.summaries_line([news("medium", "A")], None) is None


def test_a_day_with_nothing_summarised_says_none():
    assert render.summaries_line([], {"batch": 0, "fallback": 0}) == "None"


def test_a_model_without_a_page_name_shows_its_id_rather_than_stopping_the_build():
    items = [news("medium", "A", written_by=written("claude-invented-9"))]
    assert render.summaries_line(items, {"batch": 1, "fallback": 0}) == "1 by claude-invented-9, 0 by the backup model"


def test_summaries_count_every_kept_item_not_only_the_five_shown(tmp_path):
    items = [news("low", f"Item {n}", written_by=written("claude-sonnet-5-5")) for n in range(7)]
    build = {"sources_checked": 9, "items_collected": 41, "items_kept": 7, "failures": [],
             "summaries": {"batch": 7, "fallback": 0}}
    page = render_days(tmp_path, make_brief(items=items, build=build))[make_brief()["date"]]
    notes = visible_text(section(page, "build-title"))
    assert "Summaries 7 by Claude Sonnet 5.5, 0 by the backup model" in notes


# --- the archive: no "No AIS", a legend, labelled icons -----------------------------------


def archive(tmp_path, *briefs):
    render_days(tmp_path, *briefs)
    return (tmp_path / "site" / "archive.html").read_text(encoding="utf-8")


def status_three():
    return [weather(), kaub(120, level="amber"), strike_reading("No active strike", "green")]


def test_v1_archive_rows_say_nothing_about_ships(tmp_path):
    page = archive(tmp_path, make_brief(status=status_three()))
    assert "day-ships" not in page
    assert "No ship data" not in visible_text(page)


def test_v2_archive_row_without_ships_says_no_ship_data(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "AIS_SNAPSHOT_BUILT", True)
    page = archive(tmp_path, make_brief(status=status_three()))
    assert "No ship data" in visible_text(page)
    assert "No AIS" not in visible_text(page)


def legend_of(page):
    start = page.index('class="archive-legend"')
    return page[start : page.index("</p>", start)]


def test_the_archive_has_a_legend_line_above_the_list(tmp_path):
    page = archive(tmp_path, make_brief(status=status_three()))
    assert page.index('class="archive-legend"') < page.index('class="days"')
    text = visible_text(legend_of(page))
    assert "Squares: the day's items by severity" in text
    assert "Icons: weather, Rhine, strike" in text
    for word in ("Normal", "Watch", "Alert", "No data"):  # what each icon shape means
        assert word in text


def test_archive_status_icons_have_short_text_labels(tmp_path):
    page = archive(tmp_path, make_brief(status=status_three()))
    marks = page[page.index('class="status-marks"') : page.index("</span>\n</span>", page.index('class="status-marks"'))]
    labels = re.findall(r'<span class="mark-label" aria-hidden="true">([^<]+)</span>', marks)
    assert labels == ["Weather", "Rhine", "Strike"]
    # screen readers still hear the full label and level once
    assert "Weather warnings: Watch." in visible_text(marks)


def test_short_labels_come_from_one_constant():
    assert render.STATUS_SHORT_LABELS == {"weather": "Weather", "rhine": "Rhine", "strike": "Strike"}


def test_an_unknown_indicator_falls_back_to_its_own_label(tmp_path):
    other = dict(weather(), key="tide", label="Tide")
    page = archive(tmp_path, make_brief(status=[other]))
    assert '<span class="mark-label" aria-hidden="true">Tide</span>' in page


def test_short_labels_show_on_phones_and_hide_on_wide_screens():
    rules = css_rules(CSS)
    assert any(sel == ".mark-label" for sel, _ in rules)
    # 52rem is where an archive row turns from a stack (phone) into one line (style.css .day-row)
    assert re.search(r"@media \(min-width: 52rem\) \{\s*\.mark-label \{ display: none; \}\s*\}", CSS)
