"""Reading and writing the bulk-invite spreadsheet.

A school has five hundred learners in a file somebody built by hand over three years. It
will contain trailing spaces, blank rows in the middle, a header someone renamed, the same
email twice, and at least one address that is not an address. None of that is a reason to
refuse the whole upload — it is the ordinary condition of real data, and the job here is to
read what can be read and say precisely what could not.

Nothing in this module touches the database. It turns bytes into rows and rows into bytes,
so the rules about who may be invited stay in the service where every other such rule is.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Final

from openpyxl import Workbook, load_workbook

from app.core.errors import ValidationFailed

#: The most rows one upload may carry. A school with more than this splits the file, which
#: is also the right thing for them to do: five hundred invitations arriving at once from a
#: domain that has never sent mail is how a domain's reputation is destroyed.
MAX_ROWS: Final = 500

#: What each column is called in the template, and the field it fills. Matched after
#: lower-casing and collapsing spaces, so "Full Name", "full name" and "FULL  NAME" are the
#: same column — a header is a label a person typed, not an identifier.
COLUMNS: Final[dict[str, str]] = {
    "full name": "full_name",
    "email": "email",
    "branch": "branch",
    "class": "class_name",
    "section": "section",
    "parent name": "parent_name",
    "parent email": "parent_email",
    "relationship": "relationship",
}

REQUIRED: Final = ("full_name", "email")

#: Deliberately permissive. Pydantic does the real validation when the row is used; this
#: only catches the obvious so the preview can say "that is not an address" without a
#: round trip per row.
_LOOKS_LIKE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(slots=True)
class SheetRow:
    """One learner, as the file describes them."""

    #: The spreadsheet's own row number, so an error can be pointed at. Starts at 2,
    #: because row 1 is the header — telling somebody "row 14 is wrong" is only useful if
    #: it is the number they see in Excel.
    number: int
    full_name: str = ""
    email: str = ""
    branch: str = ""
    class_name: str = ""
    section: str = ""
    parent_name: str = ""
    parent_email: str = ""
    relationship: str = ""
    #: Filled by `read_rows` for anything it can tell on its own.
    problems: list[str] = field(default_factory=list)

    @property
    def has_parent(self) -> bool:
        return bool(self.parent_email)


def _clean(value: object) -> str:
    """A cell as text, with the spaces people cannot see removed.

    Excel hands back numbers, dates and `None` as well as strings — a class called "10"
    arrives as the integer ten — so everything is coerced rather than assumed.
    """
    if value is None:
        return ""
    text = str(value).strip()
    # Non-breaking spaces arrive from pasted web pages and are invisible in the cell.
    return text.replace(" ", " ")


def read_rows(data: bytes) -> list[SheetRow]:
    """Parse an uploaded workbook into rows, flagging what is wrong with each.

    Raises only when the *file* is unusable — not a workbook, no header, empty, or longer
    than `MAX_ROWS`. A bad cell is a problem on its row, never a reason to reject the other
    four hundred and ninety-nine.
    """
    try:
        # `read_only` keeps a large file off the heap; `data_only` takes the value a
        # formula produced rather than the formula, which is what the school can see.
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several unrelated types for a bad file
        raise ValidationFailed(
            "That file could not be read as a spreadsheet. Save it as .xlsx and try again."
        ) from exc

    sheet = workbook.active
    if sheet is None:
        raise ValidationFailed("That workbook has no sheets in it.")

    rows = sheet.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        raise ValidationFailed("That file is empty. Start from the template.") from None

    # Map each column position to the field it fills, ignoring any column the school added
    # for its own use — a file with a "Remarks" column is still a valid file.
    positions: dict[int, str] = {}
    for index, title in enumerate(header):
        key = " ".join(_clean(title).lower().split())
        if key in COLUMNS:
            positions[index] = COLUMNS[key]

    found = set(positions.values())
    missing = [
        name for name, field_ in COLUMNS.items() if field_ in REQUIRED and field_ not in found
    ]
    if missing:
        raise ValidationFailed(
            "The file needs a column for " + " and ".join(missing) + ". "
            "Download the template and copy your data into it."
        )

    parsed: list[SheetRow] = []
    seen_emails: dict[str, int] = {}

    for offset, raw in enumerate(rows, start=2):
        values = {field_: _clean(raw[i]) if i < len(raw) else "" for i, field_ in positions.items()}
        # A blank row in the middle is somebody's spacing, not a record.
        if not any(values.values()):
            continue

        row = SheetRow(number=offset, **values)

        if not row.full_name:
            row.problems.append("no name")
        if not row.email:
            row.problems.append("no email address")
        elif not _LOOKS_LIKE_EMAIL.match(row.email):
            row.problems.append("that is not an email address")
        else:
            row.email = row.email.lower()
            first_seen = seen_emails.get(row.email)
            if first_seen is not None:
                row.problems.append(f"the same address is already on row {first_seen}")
            else:
                seen_emails[row.email] = row.number

        if row.parent_email:
            row.parent_email = row.parent_email.lower()
            if not _LOOKS_LIKE_EMAIL.match(row.parent_email):
                row.problems.append("the parent's address is not an email address")
            elif row.parent_email == row.email:
                row.problems.append("the learner and the parent have the same address")

        parsed.append(row)
        if len(parsed) > MAX_ROWS:
            raise ValidationFailed(
                f"That file has more than {MAX_ROWS} learners in it. Split it into smaller "
                f"files — sending hundreds of invitations at once also makes them more "
                f"likely to land in a spam folder."
            )

    if not parsed:
        raise ValidationFailed("That file has a header but no learners in it.")
    return parsed


def build_template() -> bytes:
    """The workbook a school downloads, fills in, and uploads back.

    Carries one worked example row. A blank template gets filled in wrongly far more often
    than one that shows what a row is supposed to look like, and the example is obvious
    enough to delete.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Learners"

    headers = [name.title() for name in COLUMNS]
    sheet.append(headers)
    sheet.append(
        [
            "Riya Sharma",
            "riya.sharma@example.com",
            "MCA",
            "MCA 1st Year",
            "A",
            "Meera Sharma",
            "meera.sharma@example.com",
            "Mother",
        ]
    )

    for index, name in enumerate(headers, start=1):
        # Wide enough to read without the school having to drag every column.
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = max(
            16, len(name) + 4
        )
    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
