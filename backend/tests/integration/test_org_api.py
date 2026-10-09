"""Organisation hierarchy end to end, including the faculty class rules.

Covers acceptance criteria 5 and 6a from PRD §13.
"""

from __future__ import annotations

from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org.models import Class, ClassEnrollment


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "testpassword9!"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture
async def school(institute, make_user, db: AsyncSession):
    """ABC College with an MCA branch, a session, two classes and a faculty on one of them."""
    from app.modules.org.models import AcademicSession, ClassFaculty

    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")

    session = AcademicSession(
        institute_id=abc.id,
        name="2026-27",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        is_current=True,
    )
    db.add(session)
    await db.flush()

    taught = Class(
        institute_id=abc.id,
        branch_id=mca.id,
        academic_session_id=session.id,
        name="MCA 1st Year - A",
        code="MCA1A",
    )
    other = Class(
        institute_id=abc.id,
        branch_id=mca.id,
        academic_session_id=session.id,
        name="MCA 1st Year - B",
        code="MCA1B",
    )
    db.add_all([taught, other])
    await db.flush()

    admin = await make_user("institute_admin", institute_id=abc.id)
    faculty = await make_user("faculty", institute_id=abc.id, branch_id=mca.id)
    student = await make_user("student", institute_id=abc.id)

    db.add(ClassFaculty(class_id=taught.id, faculty_user_id=faculty.id))
    await db.commit()

    return {
        "institute": abc,
        "branch": mca,
        "session": session,
        "taught": taught,
        "other": other,
        "admin": admin,
        "faculty": faculty,
        "student": student,
    }


# ------------------------------------------------------- create institute with admin


async def test_super_admin_creates_an_institute_and_its_first_admin(
    client: AsyncClient, make_user, outbox
) -> None:
    """PRD §13 criterion 5, and §12's "create institute + its Institute Admin" screen."""
    await _as(client, await make_user("super_admin"))

    response = await client.post(
        "/api/v1/institutes/with-admin",
        json={
            "institute": {"name": "New College", "code": "NEWC", "type": "college"},
            "admin_full_name": "Priya Shah",
            "admin_email": "priya@newcollege.edu",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["institute"]["code"] == "NEWC"
    assert body["admin_email"] == "priya@newcollege.edu"

    invitation = outbox.last_to("priya@newcollege.edu")
    assert invitation is not None
    assert "set your" in invitation.subject.lower()


async def test_a_duplicate_institute_code_is_refused(client: AsyncClient, make_user) -> None:
    await _as(client, await make_user("super_admin"))
    body = {"name": "First", "code": "DUP", "type": "college"}
    assert (await client.post("/api/v1/institutes", json=body)).status_code == 201
    second = await client.post(
        "/api/v1/institutes", json={"name": "Second", "code": "dup", "type": "school"}
    )
    assert second.status_code == 409, "codes are normalised, so case must not create a duplicate"


# ----------------------------------------------------------- branches and sessions


async def test_an_admin_can_create_a_session_and_a_class(client: AsyncClient, school) -> None:
    await _as(client, school["admin"])

    session = await client.post(
        f"/api/v1/institutes/{school['institute'].id}/sessions",
        json={"name": "2027-28", "start_date": "2027-07-01", "end_date": "2028-06-30"},
    )
    assert session.status_code == 201, session.text

    created = await client.post(
        f"/api/v1/branches/{school['branch'].id}/classes",
        json={
            "name": "MCA 2nd Year",
            "code": "MCA2A",
            "academic_session_id": session.json()["id"],
        },
    )
    assert created.status_code == 201, created.text


async def test_only_one_session_is_current(client: AsyncClient, school, db: AsyncSession) -> None:
    from app.modules.org.models import AcademicSession

    await _as(client, school["admin"])
    await client.post(
        f"/api/v1/institutes/{school['institute'].id}/sessions",
        json={
            "name": "2027-28",
            "start_date": "2027-07-01",
            "end_date": "2028-06-30",
            "is_current": True,
        },
    )
    rows = (
        (
            await db.execute(
                select(AcademicSession).where(
                    AcademicSession.institute_id == school["institute"].id,
                    AcademicSession.is_current.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_a_class_code_is_unique_within_a_branch_and_session(
    client: AsyncClient, school
) -> None:
    await _as(client, school["admin"])
    response = await client.post(
        f"/api/v1/branches/{school['branch'].id}/classes",
        json={
            "name": "Clash",
            "code": "MCA1A",
            "academic_session_id": str(school["session"].id),
        },
    )
    assert response.status_code == 409


async def test_a_class_cannot_use_another_institutes_session(
    client: AsyncClient, school, institute, make_user
) -> None:
    """Cross-tenant foreign key: the session must belong to the branch's institute."""
    xyz, _ = await institute("XYZ College", "XYZB")
    await _as(client, await make_user("super_admin"))

    other_session = await client.post(
        f"/api/v1/institutes/{xyz.id}/sessions",
        json={"name": "2026-27", "start_date": "2026-07-01", "end_date": "2027-06-30"},
    )
    response = await client.post(
        f"/api/v1/branches/{school['branch'].id}/classes",
        json={
            "name": "Smuggled",
            "code": "SMUG",
            "academic_session_id": other_session.json()["id"],
        },
    )
    assert response.status_code == 422


# ----------------------------------------------- faculty class rules (criterion 6a)


async def test_faculty_can_enrol_a_student_into_a_class_they_teach(
    client: AsyncClient, school
) -> None:
    await _as(client, school["faculty"])
    response = await client.post(
        f"/api/v1/classes/{school['taught'].id}/students",
        json={"user_id": str(school["student"].id)},
    )
    assert response.status_code == 201, response.text


async def test_faculty_cannot_enrol_into_a_class_they_do_not_teach(
    client: AsyncClient, school
) -> None:
    """PRD §13 criterion 6a: any other class returns 403."""
    await _as(client, school["faculty"])
    response = await client.post(
        f"/api/v1/classes/{school['other'].id}/students",
        json={"user_id": str(school["student"].id)},
    )
    assert response.status_code == 403


async def test_an_institute_admin_can_enrol_into_any_class_in_their_institute(
    client: AsyncClient, school
) -> None:
    """Membership gating applies to faculty, not to admins who hold the permission higher up."""
    await _as(client, school["admin"])
    response = await client.post(
        f"/api/v1/classes/{school['other'].id}/students",
        json={"user_id": str(school["student"].id)},
    )
    assert response.status_code == 201, response.text


async def test_faculty_cannot_assign_faculty_to_a_class(client: AsyncClient, school) -> None:
    """PRD §5.3: class_faculty:manage is branch level and above."""
    await _as(client, school["faculty"])
    response = await client.post(
        f"/api/v1/classes/{school['taught'].id}/faculty",
        json={"user_id": str(school["faculty"].id)},
    )
    assert response.status_code == 403


async def test_a_student_from_another_institute_cannot_be_enrolled(
    client: AsyncClient, school, institute, make_user
) -> None:
    xyz, _ = await institute("XYZ College", "XYZC")
    outsider = await make_user("student", institute_id=xyz.id)

    await _as(client, school["admin"])
    response = await client.post(
        f"/api/v1/classes/{school['taught'].id}/students",
        json={"user_id": str(outsider.id)},
    )
    assert response.status_code == 404


async def test_enrolling_twice_is_refused(client: AsyncClient, school) -> None:
    await _as(client, school["admin"])
    body = {"user_id": str(school["student"].id)}
    assert (
        await client.post(f"/api/v1/classes/{school['taught'].id}/students", json=body)
    ).status_code == 201
    second = await client.post(f"/api/v1/classes/{school['taught'].id}/students", json=body)
    assert second.status_code == 409


async def test_removing_a_student_keeps_the_history(
    client: AsyncClient, school, db: AsyncSession
) -> None:
    """PRD §2: moving classes keeps history, so the row is marked left, not deleted."""
    await _as(client, school["admin"])
    await client.post(
        f"/api/v1/classes/{school['taught'].id}/students",
        json={"user_id": str(school["student"].id)},
    )
    response = await client.delete(
        f"/api/v1/classes/{school['taught'].id}/students/{school['student'].id}"
    )
    assert response.status_code == 204

    row = await db.scalar(
        select(ClassEnrollment).where(
            ClassEnrollment.class_id == school["taught"].id,
            ClassEnrollment.student_user_id == school["student"].id,
        )
    )
    assert row is not None, "the enrolment row must survive"
    assert row.status == "left"


async def test_re_enrolling_reuses_the_existing_row(
    client: AsyncClient, school, db: AsyncSession
) -> None:
    await _as(client, school["admin"])
    body = {"user_id": str(school["student"].id)}
    await client.post(f"/api/v1/classes/{school['taught'].id}/students", json=body)
    await client.delete(f"/api/v1/classes/{school['taught'].id}/students/{school['student'].id}")
    again = await client.post(f"/api/v1/classes/{school['taught'].id}/students", json=body)
    assert again.status_code == 201

    rows = (
        (
            await db.execute(
                select(ClassEnrollment).where(
                    ClassEnrollment.class_id == school["taught"].id,
                    ClassEnrollment.student_user_id == school["student"].id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].status == "active"


# ------------------------------------------------------------------- class visibility


async def test_faculty_see_only_the_classes_they_teach(client: AsyncClient, school) -> None:
    await _as(client, school["faculty"])
    response = await client.get(f"/api/v1/institutes/{school['institute'].id}/classes")
    assert response.status_code == 200
    codes = {c["code"] for c in response.json()["items"]}
    assert codes == {"MCA1A"}


async def test_an_admin_sees_every_class_in_their_institute(client: AsyncClient, school) -> None:
    await _as(client, school["admin"])
    codes = {
        c["code"]
        for c in (await client.get(f"/api/v1/institutes/{school['institute'].id}/classes")).json()[
            "items"
        ]
    }
    assert codes == {"MCA1A", "MCA1B"}


async def test_archiving_a_class_does_not_delete_it(
    client: AsyncClient, school, db: AsyncSession
) -> None:
    await _as(client, school["admin"])
    response = await client.patch(
        f"/api/v1/classes/{school['taught'].id}", json={"status": "archived"}
    )
    assert response.status_code == 200

    row = await db.get(Class, school["taught"].id)
    assert row is not None and row.status == "archived"
