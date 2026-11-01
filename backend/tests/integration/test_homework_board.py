"""Homework Board end to end (Phase 3, Module C).

Covers client acceptance items 6–8: a teacher assigns to their own class and a student of
that class submits photos while a student of another class cannot see it; marks and a
remark reach the student and the linked parent; a late submission is flagged, the pending
list and reminder work, and the Excel report downloads.
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import pytest_asyncio
from httpx import AsyncClient
from PIL import Image

from app.core.db import Db, utcnow
from app.modules.audit.models import AuditLog
from app.modules.homework.models import Homework, HomeworkSubmission
from app.modules.org.models import AcademicSession, Class, ClassEnrollment, ClassFaculty
from app.modules.rbac.models import InstituteModule
from app.modules.users.models import Guardian

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 120, 200)).save(out, format="JPEG")
    return out.getvalue()


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture
async def world(db: Db, institute, make_user):
    """ABC College, MCA branch, classes 10-A and 10-B; XYZ College with its own admin.

    10-A: faculty_a (set the homework), co_teacher, class_teacher; student_a; parent_a.
    10-B: faculty_b; student_b; parent_b.
    """
    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")
    xyz, _ = await institute("XYZ College", "XYZ", with_branch="CSE")
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
    for row in (abc, xyz):
        db.add(InstituteModule(institute_id=row.id, module_key="homework", enabled=True))
    await db.commit()

    def faculty():
        return make_user("faculty", institute_id=abc.id, branch_id=mca.id)

    people = {
        "abc": abc,
        "xyz": xyz,
        "mca": mca,
        "class_a": class_a,
        "class_b": class_b,
        "faculty_a": await faculty(),
        "co_teacher": await faculty(),
        "class_teacher": await faculty(),
        "faculty_b": await faculty(),
        "student_a": await make_user("student", institute_id=abc.id),
        "student_b": await make_user("student", institute_id=abc.id),
        "parent_a": await make_user("parent", institute_id=abc.id),
        "parent_b": await make_user("parent", institute_id=abc.id),
        "abc_admin": await make_user("institute_admin", institute_id=abc.id),
        "xyz_admin": await make_user("institute_admin", institute_id=xyz.id),
    }
    db.add_all(
        [
            ClassFaculty(class_id=class_a.id, faculty_user_id=people["faculty_a"].id),
            ClassFaculty(class_id=class_a.id, faculty_user_id=people["co_teacher"].id),
            ClassFaculty(
                class_id=class_a.id,
                faculty_user_id=people["class_teacher"].id,
                is_class_teacher=True,
            ),
            ClassFaculty(class_id=class_b.id, faculty_user_id=people["faculty_b"].id),
            ClassEnrollment(class_id=class_a.id, student_user_id=people["student_a"].id),
            ClassEnrollment(class_id=class_b.id, student_user_id=people["student_b"].id),
            Guardian(parent_user_id=people["parent_a"].id, student_user_id=people["student_a"].id),
            Guardian(parent_user_id=people["parent_b"].id, student_user_id=people["student_b"].id),
        ]
    )
    await db.commit()
    return people


def _payload(world, **extra) -> dict:
    return {
        "class_id": str(world["class_a"].id),
        "subject": "Science",
        "title": "Photosynthesis worksheet",
        "instructions": "Answer questions 1 to 5.",
        "total_marks": 10,
        "publish": "now",
        "due_at": (utcnow() + timedelta(days=2)).isoformat(),
        **extra,
    }


async def _assign(client: AsyncClient, world, **extra) -> dict:
    await _as(client, world["faculty_a"])
    response = await client.post("/api/v1/homework", json=_payload(world, **extra))
    assert response.status_code == 201, response.text
    return response.json()


async def _submit(client: AsyncClient, homework_id: str, *, text: str = "", photos: int = 0):
    files = [("files", (f"page{i}.jpg", _jpeg(), "image/jpeg")) for i in range(photos)]
    return await client.put(
        f"/api/v1/homework/{homework_id}/submission",
        data={"text": text},
        files=files or None,
    )


async def _make_overdue(db: Db, homework_id: str, *, allow_late: bool = True) -> None:
    import uuid

    row = await db.get(Homework, uuid.UUID(homework_id))
    row.publish_at = utcnow() - timedelta(days=3)
    row.due_at = utcnow() - timedelta(hours=1)
    row.allow_late = allow_late
    await db.commit()


# ------------------------------------------------------------------- acceptance item 6


async def test_a_teacher_assigns_to_their_class_and_its_students_are_emailed(
    client: AsyncClient, db: Db, world, outbox
) -> None:
    outbox.clear()
    body = await _assign(client, world)

    assert body["status"] == "published"
    assert body["is_visible"] is True
    assert body["class_name"] == "Class 10 A"
    recipients = {m.to for m in outbox.outbox}
    assert recipients == {world["student_a"].email}
    assert await db.count(AuditLog, {"action": "homework_published"}) == 1


async def test_a_teacher_cannot_assign_to_a_class_they_do_not_teach(
    client: AsyncClient, world
) -> None:
    await _as(client, world["faculty_b"])
    response = await client.post("/api/v1/homework", json=_payload(world))
    assert response.status_code == 403


async def test_a_student_submits_photos_and_another_class_cannot_see_it(
    client: AsyncClient, world
) -> None:
    hw = await _assign(client, world)

    await _as(client, world["student_a"])
    board = (await client.get("/api/v1/homework/mine?tab=pending")).json()
    submitted = await _submit(client, hw["id"], text="My answers", photos=2)

    assert [row["homework"]["id"] for row in board] == [hw["id"]]
    assert submitted.status_code == 200, submitted.text
    assert len(submitted.json()["files"]) == 2
    assert submitted.json()["is_late"] is False
    file_id = submitted.json()["files"][0]["id"]
    assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 200

    await _as(client, world["student_b"])
    assert (await client.get("/api/v1/homework/mine")).json() == []
    assert (await client.get(f"/api/v1/homework/{hw['id']}")).status_code == 404
    assert (await _submit(client, hw["id"], text="sneaky")).status_code == 404
    assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 404

    await _as(client, world["faculty_b"])
    assert (await client.get(f"/api/v1/homework/{hw['id']}/tracker")).status_code == 404
    assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 404

    for allowed in ("faculty_a", "parent_a", "abc_admin"):
        await _as(client, world[allowed])
        assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 200, allowed
    await _as(client, world["parent_b"])
    assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 404


async def test_a_submission_needs_text_or_a_file_and_at_most_five_files(
    client: AsyncClient, world
) -> None:
    hw = await _assign(client, world)
    await _as(client, world["student_a"])

    assert (await _submit(client, hw["id"])).status_code == 422
    assert (await _submit(client, hw["id"], photos=6)).status_code == 422


async def test_a_non_image_disguised_as_a_photo_is_refused(client: AsyncClient, world) -> None:
    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    response = await client.put(
        f"/api/v1/homework/{hw['id']}/submission",
        files=[("files", ("hw.jpg", b"MZ\x90\x00binary", "image/jpeg"))],
    )
    assert response.status_code == 422


# ------------------------------------------------------------------- acceptance item 7


async def test_marks_and_remark_reach_the_student_and_the_linked_parent(
    client: AsyncClient, db: Db, world
) -> None:
    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    sub = (await _submit(client, hw["id"], text="Answers")).json()

    await _as(client, world["faculty_a"])
    checked = await client.post(
        f"/api/v1/homework/{hw['id']}/submissions/{sub['id']}/check",
        json={"marks": 8, "grade": "A", "remark": "Good work"},
    )
    too_many = await client.post(
        f"/api/v1/homework/{hw['id']}/submissions/{sub['id']}/check", json={"marks": 11}
    )

    assert checked.status_code == 200, checked.text
    assert checked.json()["student_name"] == world["student_a"].full_name
    assert too_many.status_code == 422

    await _as(client, world["student_a"])
    mine = (await client.get("/api/v1/homework/mine?tab=checked")).json()
    assert mine[0]["submission"]["marks"] == 8
    assert mine[0]["submission"]["remark"] == "Good work"

    await _as(client, world["parent_a"])
    child = await client.get(f"/api/v1/homework/children/{world['student_a'].id}")
    assert child.status_code == 200
    assert child.json()[0]["student_status"] == "checked"
    assert child.json()[0]["submission"]["marks"] == 8

    entry = await db.find_one(AuditLog, {"action": "homework_checked"})
    assert entry.extra["old_marks"] is None and entry.extra["new_marks"] == 8


async def test_a_parent_cannot_see_a_child_they_are_not_linked_to(
    client: AsyncClient, world
) -> None:
    await _assign(client, world)
    await _as(client, world["parent_b"])

    response = await client.get(f"/api/v1/homework/children/{world['student_a'].id}")

    assert response.status_code == 404


async def test_a_parent_sees_the_child_homework_but_never_drafts(
    client: AsyncClient, world
) -> None:
    published = await _assign(client, world)
    await _assign(client, world, publish="draft", title="Draft only")
    await _as(client, world["parent_a"])

    board = (await client.get(f"/api/v1/homework/children/{world['student_a'].id}")).json()
    listed = (await client.get("/api/v1/homework")).json()

    assert [r["homework"]["id"] for r in board] == [published["id"]]
    assert [r["id"] for r in listed["items"]] == [published["id"]]


async def test_redo_reopens_the_submission(client: AsyncClient, db: Db, world) -> None:
    hw = await _assign(client, world, allow_resubmit=False)
    await _as(client, world["student_a"])
    sub = (await _submit(client, hw["id"], text="first")).json()
    assert (await _submit(client, hw["id"], text="again")).status_code == 409

    await _as(client, world["faculty_a"])
    await client.post(
        f"/api/v1/homework/{hw['id']}/submissions/{sub['id']}/check",
        json={"redo": True, "remark": "Show working"},
    )
    await _make_overdue(db, hw["id"], allow_late=False)

    await _as(client, world["student_a"])
    assert (await client.get("/api/v1/homework/mine?tab=pending")).json()[0][
        "student_status"
    ] == "redo"
    again = await _submit(client, hw["id"], text="with working")
    assert again.status_code == 200
    assert again.json()["attempts"] == 2
    assert again.json()["status"] == "submitted"


# ------------------------------------------------------------------- acceptance item 8


async def test_a_late_submission_is_flagged(client: AsyncClient, db: Db, world) -> None:
    hw = await _assign(client, world)
    await _make_overdue(db, hw["id"])
    await _as(client, world["student_a"])

    overdue = (await client.get("/api/v1/homework/mine?tab=overdue")).json()
    response = await _submit(client, hw["id"], text="sorry, late")

    assert [r["homework"]["id"] for r in overdue] == [hw["id"]]
    assert response.status_code == 200
    assert response.json()["is_late"] is True


async def test_late_submissions_are_blocked_when_turned_off(
    client: AsyncClient, db: Db, world
) -> None:
    hw = await _assign(client, world)
    await _make_overdue(db, hw["id"], allow_late=False)
    await _as(client, world["student_a"])

    response = await _submit(client, hw["id"], text="too late")

    assert response.status_code == 409
    assert "not accepted" in response.json()["error"]["message"]


async def test_the_tracker_lists_who_is_pending(client: AsyncClient, db: Db, world) -> None:
    extra = await _make_student_in_class_a(db, world)
    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    await _submit(client, hw["id"], text="done")

    await _as(client, world["faculty_a"])
    tracker = (await client.get(f"/api/v1/homework/{hw['id']}/tracker")).json()

    assert tracker["counts"]["submitted"] == 1
    assert tracker["counts"]["pending"] == 1
    pending = [r for r in tracker["rows"] if r["student_status"] == "pending"]
    assert [r["student_user_id"] for r in pending] == [str(extra.id)]


async def _make_student_in_class_a(db: Db, world):
    from app.core.security import hash_password
    from app.modules.rbac import repository as rbac_repo
    from app.modules.rbac.models import UserRoleAssignment
    from app.modules.users.models import User

    user = User(
        email="second-student@example.com",
        full_name="Second Student",
        password_hash=hash_password("Jacaranda!Tide4"),
        status="active",
    )
    role = await rbac_repo.get_role_by_key(db, "student")
    db.add(user)
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id, institute_id=world["abc"].id))
    db.add(ClassEnrollment(class_id=world["class_a"].id, student_user_id=user.id))
    await db.commit()
    return user


async def test_reminders_go_to_pending_students_and_are_rate_limited(
    client: AsyncClient, db: Db, world, outbox
) -> None:
    extra = await _make_student_in_class_a(db, world)
    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    await _submit(client, hw["id"], text="done")
    outbox.clear()

    await _as(client, world["faculty_a"])
    first = await client.post(f"/api/v1/homework/{hw['id']}/remind")
    second = await client.post(f"/api/v1/homework/{hw['id']}/remind")

    assert first.status_code == 200
    assert first.json() == {"sent": 1}
    assert [m.to for m in outbox.outbox] == [extra.email]
    assert second.status_code == 429


async def test_the_excel_report_downloads_for_admins_only(client: AsyncClient, world) -> None:
    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    await _submit(client, hw["id"], text="done")

    await _as(client, world["abc_admin"])
    summary = await client.get(f"/api/v1/homework/reports/summary?institute_id={world['abc'].id}")
    export = await client.get("/api/v1/homework/reports/export")

    assert summary.status_code == 200, summary.text
    totals = summary.json()["totals"]
    assert (totals["homework"], totals["expected"], totals["submitted"]) == (1, 1, 1)
    assert totals["completion_rate"] == 100.0
    assert summary.json()["by_teacher"][0]["label"] == world["faculty_a"].full_name
    assert export.status_code == 200
    assert export.content[:2] == b"PK"

    await _as(client, world["faculty_a"])
    assert (await client.get("/api/v1/homework/reports/summary")).status_code == 403
    await _as(client, world["xyz_admin"])
    other = await client.get(f"/api/v1/homework/reports/summary?institute_id={world['abc'].id}")
    assert other.status_code == 403
    mine = (await client.get("/api/v1/homework/reports/summary")).json()
    assert mine["totals"]["homework"] == 0


# ------------------------------------------------------------------------ other rules


async def test_scheduled_homework_is_invisible_to_students_until_its_time(
    client: AsyncClient, world
) -> None:
    hw = await _assign(
        client,
        world,
        publish="schedule",
        publish_at=(utcnow() + timedelta(hours=5)).isoformat(),
        due_at=(utcnow() + timedelta(days=3)).isoformat(),
    )
    assert hw["status"] == "published" and hw["is_visible"] is False

    await _as(client, world["student_a"])
    assert (await client.get("/api/v1/homework/mine")).json() == []
    assert (await client.get(f"/api/v1/homework/{hw['id']}")).status_code == 404

    await _as(client, world["faculty_a"])
    assert (await client.get(f"/api/v1/homework/{hw['id']}")).status_code == 200


async def test_a_disabled_module_refuses_everything(client: AsyncClient, db: Db, world) -> None:
    hw = await _assign(client, world)
    row = await db.find_one(
        InstituteModule, {"institute_id": world["abc"].id, "module_key": "homework"}
    )
    row.enabled = False
    await db.commit()

    await _as(client, world["faculty_a"])
    created = await client.post("/api/v1/homework", json=_payload(world))
    listed = await client.get(f"/api/v1/homework?institute_id={world['abc'].id}")
    await _as(client, world["student_a"])
    detail = await client.get(f"/api/v1/homework/{hw['id']}")

    assert created.status_code == 403
    assert listed.status_code == 403
    assert detail.status_code == 404


async def test_share_text_has_no_student_names_or_marks(client: AsyncClient, world) -> None:
    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    sub = (await _submit(client, hw["id"], text="answer")).json()
    await _as(client, world["faculty_a"])
    await client.post(
        f"/api/v1/homework/{hw['id']}/submissions/{sub['id']}/check", json={"marks": 9}
    )

    share = (await client.get(f"/api/v1/homework/{hw['id']}/share-text")).json()

    assert "Photosynthesis worksheet" in share["text"]
    assert "Class 10 A" in share["text"]
    assert share["url"].endswith(f"/homework/{hw['id']}")
    assert world["student_a"].full_name not in share["text"]
    assert "9" not in share["text"].split("Due:")[0]
    assert share["whatsapp_url"].startswith("https://wa.me/?text=")


async def test_only_the_author_or_class_teacher_edits(client: AsyncClient, world) -> None:
    hw = await _assign(client, world)

    await _as(client, world["co_teacher"])
    denied = await client.patch(f"/api/v1/homework/{hw['id']}", json={"title": "Changed"})
    tracker = await client.get(f"/api/v1/homework/{hw['id']}/tracker")
    await _as(client, world["class_teacher"])
    allowed = await client.patch(f"/api/v1/homework/{hw['id']}", json={"title": "Changed"})

    assert denied.status_code == 403
    assert tracker.status_code == 200  # co-teachers still follow and check it
    assert allowed.status_code == 200
    assert allowed.json()["title"] == "Changed"


async def test_attachments_upload_and_follow_homework_visibility(
    client: AsyncClient, world
) -> None:
    hw = await _assign(client, world)
    attached = await client.post(
        f"/api/v1/homework/{hw['id']}/attachments",
        files=[("files", ("worksheet.pdf", PDF, "application/pdf"))],
    )
    assert attached.status_code == 200, attached.text
    file_id = attached.json()["attachments"][0]["id"]
    too_many = await client.post(
        f"/api/v1/homework/{hw['id']}/attachments",
        files=[("files", (f"{i}.pdf", PDF, "application/pdf")) for i in range(5)],
    )
    assert too_many.status_code == 422

    await _as(client, world["student_a"])
    download = await client.get(f"/api/v1/files/{file_id}")
    assert download.status_code == 200
    assert download.content == PDF
    await _as(client, world["student_b"])
    assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 404


async def test_duplicate_makes_a_draft_and_archive_hides_it(client: AsyncClient, world) -> None:
    hw = await _assign(client, world)
    copy = await client.post(f"/api/v1/homework/{hw['id']}/duplicate")
    other_class = await client.post(
        f"/api/v1/homework/{hw['id']}/duplicate", json={"class_id": str(world["class_b"].id)}
    )
    archived = await client.post(f"/api/v1/homework/{hw['id']}/archive")

    assert copy.status_code == 201
    assert copy.json()["status"] == "draft"
    assert other_class.status_code == 403
    assert archived.json()["status"] == "archived"

    await _as(client, world["student_a"])
    assert (await client.get("/api/v1/homework/mine")).json() == []

    await _as(client, world["faculty_a"])
    published = await client.post(f"/api/v1/homework/{copy.json()['id']}/publish")
    assert published.status_code == 200
    assert published.json()["is_visible"] is True


async def test_the_list_is_scoped(client: AsyncClient, world) -> None:
    hw_a = await _assign(client, world)
    await _as(client, world["faculty_b"])
    hw_b = await client.post(
        "/api/v1/homework", json=_payload(world, class_id=str(world["class_b"].id))
    )

    faculty_b = (await client.get("/api/v1/homework")).json()
    await _as(client, world["abc_admin"])
    admin = (await client.get(f"/api/v1/homework?institute_id={world['abc'].id}")).json()
    await _as(client, world["xyz_admin"])
    other = await client.get(f"/api/v1/homework?institute_id={world['abc'].id}")
    other_all = (await client.get("/api/v1/homework")).json()

    assert [r["id"] for r in faculty_b["items"]] == [hw_b.json()["id"]]
    assert {r["id"] for r in admin["items"]} == {hw_a["id"], hw_b.json()["id"]}
    assert other.status_code == 403
    assert other_all["total"] == 0


async def test_a_due_date_before_publishing_is_refused(client: AsyncClient, world) -> None:
    await _as(client, world["faculty_a"])
    response = await client.post(
        "/api/v1/homework",
        json=_payload(world, due_at=(utcnow() - timedelta(hours=1)).isoformat()),
    )
    assert response.status_code == 422


async def test_students_cannot_manage_homework(client: AsyncClient, world) -> None:
    hw = await _assign(client, world)
    await _as(client, world["student_a"])

    assert (await client.post("/api/v1/homework", json=_payload(world))).status_code == 403
    assert (await client.get(f"/api/v1/homework/{hw['id']}/tracker")).status_code == 403
    assert (await client.get("/api/v1/homework/reports/summary")).status_code == 403


async def test_staff_cannot_submit(client: AsyncClient, world) -> None:
    hw = await _assign(client, world)
    await _as(client, world["faculty_a"])
    assert (await _submit(client, hw["id"], text="x")).status_code == 403


async def test_the_weekly_digest_goes_to_linked_parents_only(
    client: AsyncClient, db: Db, world, outbox
) -> None:
    from app.modules.homework.digest import send_digests

    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    await _submit(client, hw["id"], text="done")
    outbox.clear()

    sent = await send_digests(Db())

    assert sent == 1
    assert [m.to for m in outbox.outbox] == [world["parent_a"].email]
    message = outbox.outbox[0]
    assert "Photosynthesis worksheet" in message.text
    assert "Submitted" in message.text
    assert world["student_a"].full_name in message.text
    assert await db.count(HomeworkSubmission, {}) == 1
