"""Daily data files: written once, read back by later runs (spec §6, §6.1).

Three kinds of file, one per day each:

    data/items/YYYY-MM-DD.jsonl    every collected item, kept and dropped, one JSON object per line
    data/status/YYYY-MM-DD.json    every status reading taken that morning
    data/briefs/YYYY-MM-DD.json    the published brief (what the renderer reads)

Rules:
- Written once. Writing a day that already exists raises AlreadyWrittenError
  and leaves the file untouched; only the owner edits a day by hand.
- Stable format, so git diffs stay readable and the same data always gives
  the same bytes: UTF-8 (Dutch letters stay readable), keys sorted, LF line
  endings, a newline at the end.
- Hard rule 13: no third-party article text in the repo. Any field named like
  text / content / snippet / body / description is refused before writing.
- Everything is checked before the file is created, so a refused write leaves
  no half-written file that would block the retry.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_EXTENSIONS = {"items": ".jsonl", "status": ".json", "briefs": ".json"}

# Field names that would carry article text (hard rule 13). Matched as whole
# words inside the name, so "article_text" and "contentSnippet" are caught but
# "context" is not. "description" is the RSS field that holds feed snippets.
_TEXT_WORDS = {"text", "content", "snippet", "body", "description"}


class StorageError(Exception):
    """A day's file can't be written or read as asked."""


class AlreadyWrittenError(StorageError, FileExistsError):
    """The day's file already exists; the pipeline never rewrites it."""


class ArticleTextError(StorageError):
    """The data has a field that looks like article text (hard rule 13)."""


def path(kind: str, day: date, data_dir: Path = DATA_DIR) -> Path:
    """Where the `kind` file for `day` lives: data/<kind>/YYYY-MM-DD.<ext>."""
    if kind not in _EXTENSIONS:
        raise ValueError(f"unknown kind {kind!r} (allowed: {', '.join(_EXTENSIONS)})")
    if not isinstance(day, date) or isinstance(day, datetime):
        raise TypeError(f"day must be a date, not {type(day).__name__}")
    return Path(data_dir) / kind / f"{day.isoformat()}{_EXTENSIONS[kind]}"


def write(kind: str, day: date, data: Any, data_dir: Path = DATA_DIR) -> Path:
    """Write the day's file once. Returns its path.

    items: a list of objects; status: any JSON value; briefs: an object whose
    "date" is `day`.
    """
    target = path(kind, day, data_dir)
    _check(kind, day, data)
    content = _serialise(kind, data)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        # "x" = create only: fails if the file exists, with no gap between check and write.
        with target.open("xb") as f:
            f.write(content)
    except FileExistsError:
        raise AlreadyWrittenError(
            f"{target.parent.name}/{target.name} already exists; a day's file is written once "
            f"(only the owner edits it by hand)"
        ) from None
    return target


def read(kind: str, day: date, data_dir: Path = DATA_DIR) -> Any:
    """The day's data, or None if that day has no file."""
    source = path(kind, day, data_dir)
    try:
        text = source.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return None
    if kind == "items":
        items = []
        # splitlines() also copes with CRLF from a hand edit on Windows.
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise StorageError(f"{source.name}, line {number}: not valid JSON ({e.msg})") from None
        return items
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise StorageError(f"{source.name}: not valid JSON ({e})") from None


def read_recent(kind: str, before: date, days: int, data_dir: Path = DATA_DIR) -> list[tuple[date, Any]]:
    """The `days` days before `before` (not `before` itself), newest first, as (date, data).

    Days with no file are skipped. Used for the duplicate check (14 days)
    and the strike flag (up to 60 days), spec §5.4 and §5.7.
    """
    if days < 1:
        raise ValueError(f"days must be 1 or more, not {days}")
    path(kind, before, data_dir)  # checks kind and date
    found = []
    for back in range(1, days + 1):
        day = before - timedelta(days=back)
        data = read(kind, day, data_dir)
        if data is not None:
            found.append((day, data))
    return found


def first_day(kind: str, data_dir: Path = DATA_DIR) -> date | None:
    """The oldest day that has a `kind` file, or None if there is none yet.

    For items this is the day of the first collect run (the K+N 14-day check, spec §5.8).
    Files whose name isn't a real date (a hand-made note) are ignored.
    """
    if kind not in _EXTENSIONS:
        raise ValueError(f"unknown kind {kind!r} (allowed: {', '.join(_EXTENSIONS)})")
    days = []
    for file in (Path(data_dir) / kind).glob(f"*{_EXTENSIONS[kind]}"):
        try:
            days.append(date.fromisoformat(file.name.removesuffix(_EXTENSIONS[kind])))
        except ValueError:
            continue
    return min(days, default=None)


# --- checks and format --------------------------------------------------------


def _check(kind: str, day: date, data: Any) -> None:
    if kind == "items":
        if not isinstance(data, list):
            raise StorageError(f"items must be a list of objects, not {type(data).__name__}")
        for number, entry in enumerate(data, start=1):
            if not isinstance(entry, dict):
                raise StorageError(f"item {number} must be an object, not {type(entry).__name__}")
    if kind == "briefs":
        if not isinstance(data, dict):
            raise StorageError(f"a brief must be an object, not {type(data).__name__}")
        if data.get("date") != day.isoformat():
            raise StorageError(f"brief has date {data.get('date')!r} but is being written as {day.isoformat()}")
    _refuse_article_text(data, kind)


def _refuse_article_text(value: Any, where: str) -> None:
    """Walk every nested field; the error names the field, never its value."""
    if isinstance(value, dict):
        for key, inner in value.items():
            field = f"{where}.{key}"
            if _TEXT_WORDS & _words(str(key)):
                raise ArticleTextError(
                    f"{field}: field looks like article text; no third-party text may be stored (hard rule 13)"
                )
            _refuse_article_text(inner, field)
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            _refuse_article_text(inner, f"{where}[{index}]")


def _words(name: str) -> set[str]:
    """'contentSnippet' -> {'content', 'snippet'}; 'body_html' -> {'body', 'html'}."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return {w for w in re.split(r"[^a-z0-9]+", spaced.lower()) if w}


def _serialise(kind: str, data: Any) -> bytes:
    try:
        if kind == "items":
            text = "".join(_dumps(entry) + "\n" for entry in data)
        else:
            text = _dumps(data, indent=2) + "\n"
    except ValueError as e:  # NaN / Infinity: not valid JSON
        raise StorageError(f"{kind}: {e} (NaN and Infinity are not valid JSON; use null for no data)") from None
    except TypeError as e:  # e.g. a datetime object instead of an ISO string
        raise StorageError(f"{kind}: {e}") from None
    return text.encode("utf-8")


def _dumps(value: Any, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=indent)
