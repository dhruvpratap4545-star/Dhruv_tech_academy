"""Regression tests for the organisation / hierarchy / role audit.

Every test here drives the *API*, not the fixtures: the bugs it guards against were
invisible precisely because the older tests wrote organisation links straight into the
database instead of going through the endpoints a real administrator uses.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.db import Db, utcnow
from app.modules.homework.models import Homework
from app.modules.org.models import AcademicSession, Class, ClassEnrollment, ClassFaculty
from app.modules.rbac.models import InstituteModule
from app.modules.rbac.repository import _today
from app.modules.users.models import Guardian

pytestmark = pytest.mark.asyncio

PASSWORD = "Jacaranda!Tide4"


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client


async def _codes(client: AsyncClient, **params) -> set[str]:
    listed = await client.get("/api/v1/institutes", params={"limit": 50, **params})
    assert listed.status_code == 200, listed.text
    return {row["code"] for row in listed.json()["items"]}


def _institute(code: str, organisation_id=None) -> dict:
    body = {"name": f"College {code}", "code": code, "type": "college"}
    if organisation_id is not None:
        body["organisation_id"] = str(organisation_id)
    return body


# ------------------------------------------------------- organisation role assignment


async def test_an_assigned_organisation_admin_stays_inside_their_organisation(
    client: AsyncClient, organisation, institute, make_user
) -> None:
    """Assigning Organisation Admin through the API must store the organisation.

    It used to be dropped, leaving an organisation role with no scope at all — which the
    engine reads as *platform-wide*: the new admin saw every institute on the platform.
    """
    jspm, colleges = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    await organisation("MIT", "MIT", institutes=("MIT1",))
    await institute("Standalone", "SOLO")
    target = await make_user("student", institute_id=colleges[0].id)

    await _as(client, await make_user("super_admin"))
    granted = await client.post(
        f"/api/v1/users/{target.id}/roles",
        json={"role_key": "org_admin", "organisation_id": str(jspm.id)},
    )
    assert granted.status_code == 201, granted.text

    await _as(client, target)
    assert await _codes(client) == {"JSPM1"}
    assert (await client.post("/api/v1/institutes", json=_institute("NOPE"))).status_code == 403

    me = (await client.get("/api/v1/me")).json()
    org_roles = [r for r in me["roles"] if r["role_key"] == "org_admin"]
    assert org_roles and org_roles[0]["organisation_id"] == str(jspm.id)
    assert me["institute_ids"] == [str(colleges[0].id)]


async def test_an_organisation_admin_role_can_be_revoked(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, colleges = await organisation("JSPM", "JSPM", institutes=("JSPM1", "JSPM2"))
    target = await make_user("student", institute_id=colleges[0].id)

    await _as(client, await make_user("super_admin"))
    body = {"role_key": "org_admin", "organisation_id": str(jspm.id)}
    assert (await client.post(f"/api/v1/users/{target.id}/roles", json=body)).status_code == 201
    revoked = await client.request("DELETE", f"/api/v1/users/{target.id}/roles", json=body)
    assert revoked.status_code == 204, revoked.text

    await _as(client, target)
    assert await _codes(client) == {"JSPM1"}  # still a student there, nothing more


async def test_an_organisation_admin_can_be_invited_directly(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    await _as(client, await make_user("super_admin"))
    invited = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Group Head",
            "email": "head@jspm.example",
            "role_key": "org_admin",
            "organisation_id": str(jspm.id),
        },
    )
    assert invited.status_code == 201, invited.text


# ----------------------------------------------------- institutes inside organisations


async def test_creating_an_institute_in_an_organisation_keeps_the_link(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, _ = await organisation("JSPM", "JSPM")

    await _as(client, await make_user("super_admin"))
    created = await client.post("/api/v1/institutes", json=_institute("JSPMP", jspm.id))
    assert created.status_code == 201, created.text
    assert created.json()["organisation_id"] == str(jspm.id)

    org = (await client.get(f"/api/v1/organisations/{jspm.id}")).json()
    assert org["institute_count"] == 1
    assert await _codes(client, organisation_id=str(jspm.id)) == {"JSPMP"}


async def test_an_unknown_organisation_is_refused(client: AsyncClient, make_user) -> None:
    await _as(client, await make_user("super_admin"))
    created = await client.post(
        "/api/v1/institutes",
        json=_institute("GHOST", "00000000-0000-4000-8000-000000000000"),
    )
    assert created.status_code == 404, created.text


async def test_an_organisation_admin_adds_institutes_only_to_their_own_organisation(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    mit, _ = await organisation("MIT", "MIT")
    admin = await make_user("org_admin", organisation_id=jspm.id)

    await _as(client, admin)
    own = await client.post("/api/v1/institutes", json=_institute("JSPM2", jspm.id))
    assert own.status_code == 201, own.text
    # Visible straight away — the cached organisation snapshot is refreshed.
    assert await _codes(client) == {"JSPM1", "JSPM2"}
    branch = await client.post(
        f"/api/v1/institutes/{own.json()['id']}/branches", json={"name": "Main", "code": "MAIN"}
    )
    assert branch.status_code == 201, branch.text

    other = await client.post("/api/v1/institutes", json=_institute("MIT2", mit.id))
    standalone = await client.post("/api/v1/institutes", json=_institute("SOLO"))
    assert other.status_code == 403
    assert standalone.status_code == 403


async def test_an_organisation_admin_creates_an_institute_with_its_admin(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, _ = await organisation("JSPM", "JSPM")
    await _as(client, await make_user("org_admin", organisation_id=jspm.id))
    created = await client.post(
        "/api/v1/institutes/with-admin",
        json={
            "institute": _institute("JSPM3", jspm.id),
            "admin_full_name": "Principal",
            "admin_email": "principal@jspm3.example",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["institute"]["organisation_id"] == str(jspm.id)


async def test_platform_staff_move_an_institute_between_organisations(
    client: AsyncClient, organisation, institute, make_user
) -> None:
    jspm, _ = await organisation("JSPM", "JSPM")
    solo, _ = await institute("Solo", "SOLO")
    org_admin = await make_user("org_admin", organisation_id=jspm.id)
    solo_admin = await make_user("institute_admin", institute_id=solo.id)

    await _as(client, solo_admin)
    refused = await client.patch(
        f"/api/v1/institutes/{solo.id}", json={"organisation_id": str(jspm.id)}
    )
    assert refused.status_code == 403
    renamed = await client.patch(f"/api/v1/institutes/{solo.id}", json={"name": "Solo Renamed"})
    assert renamed.status_code == 200, renamed.text

    await _as(client, await make_user("super_admin"))
    moved = await client.patch(
        f"/api/v1/institutes/{solo.id}", json={"organisation_id": str(jspm.id)}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["organisation_id"] == str(jspm.id)
    assert moved.json()["name"] == "Solo Renamed"

    await _as(client, org_admin)
    assert await _codes(client) == {"SOLO"}

    await _as(client, await make_user("super_admin"))
    detached = await client.patch(f"/api/v1/institutes/{solo.id}", json={"organisation_id": None})
    assert detached.json()["organisation_id"] is None
    await _as(client, org_admin)
    assert await _codes(client) == set()


# ------------------------------------------------------------------ archive and restore


async def test_archiving_an_institute_ends_access_inside_it_and_restore_returns_it(
    client: AsyncClient, institute, make_user
) -> None:
    abc, _ = await institute("ABC", "ABC")
    admin = await make_user("institute_admin", institute_id=abc.id)
    owner = await make_user("super_admin")

    await _as(client, owner)
    assert (await client.post(f"/api/v1/institutes/{abc.id}/archive")).status_code == 200
    await _as(client, admin)
    # No role survives the archive, so they hold no `institute:read` anywhere.
    assert (await client.get("/api/v1/institutes")).status_code == 403
    refused = await client.post(
        f"/api/v1/institutes/{abc.id}/branches", json={"name": "Main", "code": "MAIN"}
    )
    assert refused.status_code == 403

    await _as(client, owner)
    restored = await client.post(f"/api/v1/institutes/{abc.id}/restore")
    assert restored.status_code == 200 and restored.json()["status"] == "active"
    await _as(client, admin)
    assert await _codes(client) == {"ABC"}


async def test_an_archived_organisation_can_be_restored(
    client: AsyncClient, organisation, make_user
) -> None:
    empty, _ = await organisation("Empty", "EMPTY")
    await _as(client, await make_user("super_admin"))
    assert (await client.post(f"/api/v1/organisations/{empty.id}/archive")).status_code == 200
    restored = await client.post(f"/api/v1/organisations/{empty.id}/restore")
    assert restored.status_code == 200 and restored.json()["status"] == "active"


async def test_archiving_a_branch_needs_the_archive_permission(
    client: AsyncClient, institute, make_user
) -> None:
    abc, main = await institute("ABC", "ABC", with_branch="MAIN")
    admin = await make_user("institute_admin", institute_id=abc.id)

    await _as(client, await make_user("super_admin"))
    denied = await client.post(
        f"/api/v1/users/{admin.id}/grants",
        json={
            "permission": "branch:archive",
            "effect": "deny",
            "institute_id": str(abc.id),
            "reason": "Branches are closed by head office only.",
        },
    )
    assert denied.status_code == 201, denied.text

    await _as(client, admin)
    url = f"/api/v1/institutes/{abc.id}/branches/{main.id}"
    assert (await client.patch(url, json={"city": "Pune"})).status_code == 200
    assert (await client.patch(url, json={"status": "archived"})).status_code == 403


# ------------------------------------------------------------ structure and rosters


@pytest_asyncio.fixture
async def school(db: Db, institute, make_user):
    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")
    session = AcademicSession(
        institute_id=abc.id,
        name="2026-27",
        start_date=date(2026, 4, 1),
        end_date=date(2027, 3, 31),
        is_current=True,
    )
    db.add(session)
    class_a = Class(
        institute_id=abc.id,
        branch_id=mca.id,
        academic_session_id=session.id,
        name="Class 10",
        section="A",
        code="10A",
    )
    class_b = Class(
        institute_id=abc.id,
        branch_id=mca.id,
        academic_session_id=session.id,
        name="Class 10",
        section="B",
        code="10B",
    )
    db.add_all([class_a, class_b])
    db.add(InstituteModule(institute_id=abc.id, module_key="homework", enabled=True))
    await db.commit()
    people = {
        "abc": abc,
        "mca": mca,
        "session": session,
        "class_a": class_a,
        "class_b": class_b,
        "admin": await make_user("institute_admin", institute_id=abc.id),
        "branch_admin": await make_user("branch_admin", institute_id=abc.id, branch_id=mca.id),
        "teacher": await make_user("faculty", institute_id=abc.id, branch_id=mca.id),
        "student_a": await make_user("student", institute_id=abc.id),
        "student_b": await make_user("student", institute_id=abc.id),
        "parent_a": await make_user("parent", institute_id=abc.id),
    }
    db.add_all(
        [
            ClassFaculty(class_id=class_a.id, faculty_user_id=people["teacher"].id),
            ClassEnrollment(class_id=class_a.id, student_user_id=people["student_a"].id),
            ClassEnrollment(class_id=class_b.id, student_user_id=people["student_b"].id),
            Guardian(parent_user_id=people["parent_a"].id, student_user_id=people["student_a"].id),
        ]
    )
    await db.commit()
    return people


async def test_branch_level_members_can_open_their_own_institute(
    client: AsyncClient, school, institute
) -> None:
    other, _ = await institute("Elsewhere", "ELS")
    for who in ("branch_admin", "teacher"):
        await _as(client, school[who])
        base = f"/api/v1/institutes/{school['abc'].id}"
        assert (await client.get(base)).status_code == 200, who
        assert (await client.get(f"{base}/modules")).status_code == 200, who
        assert (await client.get(f"/api/v1/institutes/{other.id}")).status_code == 404, who


async def test_a_branch_admin_creates_classes_but_not_sessions(client: AsyncClient, school) -> None:
    await _as(client, school["branch_admin"])
    session = await client.post(
        f"/api/v1/institutes/{school['abc'].id}/sessions",
        json={"name": "2027-28", "start_date": "2027-04-01", "end_date": "2028-03-31"},
    )
    assert session.status_code == 403
    created = await client.post(
        f"/api/v1/branches/{school['mca'].id}/classes",
        json={"name": "Class 11", "code": "11A", "academic_session_id": str(school["session"].id)},
    )
    assert created.status_code == 201, created.text


async def test_class_rosters_and_who_may_join_them(client: AsyncClient, school) -> None:
    class_b = school["class_b"].id
    await _as(client, school["admin"])

    as_teacher = await client.post(
        f"/api/v1/classes/{class_b}/faculty", json={"user_id": str(school["student_a"].id)}
    )
    as_pupil = await client.post(
        f"/api/v1/classes/{class_b}/students", json={"user_id": str(school["teacher"].id)}
    )
    assert as_teacher.status_code == 422, as_teacher.text
    assert as_pupil.status_code == 422, as_pupil.text

    assigned = await client.post(
        f"/api/v1/classes/{class_b}/faculty",
        json={"user_id": str(school["teacher"].id), "subject": "Maths"},
    )
    enrolled = await client.post(
        f"/api/v1/classes/{class_b}/students",
        json={"user_id": str(school["student_a"].id), "roll_no": "7"},
    )
    assert assigned.status_code == 201, assigned.text
    assert enrolled.status_code == 201, enrolled.text

    faculty = (await client.get(f"/api/v1/classes/{class_b}/faculty")).json()
    students = (await client.get(f"/api/v1/classes/{class_b}/students")).json()
    assert [(f["full_name"], f["subject"]) for f in faculty] == [
        (school["teacher"].full_name, "Maths")
    ]
    assert {s["user_id"] for s in students} == {
        str(school["student_a"].id),
        str(school["student_b"].id),
    }


async def test_a_parent_sees_only_their_childs_classes(client: AsyncClient, school) -> None:
    await _as(client, school["parent_a"])
    listed = await client.get(f"/api/v1/institutes/{school['abc'].id}/classes")
    assert listed.status_code == 200, listed.text
    assert [c["code"] for c in listed.json()["items"]] == ["10A"]

    found = (await client.get("/api/v1/search", params={"q": "Class 10"})).json()
    classes = [g for g in found["groups"] if g["kind"] == "class"]
    assert [i["id"] for g in classes for i in g["items"]] == [str(school["class_a"].id)]


async def test_an_admin_elsewhere_is_still_only_a_teacher_here(
    client: AsyncClient, school, institute, make_user
) -> None:
    """Holding Institute Admin at one college must not lift the class check at another."""
    xyz, _ = await institute("XYZ", "XYZ")
    teacher = school["teacher"]
    await _as(client, await make_user("super_admin"))
    promoted = await client.post(
        f"/api/v1/users/{teacher.id}/roles",
        json={"role_key": "institute_admin", "institute_id": str(xyz.id)},
    )
    assert promoted.status_code == 201, promoted.text

    await _as(client, teacher)
    untaught = await client.post(
        f"/api/v1/classes/{school['class_b'].id}/students",
        json={"user_id": str(school["student_a"].id)},
    )
    assert untaught.status_code == 403, untaught.text
    listed = (await client.get(f"/api/v1/institutes/{school['abc'].id}/classes")).json()
    assert [c["code"] for c in listed["items"]] == ["10A"]
    people = (await client.get("/api/v1/users", params={"limit": 100})).json()
    assert str(school["student_b"].id) not in {u["id"] for u in people["items"]}


async def test_a_branch_audit_grant_does_not_open_the_institute_log(
    client: AsyncClient, school, make_user
) -> None:
    branch_admin = school["branch_admin"]
    await _as(client, await make_user("super_admin"))
    allowed = await client.post(
        f"/api/v1/users/{branch_admin.id}/grants",
        json={
            "permission": "audit:read",
            "effect": "allow",
            "institute_id": str(school["abc"].id),
            "branch_id": str(school["mca"].id),
            "reason": "Branch head reviews activity.",
        },
    )
    assert allowed.status_code == 201, allowed.text
    await _as(client, school["admin"])  # writes something to the institute's log
    await client.patch(f"/api/v1/institutes/{school['abc'].id}", json={"name": "ABC Renamed"})

    await _as(client, branch_admin)
    log = await client.get("/api/v1/audit-logs")
    assert log.status_code == 200, log.text
    assert log.json()["items"] == []


# --------------------------------------------------------------------------- leaks


async def test_organisation_search_stays_inside_the_organisation(
    client: AsyncClient, organisation, make_user, db: Db
) -> None:
    from app.modules.org.models import Branch

    jspm, ours = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    _, theirs = await organisation("MIT", "MIT", institutes=("MIT1",))
    db.add_all(
        [
            Branch(institute_id=ours[0].id, name="Hadapsar Campus", code="HAD"),
            Branch(institute_id=theirs[0].id, name="Kothrud Campus", code="KOT"),
        ]
    )
    await db.commit()

    await _as(client, await make_user("org_admin", organisation_id=jspm.id))
    found = (await client.get("/api/v1/search", params={"q": "Campus"})).json()
    titles = {i["title"] for g in found["groups"] for i in g["items"]}
    assert titles == {"Hadapsar Campus"}


async def test_another_institutes_ai_budget_is_not_shown(
    client: AsyncClient, institute, make_user, db: Db
) -> None:
    abc, _ = await institute("ABC", "ABC")
    xyz, _ = await institute("XYZ", "XYZ")
    db.add(InstituteModule(institute_id=abc.id, module_key="ai", enabled=True))
    await db.commit()

    await _as(client, await make_user("institute_admin", institute_id=abc.id))
    own = await client.get("/api/v1/ai/usage/summary", params={"institute_id": str(abc.id)})
    other = await client.get("/api/v1/ai/usage/summary", params={"institute_id": str(xyz.id)})
    assert own.status_code == 200, own.text
    assert other.status_code == 404, other.text


async def test_an_expired_module_stops_serving_reads(client: AsyncClient, school, db: Db) -> None:
    await _as(client, school["teacher"])
    created = await client.post(
        "/api/v1/homework",
        json={
            "class_id": str(school["class_a"].id),
            "subject": "Science",
            "title": "Leaves",
            "publish": "now",
            "due_at": (utcnow() + timedelta(days=2)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text

    await _as(client, school["student_a"])
    assert len((await client.get("/api/v1/homework/mine")).json()) == 1

    row = await db.find_one(
        InstituteModule, {"institute_id": school["abc"].id, "module_key": "homework"}
    )
    row.valid_till = _today() - timedelta(days=1)
    await db.commit()
    mine = await client.get("/api/v1/homework/mine")
    assert mine.status_code in (200, 403)
    assert mine.status_code == 403 or mine.json() == []


# ------------------------------------------------------------------------ homework


async def test_a_resubmitted_redo_does_not_keep_the_old_marks(client: AsyncClient, school) -> None:
    await _as(client, school["teacher"])
    hw = (
        await client.post(
            "/api/v1/homework",
            json={
                "class_id": str(school["class_a"].id),
                "subject": "Science",
                "title": "Roots",
                "total_marks": 10,
                "publish": "now",
                "due_at": (utcnow() + timedelta(days=2)).isoformat(),
            },
        )
    ).json()
    await _as(client, school["student_a"])
    sub = (await client.put(f"/api/v1/homework/{hw['id']}/submission", data={"text": "v1"})).json()

    await _as(client, school["teacher"])
    redo = await client.post(
        f"/api/v1/homework/{hw['id']}/submissions/{sub['id']}/check",
        json={"marks": 3, "remark": "Try again", "redo": True},
    )
    assert redo.status_code == 200, redo.text

    await _as(client, school["student_a"])
    again = await client.put(f"/api/v1/homework/{hw['id']}/submission", data={"text": "v2"})
    assert again.status_code in (200, 201), again.text
    assert again.json()["marks"] is None
    assert again.json()["remark"] is None


async def test_scheduled_homework_is_announced_once_its_time_comes(
    client: AsyncClient, school, db: Db, monkeypatch
) -> None:
    from app.modules.homework import service
    from app.modules.notifications import email

    sent: list = []

    async def capture(message) -> None:
        sent.append(message)

    monkeypatch.setattr(email, "send_email", capture)

    await _as(client, school["teacher"])
    hw = await client.post(
        "/api/v1/homework",
        json={
            "class_id": str(school["class_a"].id),
            "subject": "Science",
            "title": "Stems",
            "publish": "schedule",
            "publish_at": (utcnow() + timedelta(hours=1)).isoformat(),
            "due_at": (utcnow() + timedelta(days=2)).isoformat(),
        },
    )
    assert hw.status_code == 201, hw.text

    assert await service.send_scheduled_notices(db) == 0  # not time yet

    row = await db.get(Homework, __import__("uuid").UUID(hw.json()["id"]))
    row.publish_at = utcnow() - timedelta(minutes=1)
    await db.commit()

    assert await service.send_scheduled_notices(db) == 1  # student_a only
    assert sent[0].to == school["student_a"].email
    assert await service.send_scheduled_notices(db) == 0  # never twice
