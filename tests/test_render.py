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
    briefs_dir.mkdir()
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


# --- the sample site ----------------------------------------------------------------


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
    assert count == 3
    for page in ("index.html", "archive.html", "about.html"):
        assert (tmp_path / "site" / page).is_file()
