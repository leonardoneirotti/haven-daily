"""Daily data storage (spec §6, §6.1): three files per day, written once.

    data/items/YYYY-MM-DD.jsonl    every collected item, one JSON object per line
    data/status/YYYY-MM-DD.json    every status reading
    data/briefs/YYYY-MM-DD.json    the published brief

Every test writes into pytest's `tmp_path`, never into the real data/ folder.
"""

from datetime import date, datetime

import pytest

from haven import storage

DAY = date(2026, 11, 2)


def item(n=1, **extra):
    """A small item line as the collector/filter will write it (no article text)."""
    line = {
        "headline": f"Headline {n}",
        "url": f"https://example.org/news/{n}",
        "source": "ect",
        "language": "en",
        "published": "2026-11-02T05:10:00+01:00",
        "filter": {"kept": True, "stage": "rules", "reason": "auto-keep"},
    }
    line.update(extra)
    return line


def brief(day=DAY):
    return {
        "date": day.isoformat(),
        "sample": False,
        "built_at": "2026-11-02T06:52:00+01:00",
        "corrections": [],
        "status": [],
        "items": [item(1, severity="low", summary="Own-words summary.", impact=None)],
        "build": {"failures": []},
        "ships": None,
    }


STATUS = {"readings": [{"key": "rhine", "value": 94, "level": "amber"}]}


# --- where the files go -------------------------------------------------------


def test_each_kind_has_its_own_folder_and_extension(tmp_path):
    assert storage.path("items", DAY, tmp_path) == tmp_path / "items" / "2026-11-02.jsonl"
    assert storage.path("status", DAY, tmp_path) == tmp_path / "status" / "2026-11-02.json"
    assert storage.path("briefs", DAY, tmp_path) == tmp_path / "briefs" / "2026-11-02.json"


def test_unknown_kind_is_refused(tmp_path):
    with pytest.raises(ValueError, match="kind"):
        storage.write("brief", DAY, brief(), tmp_path)  # singular: a typo


@pytest.mark.parametrize("day", ["2026-11-02", datetime(2026, 11, 2, 6, 45)])
def test_day_must_be_a_date(tmp_path, day):
    # A string could be in the wrong format; a datetime hides a time zone question.
    with pytest.raises(TypeError, match="date"):
        storage.write("items", day, [item()], tmp_path)


# --- round trip ---------------------------------------------------------------


def test_items_round_trip(tmp_path):
    items = [item(1), item(2), item(3)]
    storage.write("items", DAY, items, tmp_path)
    assert storage.read("items", DAY, tmp_path) == items


def test_status_round_trip(tmp_path):
    storage.write("status", DAY, STATUS, tmp_path)
    assert storage.read("status", DAY, tmp_path) == STATUS


def test_brief_round_trip(tmp_path):
    storage.write("briefs", DAY, brief(), tmp_path)
    assert storage.read("briefs", DAY, tmp_path) == brief()


def test_three_kinds_for_the_same_day_are_independent(tmp_path):
    storage.write("items", DAY, [item()], tmp_path)
    storage.write("status", DAY, STATUS, tmp_path)
    storage.write("briefs", DAY, brief(), tmp_path)
    assert storage.read("items", DAY, tmp_path) == [item()]


def test_a_day_with_no_items_is_still_recorded(tmp_path):
    # "Nothing collected" is a fact worth keeping, and the day stays write-once.
    storage.write("items", DAY, [], tmp_path)
    assert storage.path("items", DAY, tmp_path).exists()
    assert storage.read("items", DAY, tmp_path) == []


def test_reading_a_missing_day_gives_none(tmp_path):
    assert storage.read("items", DAY, tmp_path) is None
    assert storage.read("briefs", DAY, tmp_path) is None


# --- file format: readable git diffs ------------------------------------------


def test_items_file_is_one_json_object_per_line_ending_in_newline(tmp_path):
    storage.write("items", DAY, [item(1), item(2)], tmp_path)
    raw = storage.path("items", DAY, tmp_path).read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 2
    assert all(line.startswith("{") and line.endswith("}") for line in lines)


def test_json_files_are_indented_and_end_in_newline(tmp_path):
    storage.write("briefs", DAY, brief(), tmp_path)
    text = storage.path("briefs", DAY, tmp_path).read_bytes().decode("utf-8")
    assert text.endswith("}\n")
    assert '\n  "date": "2026-11-02"' in text


def test_line_endings_are_lf_even_on_windows(tmp_path):
    storage.write("items", DAY, [item(1), item(2)], tmp_path)
    storage.write("briefs", DAY, brief(), tmp_path)
    for kind in ("items", "briefs"):
        assert b"\r" not in storage.path(kind, DAY, tmp_path).read_bytes()


def test_dutch_text_is_stored_as_readable_utf8(tmp_path):
    storage.write("items", DAY, [item(headline="Staking op de Maasvlakte – Coöperatie")], tmp_path)
    raw = storage.path("items", DAY, tmp_path).read_bytes()
    assert "Staking op de Maasvlakte – Coöperatie".encode("utf-8") in raw
    assert b"\\u" not in raw  # not escaped as ö


def test_not_a_number_is_refused(tmp_path):
    # NaN is not valid JSON; other tools would fail to read the file.
    with pytest.raises(storage.StorageError, match="NaN"):
        storage.write("status", DAY, {"value": float("nan")}, tmp_path)
    assert not storage.path("status", DAY, tmp_path).exists()


# --- deterministic output -----------------------------------------------------


def test_same_input_gives_byte_identical_files(tmp_path):
    storage.write("items", DAY, [item(1), item(2)], tmp_path / "a")
    storage.write("items", DAY, [item(1), item(2)], tmp_path / "b")
    storage.write("briefs", DAY, brief(), tmp_path / "a")
    storage.write("briefs", DAY, brief(), tmp_path / "b")
    for kind in ("items", "briefs"):
        a = storage.path(kind, DAY, tmp_path / "a").read_bytes()
        b = storage.path(kind, DAY, tmp_path / "b").read_bytes()
        assert a == b


def test_key_order_in_the_input_does_not_change_the_file(tmp_path):
    forward = {"a": 1, "b": {"x": 1, "y": 2}}
    backward = {"b": {"y": 2, "x": 1}, "a": 1}
    storage.write("status", DAY, forward, tmp_path / "a")
    storage.write("status", DAY, backward, tmp_path / "b")
    a = storage.path("status", DAY, tmp_path / "a").read_bytes()
    b = storage.path("status", DAY, tmp_path / "b").read_bytes()
    assert a == b


def test_item_order_is_kept(tmp_path):
    # Lists are not sorted: the order items were collected in is information.
    items = [item(3), item(1), item(2)]
    storage.write("items", DAY, items, tmp_path)
    assert [i["headline"] for i in storage.read("items", DAY, tmp_path)] == ["Headline 3", "Headline 1", "Headline 2"]


# --- written once -------------------------------------------------------------


@pytest.mark.parametrize(
    "kind, first, second",
    [
        ("items", [item(1)], [item(2)]),
        ("status", STATUS, {"readings": []}),
        ("briefs", brief(), {**brief(), "sample": True}),
    ],
)
def test_writing_an_existing_day_fails_and_leaves_it_untouched(tmp_path, kind, first, second):
    storage.write(kind, DAY, first, tmp_path)
    before = storage.path(kind, DAY, tmp_path).read_bytes()
    with pytest.raises(storage.AlreadyWrittenError, match="2026-11-02"):
        storage.write(kind, DAY, second, tmp_path)
    assert storage.path(kind, DAY, tmp_path).read_bytes() == before


def test_already_written_is_also_a_file_exists_error(tmp_path):
    # So callers that only know the standard library can still catch it.
    storage.write("items", DAY, [item()], tmp_path)
    with pytest.raises(FileExistsError):
        storage.write("items", DAY, [item()], tmp_path)


def test_bad_data_writes_nothing(tmp_path):
    # Checked before the file is created, so a failed write can't block the retry.
    with pytest.raises(storage.StorageError):
        storage.write("items", DAY, [item(), "not an object"], tmp_path)
    assert not storage.path("items", DAY, tmp_path).exists()


def test_items_must_be_a_list_of_objects(tmp_path):
    with pytest.raises(storage.StorageError, match="list"):
        storage.write("items", DAY, item(), tmp_path)


def test_brief_date_must_match_the_file_date(tmp_path):
    with pytest.raises(storage.StorageError, match="2026-11-01"):
        storage.write("briefs", DAY, brief(date(2026, 11, 1)), tmp_path)
    assert not storage.path("briefs", DAY, tmp_path).exists()


# --- hard rule 13: never store article text -----------------------------------


@pytest.mark.parametrize(
    "field",
    ["text", "content", "snippet", "body", "description",
     "article_text", "full_text", "body_html", "contentSnippet", "Content"],
)
def test_guard_rejects_fields_that_look_like_article_text(tmp_path, field):
    with pytest.raises(storage.ArticleTextError, match=field):
        storage.write("items", DAY, [item(), item(2, **{field: "Third-party words"})], tmp_path)
    assert not storage.path("items", DAY, tmp_path).exists()


def test_guard_looks_inside_nested_fields(tmp_path):
    nested = item(raw={"entries": [{"snippet": "Third-party words"}]})
    with pytest.raises(storage.ArticleTextError, match=r"raw\.entries\[0\]\.snippet"):
        storage.write("items", DAY, [nested], tmp_path)


def test_guard_also_checks_briefs_and_status(tmp_path):
    bad = brief()
    bad["items"][0]["content"] = "Third-party words"
    with pytest.raises(storage.ArticleTextError):
        storage.write("briefs", DAY, bad, tmp_path)
    with pytest.raises(storage.ArticleTextError):
        storage.write("status", DAY, {"readings": [{"text": "Warning text"}]}, tmp_path)


def test_guard_error_never_repeats_the_text(tmp_path):
    with pytest.raises(storage.ArticleTextError) as caught:
        storage.write("items", DAY, [item(body="Secret third-party paragraph")], tmp_path)
    assert "Secret third-party paragraph" not in str(caught.value)


@pytest.mark.parametrize("field", ["summary", "headline", "impact", "context", "note", "reason", "textile_terminal"])
def test_guard_allows_our_own_fields_and_lookalike_words(tmp_path, field):
    # Whole words only: "context" is not "text"; our own summary is allowed.
    storage.write("items", DAY, [item(**{field: "fine"})], tmp_path)


# --- reading the last N days --------------------------------------------------


def test_recent_days_are_newest_first_and_skip_missing_days(tmp_path):
    for day in (date(2026, 10, 30), date(2026, 11, 1), date(2026, 10, 27)):
        storage.write("items", day, [item(headline=day.isoformat())], tmp_path)
    recent = storage.read_recent("items", before=DAY, days=14, data_dir=tmp_path)
    assert [day for day, _ in recent] == [date(2026, 11, 1), date(2026, 10, 30), date(2026, 10, 27)]
    assert recent[0][1] == [item(headline="2026-11-01")]


def test_recent_days_cover_exactly_n_days_before_the_given_day(tmp_path):
    # 14 days before 2 Nov = 19 Oct .. 1 Nov. The day itself is not included:
    # the collector runs before today's file exists.
    for day in (date(2026, 10, 18), date(2026, 10, 19), date(2026, 11, 1), DAY):
        storage.write("items", day, [item()], tmp_path)
    recent = storage.read_recent("items", before=DAY, days=14, data_dir=tmp_path)
    assert [day for day, _ in recent] == [date(2026, 11, 1), date(2026, 10, 19)]


def test_recent_days_work_across_month_and_clock_change(tmp_path):
    # 25 Oct 2026 is the winter-time change; dates are plain dates, so no effect.
    for day in (date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)):
        storage.write("status", day, STATUS, tmp_path)
    recent = storage.read_recent("status", before=date(2026, 10, 27), days=3, data_dir=tmp_path)
    assert [day for day, _ in recent] == [date(2026, 10, 26), date(2026, 10, 25), date(2026, 10, 24)]


def test_recent_days_with_nothing_stored_is_empty(tmp_path):
    assert storage.read_recent("items", before=DAY, days=60, data_dir=tmp_path) == []


def test_recent_days_needs_a_positive_count(tmp_path):
    with pytest.raises(ValueError, match="days"):
        storage.read_recent("items", before=DAY, days=0, data_dir=tmp_path)


# --- files edited by hand -----------------------------------------------------


def test_hand_edited_items_file_with_blank_lines_and_crlf_still_reads(tmp_path):
    path = storage.path("items", DAY, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"headline": "A"}\r\n\r\n{"headline": "B"}\r\n\r\n')
    assert storage.read("items", DAY, tmp_path) == [{"headline": "A"}, {"headline": "B"}]


def test_broken_line_in_items_file_names_file_and_line(tmp_path):
    path = storage.path("items", DAY, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"headline": "A"}\n{"headline": \n')
    with pytest.raises(storage.StorageError, match=r"2026-11-02\.jsonl, line 2"):
        storage.read("items", DAY, tmp_path)
