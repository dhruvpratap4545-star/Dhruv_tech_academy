"""Reading the file a school actually sends.

No database here: these are about bytes in and rows out. The cases are drawn from what
goes wrong in real learner lists rather than from the code's own branches — a header
somebody renamed, a class that Excel decided is a number, a column added for the school's
own notes, and the invisible space that arrives with anything pasted from a web page.
"""

from __future__ import annotations

import io
import re

import pytest
from openpyxl import Workbook

from app.core.errors import ValidationFailed
from app.modules.users.spreadsheet import MAX_ROWS, build_template, read_rows

HEADERS = [
    "Full Name",
    "Email",
    "Branch",
    "Class",
    "Section",
    "Parent Name",
    "Parent Email",
    "Relationship",
]


def book(header: list[object], *rows: list[object]) -> bytes:
    workbook = Workbook()
    workbook.active.append(header)
    for row in rows:
        workbook.active.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_the_template_round_trips() -> None:
    rows = read_rows(build_template())
    assert len(rows) == 1
    assert rows[0].number == 2
    assert rows[0].problems == []
    assert rows[0].email == "riya.sharma@example.com"


def test_headers_are_matched_however_they_are_capitalised_or_spaced() -> None:
    rows = read_rows(book(["  FULL   NAME ", "EMail"], ["Riya Sharma", "riya@example.com"]))
    assert rows[0].full_name == "Riya Sharma"
    assert rows[0].email == "riya@example.com"


def test_a_column_the_school_added_is_ignored() -> None:
    """A file with a "Remarks" column is still a valid file."""
    rows = read_rows(
        book(
            ["Full Name", "Remarks", "Email"],
            ["Riya Sharma", "paid in full", "riya@example.com"],
        )
    )
    assert rows[0].problems == []
    assert rows[0].email == "riya@example.com"


def test_a_class_excel_stored_as_a_number_is_still_a_class() -> None:
    """Type "10" into a cell and Excel hands back the integer ten."""
    rows = read_rows(book(["Full Name", "Email", "Class"], ["Riya", "riya@example.com", 10]))
    assert rows[0].class_name == "10"


def test_the_space_nobody_can_see_is_removed() -> None:
    """A non-breaking space arrives with anything pasted from a web page, and makes an
    address that looks correct fail to match."""
    rows = read_rows(book(["Full Name", "Email"], [" Riya Sharma ", " riya@example.com "]))
    # The one in the middle is the case `strip()` does not cover, and the one that makes a
    # name look identical to the one already in the database while not matching it.
    assert rows[0].full_name == "Riya Sharma"
    assert rows[0].email == "riya@example.com"


def test_an_address_is_lower_cased_so_the_same_person_is_one_person() -> None:
    rows = read_rows(
        book(
            ["Full Name", "Email", "Parent Email"],
            ["Riya", "RIYA@Example.COM", "Meera@Example.com"],
        )
    )
    assert rows[0].email == "riya@example.com"
    assert rows[0].parent_email == "meera@example.com"


def test_problems_are_collected_per_row_not_raised() -> None:
    rows = read_rows(
        book(
            ["Full Name", "Email"],
            ["", "riya@example.com"],
            ["Arun", "not-an-address"],
            ["Nisha", "nisha@example.com"],
        )
    )
    assert rows[0].problems == ["no name"]
    assert rows[1].problems == ["that is not an email address"]
    assert rows[2].problems == []


def test_the_second_use_of_an_address_points_at_the_first() -> None:
    rows = read_rows(
        book(
            ["Full Name", "Email"],
            ["Riya", "riya@example.com"],
            ["Riya again", "RIYA@example.com"],
        )
    )
    assert rows[0].problems == []
    assert rows[1].problems == ["the same address is already on row 2"]


def test_a_blank_row_in_the_middle_is_not_a_record() -> None:
    rows = read_rows(
        book(
            ["Full Name", "Email"],
            ["Riya", "riya@example.com"],
            [None, None],
            ["Arun", "arun@example.com"],
        )
    )
    # Numbered as Excel numbers them, so "row 4" means the row labelled 4 on screen.
    assert [row.number for row in rows] == [2, 4]


def test_a_learner_cannot_be_listed_as_their_own_parent() -> None:
    rows = read_rows(
        book(
            ["Full Name", "Email", "Parent Email"],
            ["Riya", "riya@example.com", "riya@example.com"],
        )
    )
    assert rows[0].problems == ["the learner and the parent have the same address"]


def test_a_row_with_no_parent_says_so() -> None:
    rows = read_rows(book(["Full Name", "Email"], ["Riya", "riya@example.com"]))
    assert rows[0].has_parent is False


# ------------------------------------------------------- files that cannot be used at all


def test_something_that_is_not_a_workbook_is_refused() -> None:
    with pytest.raises(ValidationFailed, match=re.escape("Save it as .xlsx")):
        read_rows(b"full name,email\nRiya,riya@example.com\n")


def test_a_file_without_the_required_columns_names_them() -> None:
    with pytest.raises(ValidationFailed, match="email"):
        read_rows(book(["Full Name", "Branch"], ["Riya", "MCA"]))


def test_a_file_with_only_a_header_is_refused() -> None:
    with pytest.raises(ValidationFailed, match="no learners"):
        read_rows(book(["Full Name", "Email"]))


def test_a_file_longer_than_the_cap_is_refused() -> None:
    """The cap is about deliverability, not memory: hundreds of invitations at once from a
    domain that has never sent mail is how a domain's reputation is destroyed."""
    rows = [[f"Learner {i}", f"learner{i}@example.com"] for i in range(MAX_ROWS + 1)]
    with pytest.raises(ValidationFailed, match=str(MAX_ROWS)):
        read_rows(book(["Full Name", "Email"], *rows))


def test_a_file_exactly_at_the_cap_is_accepted() -> None:
    rows = [[f"Learner {i}", f"learner{i}@example.com"] for i in range(MAX_ROWS)]
    assert len(read_rows(book(["Full Name", "Email"], *rows))) == MAX_ROWS
