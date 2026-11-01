"""Reading and writing the syllabus import spreadsheet.

One row is one path through the tree — Track › Level › Subject › (Unit) › (Chapter) ›
(Topic). Rows that share a prefix share those nodes, so a content team can paste a whole
board's syllabus from Excel with one row per topic. Like the bulk invite, a bad row is
reported by its Excel row number and the rest are still read.

Nothing here touches the database.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Final

from openpyxl import Workbook, load_workbook

from app.core.errors import ValidationFailed
from app.modules.library.models import TRACKS
from app.modules.library.rules import slugify

MAX_ROWS: Final = 5000

COLUMNS: Final[dict[str, str]] = {
    "track": "track",
    "level": "level",
    "subject": "subject",
    "unit": "unit",
    "chapter": "chapter",
    "topic": "topic",
    "medium": "medium",
    "difficulty": "difficulty",
    "exam tags": "exam_tags",
}
TEMPLATE_HEADERS: Final = [
    "Track",
    "Level",
    "Subject",
    "Unit",
    "Chapter",
    "Topic",
    "Medium",
    "Difficulty",
    "Exam tags",
]
PATH_KINDS: Final = ("level", "subject", "unit", "chapter", "topic")
_TRACK_NAMES: Final = {
    "cbse": "CBSE",
    "neet": "NEET",
    "jee": "JEE",
    "upsc": "UPSC",
    "custom": "Custom",
}
_MEDIUMS: Final = {
    "hindi": ["hi"],
    "hi": ["hi"],
    "english": ["en"],
    "en": ["en"],
    "both": ["hi", "en"],
    "hindi, english": ["hi", "en"],
    "": ["hi", "en"],
}


@dataclass(slots=True)
class ImportRow:
    number: int
    track: str = ""
    #: (kind, name) from the level downwards, empty cells skipped.
    path: list[tuple[str, str]] = field(default_factory=list)
    mediums: list[str] = field(default_factory=lambda: ["hi", "en"])
    difficulty: str | None = None
    exam_tags: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def validate_row(number: int, cells: dict[str, str]) -> ImportRow:
    """Turn one row's cells into an ``ImportRow``, collecting every problem found."""
    row = ImportRow(number=number)
    track = cells.get("track", "").lower()
    if track not in TRACKS:
        row.problems.append(f"Track must be one of {', '.join(_TRACK_NAMES.values())}.")
    row.track = track

    for kind in PATH_KINDS:
        name = cells.get(kind, "")
        if name:
            if len(name) > 200:
                row.problems.append(f"{kind.title()} is longer than 200 characters.")
            elif not slugify(name):
                row.problems.append(
                    f"{kind.title()} '{name}' needs at least one letter or number in English "
                    "so it can be given a code."
                )
            row.path.append((kind, name))
    present = {kind for kind, _ in row.path}
    for required in ("level", "subject"):
        if required not in present:
            row.problems.append(f"{required.title()} is required.")
    if "topic" in present and "chapter" not in present and "unit" not in present:
        row.problems.append("A topic needs the chapter or unit it belongs to.")

    medium = cells.get("medium", "").lower()
    if medium not in _MEDIUMS:
        row.problems.append("Medium must be Hindi, English or Both.")
    else:
        row.mediums = _MEDIUMS[medium]

    difficulty = cells.get("difficulty", "").lower()
    if difficulty and difficulty not in ("easy", "medium", "hard"):
        row.problems.append("Difficulty must be Easy, Medium or Hard.")
    row.difficulty = difficulty or None

    tags = [slugify(t, max_length=20) for t in cells.get("exam_tags", "").split(",")]
    row.exam_tags = sorted({t for t in tags if t})
    return row


def read_rows(data: bytes) -> list[ImportRow]:
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several unrelated types for a bad file
        raise ValidationFailed("That file is not an Excel workbook (.xlsx).") from exc
    sheet = book.active
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if header is None:
        raise ValidationFailed("The spreadsheet is empty.")
    mapping: dict[int, str] = {}
    for index, title in enumerate(header):
        key = COLUMNS.get(_clean(title).lower())
        if key:
            mapping[index] = key
    if "track" not in mapping.values() or "level" not in mapping.values():
        raise ValidationFailed("The first row must be the template's headings (Track, Level, …).")

    parsed: list[ImportRow] = []
    for number, values in enumerate(rows, start=2):
        cells = {mapping[i]: _clean(v) for i, v in enumerate(values) if i in mapping}
        if not any(cells.values()):
            continue  # blank rows in the middle of a sheet are normal
        if len(parsed) >= MAX_ROWS:
            raise ValidationFailed(f"A file can have at most {MAX_ROWS} rows. Please split it.")
        parsed.append(validate_row(number, cells))
    book.close()
    return parsed


def template() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Syllabus"
    sheet.append(TEMPLATE_HEADERS)
    sheet.append(
        ["CBSE", "Class 10", "Science", "", "Electricity", "Ohm's Law", "Both", "Medium", "cbse"]
    )
    sheet.append(
        ["CBSE", "Class 10", "Science", "", "Electricity", "Resistance in Series", "Both", "", ""]
    )
    for column, width in zip("ABCDEFGHI", (10, 14, 18, 18, 30, 30, 10, 12, 16), strict=True):
        sheet.column_dimensions[column].width = width
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def track_name(track: str) -> str:
    return _TRACK_NAMES.get(track, track.upper())
