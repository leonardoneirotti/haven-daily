"""Renderer: publication line and corrections (spec §2.3, §6, ADR 0001).

A brief is published directly by the morning job. The page shows when it was
built ("Published 06:52") and, after a hand-made correction, when it was last
corrected ("Corrected 09:14"). Every correction note is listed under
"How this brief was made".
"""

import json
import re
from pathlib import Path

import pytest

from haven import render

PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_BRIEFS = PROJECT_DIR / "data" / "sample" / "briefs"

BUILT = "2026-10-29T06:52:00+01:00"


def correction(at, note="Fixed something."):
    return {"at": at, "note": note}


# --- publication line: built_at + corrections -> text ----------------------------


def test_no_corrections_shows_published_time_only():
    assert render.publication_line(BUILT, []) == "Published 06:52 · Amsterdam time"


def test_one_correction_shows_its_time():
    line = render.publication_line(BUILT, [correction("2026-10-29T09:14:00+01:00")])
    assert line == "Published 06:52 · Corrected 09:14 · Amsterdam time"


def test_two_corrections_show_the_latest():
    corrections = [correction("2026-10-29T09:14:00+01:00"), correction("2026-10-29T11:05:00+01:00")]
    line = render.publication_line(BUILT, corrections)
    assert line == "Published 06:52 · Corrected 11:05 · Amsterdam time"


def test_latest_correction_is_found_by_time_not_by_list_order():
    corrections = [correction("2026-10-29T11:05:00+01:00"), correction("2026-10-29T09:14:00+01:00")]
    line = render.publication_line(BUILT, corrections)
    assert line == "Published 06:52 · Corrected 11:05 · Amsterdam time"


def test_times_are_shown_in_amsterdam_time_even_if_written_in_utc():
    # 05:52 UTC = 06:52 CET; 08:14 UTC = 09:14 CET
    line = render.publication_line("2026-10-29T05:52:00Z", [correction("2026-10-29T08:14:00+00:00")])
    assert line == "Published 06:52 · Corrected 09:14 · Amsterdam time"


def test_correction_on_a_later_day_also_shows_the_date():
    line = render.publication_line(BUILT, [correction("2026-10-30T10:02:00+01:00")])
    assert line == "Published 06:52 · Corrected 30 Oct 10:02 · Amsterdam time"


def test_timestamp_without_timezone_is_refused():
    with pytest.raises(ValueError):
        render.publication_line("2026-10-29T06:52:00", [])


# --- rendering a brief ------------------------------------------------------------


def make_brief(**fields):
    """The smallest brief the renderer accepts."""
    brief = {
        "date": "2026-10-29",
        "sample": True,
        "built_at": BUILT,
        "status": [],
        "items": [],
        "build": {"sources_checked": 9, "items_collected": 41, "items_kept": 0, "failures": []},
        "ships": None,
    }
    brief.update(fields)
    return brief


def render_day(tmp_path, brief):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir(parents=True)
    (briefs_dir / f"{brief['date']}.json").write_text(json.dumps(brief), encoding="utf-8")
    render.render_site(briefs_dir, tmp_path / "site")
    return (tmp_path / "site" / "days" / f"{brief['date']}.html").read_text(encoding="utf-8")


def text_of(html):
    """Visible text with tags removed and spaces collapsed, to assert on sentences."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def build_notes(html):
    """The "How this brief was made" section."""
    start = html.index('id="build-title"')
    return html[start : html.index("</section>", start)]


def test_missing_corrections_field_counts_as_none(tmp_path):
    html = render_day(tmp_path, make_brief())
    assert "Published 06:52 · Amsterdam time" in text_of(html)
    assert "Corrected" not in text_of(html)


def test_brief_with_corrections_shows_latest_in_publication_line(tmp_path):
    brief = make_brief(corrections=[
        correction("2026-10-29T09:14:00+01:00", "Item 2: wrong terminal, ECT Delta not APM 2."),
        correction("2026-10-29T11:05:00+01:00", "Rhine level: typo, 94 cm not 49 cm."),
    ])
    html = render_day(tmp_path, brief)
    assert "Published 06:52 · Corrected 11:05 · Amsterdam time" in text_of(html)


def test_every_correction_note_is_listed_under_how_this_brief_was_made(tmp_path):
    brief = make_brief(corrections=[
        correction("2026-10-29T09:14:00+01:00", "Item 2: wrong terminal, ECT Delta not APM 2."),
        correction("2026-10-29T11:05:00+01:00", "Rhine level: typo, 94 cm not 49 cm."),
    ])
    notes = text_of(build_notes(render_day(tmp_path, brief)))
    assert "Corrected 09:14 Item 2: wrong terminal, ECT Delta not APM 2." in notes
    assert "Corrected 11:05 Rhine level: typo, 94 cm not 49 cm." in notes


def test_brief_without_corrections_lists_none(tmp_path):
    notes = build_notes(render_day(tmp_path, make_brief(corrections=[])))
    assert "Corrected" not in notes


# --- unrated items and the reduced brief (spec §2.1, §5.6, issue #6) ----------------


def item(severity, headline=None, **fields):
    """A news item; severity None = unrated (the AI failed for it)."""
    unrated = severity is None
    base = {
        "severity": severity,
        "headline": headline or f"{severity or 'unrated'} item",
        "url": "https://example.com/news",
        "source": "Sample source",
        "language": "en",
        "published": "2026-10-29T05:10:00+01:00",
        "summary": None if unrated else "Something happened.",
        "impact": None if unrated else "Something follows for planners.",
        "affects": [] if unrated else ["Containers"],
    }
    base.update(fields)
    return base


def test_rank_sorts_high_medium_low_then_unrated():
    items = [item(None, "u"), item("low", "l"), item("high", "h"), item(None, "u2"), item("medium", "m")]
    assert [i["headline"] for i in render.rank_items(items)] == ["h", "m", "l", "u", "u2"]


def test_rank_keeps_source_order_within_a_severity():
    items = [item(None, "u1"), item("medium", "m1"), item(None, "u2"), item("medium", "m2")]
    assert [i["headline"] for i in render.rank_items(items)] == ["m1", "m2", "u1", "u2"]


def test_unrated_items_count_toward_the_max_and_are_cut_first():
    items = [item(None, "u1"), item("low", "l1"), item("low", "l2"), item(None, "u2"),
             item("medium", "m1"), item("high", "h1")]
    ranked = render.rank_items(items)
    assert len(ranked) == render.MAX_ITEMS == 5
    assert [i["headline"] for i in ranked] == ["h1", "m1", "l1", "l2", "u1"]


def test_six_rated_items_leave_no_room_for_unrated():
    items = [item(None, "u")] + [item("low", f"l{n}") for n in range(6)]
    assert all(i["severity"] == "low" for i in render.rank_items(items))


def news_card(html, rank):
    """One item card in the full brief."""
    start = html.index(f'id="item-{rank}"')
    return html[start : html.index("</li>", start)]


def test_unrated_card_has_tag_and_outlined_square_but_no_summary_or_impact(tmp_path):
    html = render_day(tmp_path, make_brief(items=[item("high"), item(None, "Terminal closes gate early")]))
    card = news_card(html, 2)
    assert "num-unrated" in card
    assert "sev-unrated" in card
    assert "Severity: unrated" in text_of(card)
    assert "Terminal closes gate early" in card
    assert "Not enough information" not in card
    assert "Impact for planners" not in card
    assert "The AI step failed for this item" in text_of(card)  # says why, instead of a summary
    assert "-None" not in html  # a null severity never leaks into a class name


def test_unrated_item_shows_in_panel_and_archive_strip(tmp_path):
    brief = make_brief(items=[item("medium"), item(None)])
    html = render_day(tmp_path, brief)
    panel = html[html.index('class="panel-items"') : html.index('class="panel-status"')]
    assert "num-unrated" in panel and "sev-unrated" in panel
    archive = (tmp_path / "site" / "archive.html").read_text(encoding="utf-8")
    assert 'class="slot num-unrated"' in archive
    assert "1 unrated" in archive  # the strip's screen-reader label counts it


def test_unrated_item_with_a_place_is_drawn_unrated_on_the_chart():
    brief = make_brief(items=[item(None, map={"lat": 51.95, "lon": 4.05, "label": "ECT Delta", "side": "right"})])
    callout = render.prepare_briefs([brief])[0]["map"]["callouts"][0]
    assert callout["severity"] == "unrated"


def test_ship_at_the_terminal_of_an_unrated_item_is_still_linked():
    ship = {"name": "Test Ship", "type": "container", "flag": "NL", "lat": 51.95, "lon": 4.05, "heading": 0,
            "status": "moored", "speed_kn": 0, "length_m": 300, "area": "ECT Delta",
            "destination_raw": "", "destination": None, "news_item": 1}
    ships = {"snapshot_start": BUILT, "snapshot_end": BUILT, "source_name": "Sample", "vessels": [ship]}
    brief = render.prepare_briefs([make_brief(items=[item(None)], ships=ships)])[0]
    assert brief["ships"]["vessels"][0]["news_severity"] == "unrated"
    assert brief["ships"]["linked"] == 1


REDUCED_NOTE = "The AI step was unavailable this morning: headlines only, no summaries."


def test_reduced_brief_note_shows_when_the_flag_is_set(tmp_path):
    build = {"sources_checked": 9, "items_collected": 12, "items_kept": 1, "failures": [], "ai_unavailable": True}
    html = render_day(tmp_path, make_brief(items=[item(None)], build=build))
    assert REDUCED_NOTE in text_of(html)


def test_reduced_brief_note_hidden_when_the_flag_is_false_or_missing(tmp_path):
    build = {"sources_checked": 9, "items_collected": 12, "items_kept": 1, "failures": [], "ai_unavailable": False}
    assert REDUCED_NOTE not in text_of(render_day(tmp_path / "a", make_brief(items=[item(None)], build=build)))
    assert REDUCED_NOTE not in text_of(render_day(tmp_path / "b", make_brief(items=[item(None)])))


def test_reduced_brief_without_items_does_not_claim_nothing_met_the_bar(tmp_path):
    build = {"sources_checked": 9, "items_collected": 12, "items_kept": 0, "failures": [], "ai_unavailable": True}
    html = text_of(render_day(tmp_path, make_brief(build=build)))
    assert REDUCED_NOTE in html
    assert "nothing met the bar" not in html


# --- the sample site ----------------------------------------------------------------


def load_samples():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAMPLE_BRIEFS.glob("*.json"))]


def test_a_sample_brief_has_an_unrated_item_among_rated_ones():
    assert any(
        any(i["severity"] is None for i in b["items"]) and any(i["severity"] for i in b["items"])
        for b in load_samples()
    )


def test_a_sample_brief_is_reduced_and_all_its_items_are_unrated():
    reduced = [b for b in load_samples() if b["build"].get("ai_unavailable")]
    assert len(reduced) == 1
    brief = reduced[0]
    assert brief["sample"] is True
    assert brief["items"] and all(i["severity"] is None for i in brief["items"])
    strike = next(s for s in brief["status"] if s["key"] == "strike")
    assert strike["value"] is None and strike["level"] is None  # spec §5.6: strike flag = No data


def test_unrated_sample_items_have_no_ai_text():
    for brief in load_samples():
        for i in brief["items"]:
            if i["severity"] is None:
                assert i["summary"] is None and i["impact"] is None, i["headline"]


def test_samples_use_the_new_fields():
    for path in sorted(SAMPLE_BRIEFS.glob("*.json")):
        brief = json.loads(path.read_text(encoding="utf-8"))
        assert "review" not in brief, path.name
        assert "published_at" not in brief, path.name
        assert "built_at" in brief, path.name
        assert isinstance(brief["corrections"], list), path.name


def test_at_least_one_sample_has_a_correction():
    briefs = [json.loads(p.read_text(encoding="utf-8")) for p in SAMPLE_BRIEFS.glob("*.json")]
    assert any(brief["corrections"] for brief in briefs)


def test_site_renders_from_the_samples(tmp_path):
    # StrictUndefined makes any template typo or missing field fail here.
    count = render.render_site(SAMPLE_BRIEFS, tmp_path / "site")
    assert count == 4
    for page in ("index.html", "archive.html", "about.html"):
        assert (tmp_path / "site" / page).is_file()
