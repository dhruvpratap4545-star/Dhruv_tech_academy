"""Inviting a whole class from a spreadsheet.

The file a school uploads is not clean, and these tests are mostly about that: a blank row
in the middle, the same address twice, a branch that was renamed last year, a parent shared
between two siblings. The property under test throughout is that one bad row costs exactly
one row.
"""

from __future__ import annotations

import io
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from app.modules.users.spreadsheet import COLUMNS, read_rows

pytestmark = pytest.mark.asyncio

PASSWORD = "Jacaranda!Tide4"
HEADERS = [name.title() for name in COLUMNS]


def sheet(*rows: dict[str, str]) -> bytes:
    """A workbook with the template's headers and the rows given, as bytes.

    Written out rather than fixtured because half these tests are about a file that is
    subtly wrong, and the wrongness has to be visible in the test that asserts on it.
    """
    workbook = Workbook()
    workbook.active.append(HEADERS)
    for row in rows:
        workbook.active.append([row.get(name.lower(), "") for name in HEADERS])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def upload(data: bytes, institute_id=None) -> dict:
    """The multipart body httpx needs for an upload."""
    files = {
        "file": (
            "learners.xlsx",
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    return {"files": files, "data": {"institute_id": str(institute_id)} if institute_id else {}}


async def _as(client: AsyncClient, user) -> AsyncClient:
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def college(institute, make_user):
    async def _make():
        row, branch = await institute("Vidya College", "VIDYA1", with_branch="MCA")
        return {
            "institute": row,
            "branch": branch,
            "principal": await make_user("institute_admin", institute_id=row.id),
        }

    return _make


def by_row(body: dict) -> dict[int, dict]:
    return {row["row"]: row for row in body["rows"]}


# ------------------------------------------------------------------------ the template


async def test_the_template_downloads_and_can_be_read_back(client: AsyncClient, college) -> None:
    """A template the reader cannot parse is worse than no template."""
    world = await college()
    await _as(client, world["principal"])

    response = await client.get("/api/v1/users/bulk-invite/template")
    assert response.status_code == 200, response.text
    assert "spreadsheetml" in response.headers["content-type"]
    assert "invite-learners.xlsx" in response.headers["content-disposition"]

    rows = read_rows(response.content)
    assert len(rows) == 1, "the worked example"
    assert rows[0].problems == []
    assert rows[0].has_parent


# -------------------------------------------------------------------------- the preview


async def test_a_preview_writes_nothing(client: AsyncClient, college, outbox) -> None:
    world = await college()
    await _as(client, world["principal"])
    data = sheet(
        {"full name": "Riya Sharma", "email": "riya@vidya.example"},
        {"full name": "Arun Patel", "email": "arun@vidya.example"},
    )

    preview = await client.post(
        "/api/v1/users/bulk-invite/preview", **upload(data, world["institute"].id)
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["dry_run"] is True
    assert [row["outcome"] for row in body["rows"]] == ["ready", "ready"]
    assert body["invited"] == 0

    listed = await client.get("/api/v1/users", params={"search": "vidya.example", "limit": 100})
    assert listed.json()["total"] == 0
    assert outbox.outbox == []


# --------------------------------------------------------------------------- the import


async def test_the_import_invites_the_learner_and_the_parent(
    client: AsyncClient, college, outbox
) -> None:
    world = await college()
    await _as(client, world["principal"])
    data = sheet(
        {
            "full name": "Riya Sharma",
            "email": "riya@vidya.example",
            "parent name": "Meera Sharma",
            "parent email": "meera@parent.example",
            "relationship": "Mother",
        }
    )

    done = await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["invited"] == 1
    assert body["parents"] == 1
    assert body["skipped"] == 0
    assert body["rows"][0]["parent_outcome"] == "invited"

    listed = await client.get("/api/v1/users", params={"search": "riya@vidya.example"})
    student = listed.json()["items"][0]
    assert student["status"] == "invited"

    guardians = await client.get(f"/api/v1/users/{student['id']}/guardians")
    assert [g["email"] for g in guardians.json()] == ["meera@parent.example"]
    assert guardians.json()[0]["relationship"] == "Mother"

    # Both of them are told, and nobody else is.
    assert {m.to for m in outbox.outbox} == {"riya@vidya.example", "meera@parent.example"}


async def test_one_bad_row_does_not_cost_the_good_ones(client: AsyncClient, college) -> None:
    """The reason every row is written inside its own savepoint."""
    world = await college()
    await _as(client, world["principal"])
    data = sheet(
        {"full name": "Riya Sharma", "email": "riya@vidya.example"},
        {"full name": "Broken", "email": "not-an-address"},
        {"full name": "Arun Patel", "email": "arun@vidya.example"},
    )

    body = (
        await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    ).json()
    rows = by_row(body)
    assert body["invited"] == 2
    assert body["skipped"] == 1
    assert rows[3]["outcome"] == "skipped"
    assert "not an email address" in rows[3]["reason"]

    listed = await client.get("/api/v1/users", params={"search": "vidya.example", "limit": 100})
    assert listed.json()["total"] == 2


async def test_the_same_address_twice_keeps_the_first(client: AsyncClient, college) -> None:
    world = await college()
    await _as(client, world["principal"])
    data = sheet(
        {"full name": "Riya Sharma", "email": "riya@vidya.example"},
        {"full name": "Riya Sharma again", "email": "RIYA@vidya.example"},
    )

    body = (
        await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    ).json()
    rows = by_row(body)
    assert rows[2]["outcome"] == "invited"
    assert rows[3]["outcome"] == "skipped"
    assert "row 2" in rows[3]["reason"]


async def test_somebody_already_on_the_platform_is_skipped(
    client: AsyncClient, college, make_user
) -> None:
    """The common case, not an exception: a school re-uploads last term's file."""
    world = await college()
    await make_user("student", institute_id=world["institute"].id, email="riya@vidya.example")
    await _as(client, world["principal"])

    data = sheet({"full name": "Riya Sharma", "email": "riya@vidya.example"})
    body = (
        await client.post(
            "/api/v1/users/bulk-invite/preview", **upload(data, world["institute"].id)
        )
    ).json()
    assert body["rows"][0]["outcome"] == "skipped"
    assert "already on the platform" in body["rows"][0]["reason"]


async def test_two_siblings_share_one_parent_account(client: AsyncClient, college) -> None:
    world = await college()
    await _as(client, world["principal"])
    data = sheet(
        {
            "full name": "Riya Sharma",
            "email": "riya@vidya.example",
            "parent email": "meera@parent.example",
            "parent name": "Meera Sharma",
        },
        {
            "full name": "Rohan Sharma",
            "email": "rohan@vidya.example",
            "parent email": "meera@parent.example",
        },
    )

    body = (
        await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    ).json()
    rows = by_row(body)
    assert rows[2]["parent_outcome"] == "invited"
    # The second sibling finds the account the first one created rather than making another.
    assert rows[3]["parent_outcome"] == "linked"
    assert body["parents"] == 2

    parents = await client.get("/api/v1/users", params={"search": "meera@parent.example"})
    assert parents.json()["total"] == 1


async def test_a_learner_listed_as_their_own_parent_is_caught_before_anything_is_written(
    client: AsyncClient, college
) -> None:
    world = await college()
    await _as(client, world["principal"])
    data = sheet(
        {
            "full name": "Riya Sharma",
            "email": "riya@vidya.example",
            "parent email": "riya@vidya.example",
        }
    )

    body = (
        await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    ).json()
    row = body["rows"][0]
    assert row["outcome"] == "skipped"
    assert "same address" in row["reason"]


async def test_a_parent_that_fails_does_not_undo_the_child(
    client: AsyncClient, college, make_user, db
) -> None:
    """The learner is on the platform either way; the adult can be added afterwards.

    A removed account is the realistic way this happens: the address is in the school's
    file because the parent was here last year, and it cannot be invited again.
    """
    world = await college()
    gone = await make_user(
        "parent", institute_id=world["institute"].id, email="meera@parent.example"
    )
    gone.status = "deleted"
    # Written, not just set: the request runs in its own unit of work and reads the
    # database, so an edit left in memory here would be invisible to it.
    await db.flush()
    await _as(client, world["principal"])

    data = sheet(
        {
            "full name": "Riya Sharma",
            "email": "riya@vidya.example",
            "parent email": "meera@parent.example",
        }
    )
    body = (
        await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    ).json()
    row = body["rows"][0]
    assert row["outcome"] == "invited", "the child is not punished for the parent"
    assert row["parent_outcome"] == "skipped"
    assert "removed" in row["parent_reason"]
    assert body["invited"] == 1 and body["parents"] == 0

    listed = await client.get("/api/v1/users", params={"search": "riya@vidya.example"})
    assert listed.json()["total"] == 1


# ------------------------------------------------------------------ branches and classes


async def test_an_unknown_branch_is_named_in_the_reason(client: AsyncClient, college) -> None:
    world = await college()
    await _as(client, world["principal"])
    data = sheet({"full name": "Riya", "email": "riya@vidya.example", "branch": "Mechanical"})

    body = (
        await client.post(
            "/api/v1/users/bulk-invite/preview", **upload(data, world["institute"].id)
        )
    ).json()
    assert body["rows"][0]["outcome"] == "skipped"
    assert "Mechanical" in body["rows"][0]["reason"]


async def test_a_named_class_enrols_the_learner(client: AsyncClient, college, db) -> None:
    from app.modules.org.models import AcademicSession, Class, ClassEnrollment

    world = await college()
    session = AcademicSession(
        institute_id=world["institute"].id,
        name="2026-27",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
        is_current=True,
    )
    db.add(session)
    await db.flush()
    klass = Class(
        institute_id=world["institute"].id,
        branch_id=world["branch"].id,
        academic_session_id=session.id,
        name="MCA 1st Year",
        section="A",
        code="MCA1A",
    )
    db.add(klass)
    await db.commit()

    await _as(client, world["principal"])
    data = sheet(
        {
            "full name": "Riya Sharma",
            "email": "riya@vidya.example",
            "branch": "MCA",
            "class": "MCA 1st Year",
            "section": "A",
        }
    )
    body = (
        await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    ).json()
    assert body["rows"][0]["outcome"] == "invited", body["rows"][0]["reason"]
    assert body["rows"][0]["class_name"] == "MCA 1st Year"

    listed = await client.get("/api/v1/users", params={"search": "riya@vidya.example"})
    student_id = uuid.UUID(listed.json()["items"][0]["id"])
    enrolment = await db.find_one(ClassEnrollment, {"student_user_id": student_id})
    assert enrolment is not None, "the class column has to actually enrol them"


async def test_a_class_with_two_sections_asks_which(client: AsyncClient, college, db) -> None:
    from app.modules.org.models import AcademicSession, Class

    world = await college()
    session = AcademicSession(
        institute_id=world["institute"].id,
        name="2026-27",
        start_date=date(2026, 6, 1),
        end_date=date(2027, 5, 31),
        is_current=True,
    )
    db.add(session)
    await db.flush()
    for section in ("A", "B"):
        db.add(
            Class(
                institute_id=world["institute"].id,
                branch_id=world["branch"].id,
                academic_session_id=session.id,
                name="MCA 1st Year",
                section=section,
                code=f"MCA1{section}",
            )
        )
    await db.commit()

    await _as(client, world["principal"])
    data = sheet(
        {
            "full name": "Riya",
            "email": "riya@vidya.example",
            "branch": "MCA",
            "class": "MCA 1st Year",
        }
    )
    body = (
        await client.post(
            "/api/v1/users/bulk-invite/preview", **upload(data, world["institute"].id)
        )
    ).json()
    assert body["rows"][0]["outcome"] == "skipped"
    assert "name the section" in body["rows"][0]["reason"]


# ----------------------------------------------------------------------- who may do this


async def test_an_administrator_cannot_import_into_another_institute(
    client: AsyncClient, college, institute
) -> None:
    world = await college()
    other, _ = await institute("Other College", "OTHER1")
    await _as(client, world["principal"])

    data = sheet({"full name": "Riya", "email": "riya@other.example"})
    refused = await client.post("/api/v1/users/bulk-invite", **upload(data, other.id))
    assert refused.status_code == 403, refused.text


async def test_a_student_cannot_upload_a_file(client: AsyncClient, college, make_user) -> None:
    world = await college()
    student = await make_user("student", institute_id=world["institute"].id)
    await _as(client, student)

    data = sheet({"full name": "Riya", "email": "riya@vidya.example"})
    refused = await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    assert refused.status_code == 403, refused.text
    assert (await client.get("/api/v1/users/bulk-invite/template")).status_code == 403


async def test_a_branch_admin_must_name_the_branch(client: AsyncClient, college, make_user) -> None:
    """Their authority is their branch, so a row with no branch has nowhere to land —
    and saying that is more use than "you do not have permission"."""
    world = await college()
    head = await make_user(
        "branch_admin", institute_id=world["institute"].id, branch_id=world["branch"].id
    )
    await _as(client, head)

    data = sheet(
        {"full name": "Riya", "email": "riya@vidya.example"},
        {"full name": "Arun", "email": "arun@vidya.example", "branch": "MCA"},
    )
    body = (
        await client.post("/api/v1/users/bulk-invite", **upload(data, world["institute"].id))
    ).json()
    rows = by_row(body)
    assert rows[2]["outcome"] == "skipped"
    assert "name the branch" in rows[2]["reason"]
    assert rows[3]["outcome"] == "invited", rows[3]["reason"]


# --------------------------------------------------------------------------- bad files


async def test_a_file_that_is_not_a_spreadsheet_is_refused(client: AsyncClient, college) -> None:
    world = await college()
    await _as(client, world["principal"])

    refused = await client.post(
        "/api/v1/users/bulk-invite",
        **upload(b"full name,email\nRiya,riya@vidya.example\n", world["institute"].id),
    )
    assert refused.status_code == 422, refused.text
    assert "save it as .xlsx" in refused.json()["error"]["message"].lower()


async def test_a_file_without_an_email_column_is_refused(client: AsyncClient, college) -> None:
    world = await college()
    await _as(client, world["principal"])

    workbook = Workbook()
    workbook.active.append(["Full Name", "Branch"])
    workbook.active.append(["Riya Sharma", "MCA"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    refused = await client.post(
        "/api/v1/users/bulk-invite", **upload(buffer.getvalue(), world["institute"].id)
    )
    assert refused.status_code == 422, refused.text
    assert "email" in refused.json()["error"]["message"]


async def test_a_blank_row_in_the_middle_is_skipped_and_the_numbers_still_match(
    client: AsyncClient, college
) -> None:
    """An administrator told "row 4 is wrong" has to find row 4 in Excel, not row 3."""
    world = await college()
    await _as(client, world["principal"])
    data = sheet(
        {"full name": "Riya", "email": "riya@vidya.example"},
        {},
        {"full name": "Arun", "email": "arun@vidya.example"},
    )

    body = (
        await client.post(
            "/api/v1/users/bulk-invite/preview", **upload(data, world["institute"].id)
        )
    ).json()
    assert sorted(by_row(body)) == [2, 4]
