"""Homework Board use cases (Phase 3, Module C).

Assign → notify → submit → check → follow up, on the school's real classes, teachers,
students and parents. Access rules live in ``homework/access.py``; derived student status
in ``homework/status.py``. This module wires them to the database, the audit log, file
storage and email.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from fastapi import UploadFile

from app.core.config import settings
from app.core.db import Db, ids_in, utcnow
from app.core.errors import Conflict, Forbidden, NotFound, RateLimited, ValidationFailed
from app.core.pagination import paginate
from app.modules.audit import events
from app.modules.audit import service as audit
from app.modules.auth.service import RequestMeta
from app.modules.files import service as files
from app.modules.files.models import StoredFile
from app.modules.files.schemas import FileOut
from app.modules.homework import access, schemas
from app.modules.homework.models import MAX_FILES, Homework, HomeworkSubmission
from app.modules.homework.status import (
    TABS,
    is_late,
    student_status,
    submission_refusal,
    visible_to_learners,
)
from app.modules.notifications.email import EmailMessage
from app.modules.org.models import Class, ClassEnrollment
from app.modules.rbac import repository as rbac_repo
from app.modules.rbac.context import AuthContext
from app.modules.rbac.service import Authorized
from app.modules.users.models import User

REMIND_INTERVAL = timedelta(hours=6)
#: A student's board is not paged: a class sets a few hundred homework a year at most.
BOARD_LIMIT = 300


def _record(
    db: Db,
    actor: uuid.UUID,
    meta: RequestMeta | None,
    action: str,
    homework: Homework,
    *,
    target_type: str = "homework",
    target_id: uuid.UUID | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action=action,
        actor_user_id=actor,
        target_type=target_type,
        target_id=target_id or homework.id,
        institute_id=homework.institute_id,
        ip=meta.ip if meta else None,
        user_agent=meta.user_agent if meta else None,
        extra=extra,
    )


def class_label(row: Class | dict[str, Any] | None) -> str:
    if row is None:
        return "Class"
    name = row.name if isinstance(row, Class) else row.get("name", "Class")
    section = row.section if isinstance(row, Class) else row.get("section")
    return f"{name} {section}".strip() if section else name


# --------------------------------------------------------------------------- presenting


async def present(db: Db, rows: Sequence[Homework]) -> list[schemas.HomeworkOut]:
    """Homework as the API returns it, with class names and attachment metadata loaded in
    two batch queries for the whole page rather than two per row."""
    now = utcnow()
    classes = {
        c["_id"]: c
        for c in await db.raw(
            Class, {"_id": ids_in({r.class_id for r in rows})}, {"name": 1, "section": 1}
        )
    }
    stored = await files.files_by_id(db, {fid for r in rows for fid in r.attachment_ids})
    return [
        schemas.HomeworkOut(
            id=r.id,
            institute_id=r.institute_id,
            branch_id=r.branch_id,
            class_id=r.class_id,
            class_name=class_label(classes.get(r.class_id)),
            subject=r.subject,
            node_id=r.node_id,
            title=r.title,
            instructions=r.instructions,
            attachments=[
                FileOut.model_validate(stored[f]) for f in r.attachment_ids if f in stored
            ],
            medium=r.medium,
            total_marks=r.total_marks,
            publish_at=r.publish_at,
            due_at=r.due_at,
            allow_late=r.allow_late,
            allow_resubmit=r.allow_resubmit,
            status=r.status,
            is_visible=visible_to_learners(status=r.status, publish_at=r.publish_at, now=now),
            created_by=r.created_by,
            created_at=r.created_at,
        )
        for r in rows
    ]


async def present_submissions(
    db: Db, rows: Sequence[HomeworkSubmission], *, with_names: bool = False
) -> list[schemas.SubmissionOut]:
    stored = await files.files_by_id(db, {fid for r in rows for fid in r.file_ids})
    names: dict[uuid.UUID, str] = {}
    if with_names:
        names = {
            u["_id"]: u["full_name"]
            for u in await db.raw(
                User, {"_id": ids_in({r.student_user_id for r in rows})}, {"full_name": 1}
            )
        }
    return [
        schemas.SubmissionOut(
            id=r.id,
            homework_id=r.homework_id,
            student_user_id=r.student_user_id,
            student_name=names.get(r.student_user_id),
            text=r.text,
            files=[FileOut.model_validate(stored[f]) for f in r.file_ids if f in stored],
            submitted_at=r.submitted_at,
            is_late=r.is_late,
            attempts=r.attempts,
            status=r.status,
            marks=r.marks,
            grade=r.grade,
            remark=r.remark,
            checked_at=r.checked_at,
        )
        for r in rows
    ]


# ------------------------------------------------------------------------------ writing


async def _validate_node(node_id: uuid.UUID | None, institute_id: uuid.UUID) -> None:
    """A linked syllabus topic must be a master node or one of this institute's own."""
    if node_id is None:
        return
    node = (
        await Homework.get_pymongo_collection()
        .database["syllabus_nodes"]
        .find_one({"_id": node_id}, {"institute_id": 1})
    )
    if node is None or node.get("institute_id") not in (None, institute_id):
        raise ValidationFailed("Choose a chapter or topic from the library.")


def _check_dates(publish_at: datetime | None, due_at: datetime) -> None:
    if due_at <= (publish_at or utcnow()):
        raise ValidationFailed("The due date must be after the homework is published.")


async def create_homework(
    db: Db, *, guard: Authorized, payload: schemas.HomeworkCreate, meta: RequestMeta
) -> tuple[Homework, list[EmailMessage]]:
    target = await db.get(Class, payload.class_id)
    if target is None or target.status != "active":
        raise NotFound("That class does not exist.")
    if not await access.can_manage_class(db, guard.context, target.id):
        raise Forbidden("You can only set homework for classes you teach.")
    await _validate_node(payload.node_id, target.institute_id)

    publish_at: datetime | None = None
    status = "draft"
    if payload.publish == "now":
        publish_at, status = utcnow(), "published"
    elif payload.publish == "schedule":
        if payload.publish_at is None or payload.publish_at <= utcnow():
            raise ValidationFailed("Choose a publish time in the future to schedule it.")
        publish_at, status = payload.publish_at, "published"
    _check_dates(publish_at, payload.due_at)

    homework = Homework(
        institute_id=target.institute_id,
        branch_id=target.branch_id,
        class_id=target.id,
        subject=payload.subject,
        node_id=payload.node_id,
        title=payload.title,
        instructions=payload.instructions,
        medium=payload.medium,
        total_marks=payload.total_marks,
        publish_at=publish_at,
        due_at=payload.due_at,
        allow_late=payload.allow_late,
        allow_resubmit=payload.allow_resubmit,
        status=status,  # type: ignore[arg-type]
        created_by=guard.user_id,
    )
    db.add(homework)
    _record(db, guard.user_id, meta, events.HOMEWORK_CREATED, homework, extra={"status": status})
    messages: list[EmailMessage] = []
    if status == "published":
        _record(db, guard.user_id, meta, events.HOMEWORK_PUBLISHED, homework)
        # Scheduled homework is announced when its time comes (`send_scheduled_notices`),
        # not at creation — telling students about work they cannot open yet.
        if publish_at is not None and publish_at <= utcnow():
            messages = await _publish_messages(db, homework)
    return homework, messages


async def update_homework(
    db: Db,
    *,
    guard: Authorized,
    homework_id: uuid.UUID,
    payload: schemas.HomeworkUpdate,
    meta: RequestMeta,
) -> Homework:
    homework = await access.require_manageable(db, guard.context, homework_id, edit=True)
    if homework.status == "archived":
        raise Conflict("Archived homework cannot be changed.")
    changed = payload.model_dump(exclude_unset=True)
    if "node_id" in changed:
        await _validate_node(changed["node_id"], homework.institute_id)
    if "attachment_ids" in changed:
        keep = changed["attachment_ids"] or []
        if not set(keep) <= set(homework.attachment_ids):
            raise ValidationFailed("Upload new files with 'Add attachments'.")
    if "publish_at" in changed and homework.status == "draft":
        changed.pop("publish_at")  # a draft gets its publish time when it is published
    for field, value in changed.items():
        if value is None and field not in ("node_id", "medium", "total_marks"):
            continue
        setattr(homework, field, value)
    _check_dates(homework.publish_at, homework.due_at)
    _record(
        db,
        guard.user_id,
        meta,
        events.HOMEWORK_UPDATED,
        homework,
        extra={"fields": sorted(changed)},
    )
    return homework


async def publish_homework(
    db: Db,
    *,
    guard: Authorized,
    homework_id: uuid.UUID,
    payload: schemas.PublishRequest,
    meta: RequestMeta,
) -> tuple[Homework, list[EmailMessage]]:
    homework = await access.require_manageable(db, guard.context, homework_id, edit=True)
    if homework.status == "archived":
        raise Conflict("Archived homework cannot be published.")
    now = utcnow()
    if visible_to_learners(status=homework.status, publish_at=homework.publish_at, now=now):
        raise Conflict("This homework is already published.")
    publish_at = payload.publish_at or now
    if publish_at < now - timedelta(minutes=1):
        raise ValidationFailed("Choose a publish time that is now or in the future.")
    _check_dates(publish_at, homework.due_at)
    homework.status = "published"
    homework.publish_at = publish_at
    _record(
        db,
        guard.user_id,
        meta,
        events.HOMEWORK_PUBLISHED,
        homework,
        extra={"scheduled": publish_at > now},
    )
    messages = [] if publish_at > now else await _publish_messages(db, homework)
    return homework, messages


async def archive_homework(
    db: Db, *, guard: Authorized, homework_id: uuid.UUID, meta: RequestMeta
) -> Homework:
    homework = await access.require_manageable(db, guard.context, homework_id, edit=True)
    if homework.status != "archived":
        homework.status = "archived"
        _record(db, guard.user_id, meta, events.HOMEWORK_ARCHIVED, homework)
    return homework


async def duplicate_homework(
    db: Db,
    *,
    guard: Authorized,
    homework_id: uuid.UUID,
    payload: schemas.DuplicateRequest,
    meta: RequestMeta,
) -> Homework:
    """A draft copy, for reuse — the same files, a fresh due date to set."""
    source = await access.require_manageable(db, guard.context, homework_id)
    target = await db.get(Class, payload.class_id or source.class_id)
    if target is None or target.status != "active":
        raise NotFound("That class does not exist.")
    if target.institute_id != source.institute_id:
        raise ValidationFailed("Homework can only be copied within the same institute.")
    if not await access.can_manage_class(db, guard.context, target.id):
        raise Forbidden("You can only set homework for classes you teach.")
    due = source.due_at
    if due <= utcnow():
        due = utcnow() + timedelta(days=7)
    copy = Homework(
        institute_id=target.institute_id,
        branch_id=target.branch_id,
        class_id=target.id,
        subject=source.subject,
        node_id=source.node_id,
        title=source.title,
        instructions=source.instructions,
        attachment_ids=list(source.attachment_ids),
        medium=source.medium,
        total_marks=source.total_marks,
        due_at=due,
        allow_late=source.allow_late,
        allow_resubmit=source.allow_resubmit,
        created_by=guard.user_id,
    )
    db.add(copy)
    _record(
        db,
        guard.user_id,
        meta,
        events.HOMEWORK_CREATED,
        copy,
        extra={"status": "draft", "copied_from": str(source.id)},
    )
    return copy


async def add_attachments(
    db: Db,
    *,
    guard: Authorized,
    homework_id: uuid.UUID,
    uploads: list[UploadFile],
    meta: RequestMeta,
) -> Homework:
    homework = await access.require_manageable(db, guard.context, homework_id, edit=True)
    if homework.status == "archived":
        raise Conflict("Archived homework cannot be changed.")
    if not uploads:
        raise ValidationFailed("Choose at least one file.")
    if len(homework.attachment_ids) + len(uploads) > MAX_FILES:
        raise ValidationFailed(f"A homework can have at most {MAX_FILES} attachments.")
    for upload in uploads:
        stored = await files.store_upload(
            db,
            upload=upload,
            institute_id=homework.institute_id,
            purpose="homework_attachment",
            user_id=guard.user_id,
            ip=meta.ip,
            user_agent=meta.user_agent,
        )
        stored.status = "attached"
        homework.attachment_ids = [*homework.attachment_ids, stored.id]
    _record(
        db,
        guard.user_id,
        meta,
        events.HOMEWORK_UPDATED,
        homework,
        extra={"fields": ["attachment_ids"], "added": len(uploads)},
    )
    return homework


# ------------------------------------------------------------------------------ reading


async def list_homework(
    db: Db,
    *,
    guard: Authorized,
    class_id: uuid.UUID | None,
    institute_id: uuid.UUID | None,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[Sequence[Homework], str | None, int]:
    """The teacher and admin list. Anyone else holding ``homework:read`` gets the same
    filter applied, so a student calling it sees only their own classes' work."""
    if institute_id is not None:
        await guard.ensure_within(institute_id)  # 403 when the module is off, as for any list
    if class_id is not None:
        await guard.ensure_class(class_id)
    clauses: list[dict[str, Any]] = [await access.reader_match(db, guard.context, utcnow())]
    if institute_id is not None:
        clauses.append({"institute_id": institute_id})
    if class_id is not None:
        clauses.append({"class_id": class_id})
    if status is not None:
        clauses.append({"status": status})
    return await paginate(db, Homework, {"$and": clauses}, cursor=cursor, limit=limit)


async def get_homework_detail(
    db: Db,
    *,
    context: AuthContext,
    homework_id: uuid.UUID,
    student_id: uuid.UUID | None = None,
) -> schemas.StudentHomeworkOut:
    """One homework. For a student, their own submission and status come with it; for a
    parent, those of the linked child in this class (``student_id`` picks one of several).
    """
    from app.modules.users import repository as users_repo

    now = utcnow()
    homework = await access.require_readable(db, context, homework_id, now)
    if student_id is not None and student_id != context.user_id:
        linked = await users_repo.guardian_link(db, context.user_id, student_id)
        if linked is None or not await rbac_repo.student_enrolled_in_class(
            db, student_id, homework.class_id
        ):
            raise NotFound("That learner does not exist.")
    elif student_id is None and not await rbac_repo.student_enrolled_in_class(
        db, context.user_id, homework.class_id
    ):
        children = await users_repo.children_of(db, context.user_id)
        in_class = await db.distinct(
            ClassEnrollment,
            "student_user_id",
            {
                "class_id": homework.class_id,
                "student_user_id": ids_in(children),
                "status": "active",
            },
        )
        student_id = min(in_class) if in_class else None
    submission = await db.find_one(
        HomeworkSubmission,
        {"homework_id": homework.id, "student_user_id": student_id or context.user_id},
    )
    out = (await present(db, [homework]))[0]
    return schemas.StudentHomeworkOut(
        homework=out,
        student_status=student_status(
            due_at=homework.due_at,
            submission_status=submission.status if submission else None,
            now=now,
        ),
        submission=(await present_submissions(db, [submission]))[0] if submission else None,
    )


async def _active_students(db: Db, class_id: uuid.UUID) -> list[dict[str, Any]]:
    enrolments = await db.raw(
        ClassEnrollment,
        {"class_id": class_id, "status": "active"},
        {"student_user_id": 1, "roll_no": 1},
    )
    users = {
        u["_id"]: u
        for u in await db.raw(
            User,
            {"_id": ids_in(e["student_user_id"] for e in enrolments), "status": {"$ne": "deleted"}},
            {"full_name": 1, "email": 1, "status": 1},
        )
    }
    return [
        {**users[e["student_user_id"]], "roll_no": e.get("roll_no")}
        for e in enrolments
        if e["student_user_id"] in users
    ]


async def tracker(db: Db, *, guard: Authorized, homework_id: uuid.UUID) -> schemas.TrackerOut:
    homework = await access.require_manageable(db, guard.context, homework_id)
    now = utcnow()
    students = await _active_students(db, homework.class_id)
    submissions = {
        s.student_user_id: s
        for s in await db.find(HomeworkSubmission, {"homework_id": homework.id})
    }
    rows = []
    for student in sorted(students, key=lambda s: (s.get("roll_no") or "", s["full_name"])):
        sub = submissions.get(student["_id"])
        rows.append(
            schemas.TrackerRow(
                student_user_id=student["_id"],
                full_name=student["full_name"],
                roll_no=student.get("roll_no"),
                student_status=student_status(
                    due_at=homework.due_at, submission_status=sub.status if sub else None, now=now
                ),
                submission_id=sub.id if sub else None,
                submitted_at=sub.submitted_at if sub else None,
                is_late=bool(sub and sub.is_late),
                marks=sub.marks if sub else None,
            )
        )
    counts = dict.fromkeys(("pending", "overdue", "submitted", "checked", "redo"), 0)
    for row in rows:
        counts[row.student_status] += 1
    return schemas.TrackerOut(
        homework_id=homework.id, counts=counts, late=sum(r.is_late for r in rows), rows=rows
    )


async def remind(
    db: Db, *, guard: Authorized, homework_id: uuid.UUID, meta: RequestMeta
) -> list[EmailMessage]:
    """Email every student who has not submitted (or was asked to redo). Once per six hours
    per homework, so a nervous click does not become ten emails in a child's inbox."""
    from app.modules.notifications.templates import homework_reminder

    homework = await access.require_manageable(db, guard.context, homework_id)
    now = utcnow()
    if not visible_to_learners(status=homework.status, publish_at=homework.publish_at, now=now):
        raise Conflict("Students cannot see this homework yet, so there is nothing to remind.")
    if homework.last_reminded_at and now - homework.last_reminded_at < REMIND_INTERVAL:
        raise RateLimited("A reminder was sent recently. Try again in a few hours.")
    done = set(
        await db.distinct(
            HomeworkSubmission,
            "student_user_id",
            {"homework_id": homework.id, "status": {"$in": ["submitted", "checked"]}},
        )
    )
    klass = await db.get(Class, homework.class_id)
    messages = [
        homework_reminder(
            s["email"],
            s["full_name"],
            title=homework.title,
            class_name=class_label(klass),
            due_at=homework.due_at,
            link=deep_link(homework.id),
        )
        for s in await _active_students(db, homework.class_id)
        if s["_id"] not in done and s.get("status") == "active"
    ]
    homework.last_reminded_at = now
    _record(
        db, guard.user_id, meta, events.HOMEWORK_REMINDED, homework, extra={"sent": len(messages)}
    )
    return messages


async def get_submission(
    db: Db, *, guard: Authorized, homework_id: uuid.UUID, submission_id: uuid.UUID
) -> schemas.SubmissionOut:
    homework = await access.require_manageable(db, guard.context, homework_id)
    submission = await db.find_one(
        HomeworkSubmission, {"_id": submission_id, "homework_id": homework.id}
    )
    if submission is None:
        raise NotFound("That submission does not exist.")
    return (await present_submissions(db, [submission], with_names=True))[0]


async def check_submission(
    db: Db,
    *,
    guard: Authorized,
    homework_id: uuid.UUID,
    submission_id: uuid.UUID,
    payload: schemas.CheckRequest,
    meta: RequestMeta,
) -> HomeworkSubmission:
    homework = await access.require_manageable(db, guard.context, homework_id)
    submission = await db.find_one(
        HomeworkSubmission, {"_id": submission_id, "homework_id": homework.id}
    )
    if submission is None:
        raise NotFound("That submission does not exist.")
    if submission.status == "redo":
        raise Conflict("This was sent back for redo. Check it after the student resubmits.")
    if (
        payload.marks is not None
        and homework.total_marks is not None
        and payload.marks > homework.total_marks
    ):
        raise ValidationFailed(f"Marks cannot be more than {homework.total_marks}.")
    old_marks, old_status = submission.marks, submission.status
    submission.status = "redo" if payload.redo else "checked"
    # A field sent as null (or blank) clears it; a field left out keeps its value.
    sent = payload.model_fields_set
    if "marks" in sent:
        submission.marks = payload.marks
    if "grade" in sent:
        submission.grade = payload.grade or None
    if "remark" in sent:
        submission.remark = payload.remark or None
    submission.checked_by = guard.user_id
    submission.checked_at = utcnow()
    _record(
        db,
        guard.user_id,
        meta,
        events.HOMEWORK_CHECKED,
        homework,
        target_type="homework_submission",
        target_id=submission.id,
        extra={
            "homework_id": str(homework.id),
            "old_marks": old_marks,
            "new_marks": submission.marks,
            "old_status": old_status,
            "new_status": submission.status,
        },
    )
    return submission


# ------------------------------------------------------------------- student and parent


async def board_for(
    db: Db, student_id: uuid.UUID, *, tab: str | None
) -> list[schemas.StudentHomeworkOut]:
    """A learner's homework across every class they are enrolled in, soonest due first."""
    now = utcnow()
    class_ids = await rbac_repo.student_class_ids(db, student_id)
    rows = await db.find(
        Homework,
        {
            "class_id": ids_in(class_ids),
            "institute_id": ids_in(await access.enabled_institutes(db)),
            **access.learner_visible(now),
        },
        sort=[("due_at", 1)],
        limit=BOARD_LIMIT,
    )
    submissions = {
        s.homework_id: s
        for s in await db.find(
            HomeworkSubmission,
            {"student_user_id": student_id, "homework_id": ids_in(r.id for r in rows)},
        )
    }
    wanted = TABS.get(tab) if tab else None
    picked: list[tuple[Homework, str, HomeworkSubmission | None]] = []
    for row in rows:
        sub = submissions.get(row.id)
        derived = student_status(
            due_at=row.due_at, submission_status=sub.status if sub else None, now=now
        )
        if wanted is None or derived in wanted:
            picked.append((row, derived, sub))
    presented = await present(db, [p[0] for p in picked])
    subs = await present_submissions(db, [p[2] for p in picked if p[2] is not None])
    by_homework = {s.homework_id: s for s in subs}
    return [
        schemas.StudentHomeworkOut(
            homework=out, student_status=derived, submission=by_homework.get(out.id)
        )
        for out, (_, derived, _) in zip(presented, picked, strict=True)
    ]


async def my_board(
    db: Db, *, guard: Authorized, tab: str | None
) -> list[schemas.StudentHomeworkOut]:
    return await board_for(db, guard.user_id, tab=tab)


async def child_board(
    db: Db, *, guard: Authorized, student_id: uuid.UUID, tab: str | None
) -> list[schemas.StudentHomeworkOut]:
    """A parent's view of one child. The guardian link is the whole of the authority: a
    parent holds ``homework:read`` institute-wide, and without this check that would mean
    every child in the school."""
    from app.modules.users import repository as users_repo

    if await users_repo.guardian_link(db, guard.user_id, student_id) is None:
        raise NotFound("That learner does not exist.")
    return await board_for(db, student_id, tab=tab)


async def submit(
    db: Db,
    *,
    guard: Authorized,
    homework_id: uuid.UUID,
    text: str,
    uploads: list[UploadFile],
    meta: RequestMeta,
) -> HomeworkSubmission:
    now = utcnow()
    homework = await access.require_readable(db, guard.context, homework_id, now)
    if not visible_to_learners(status=homework.status, publish_at=homework.publish_at, now=now):
        raise NotFound("That homework does not exist.")
    await guard.ensure_class(homework.class_id)  # enrolled in this class, module on
    if not await rbac_repo.student_enrolled_in_class(db, guard.user_id, homework.class_id):
        raise Forbidden("Only students of this class can submit this homework.")
    text = text.strip()
    if not text and not uploads:
        raise ValidationFailed("Write an answer or attach at least one photo or PDF.")
    if len(text) > 10_000:
        raise ValidationFailed("The answer can be at most 10,000 characters.")
    if len(uploads) > MAX_FILES:
        raise ValidationFailed(f"Attach at most {MAX_FILES} files.")

    existing = await db.find_one(
        HomeworkSubmission, {"homework_id": homework.id, "student_user_id": guard.user_id}
    )
    refusal = submission_refusal(
        due_at=homework.due_at,
        allow_late=homework.allow_late,
        allow_resubmit=homework.allow_resubmit,
        existing_status=existing.status if existing else None,
        now=now,
    )
    if refusal:
        raise Conflict(refusal)

    file_ids: list[uuid.UUID] = []
    for upload in uploads:
        stored = await files.store_upload(
            db,
            upload=upload,
            institute_id=homework.institute_id,
            purpose="submission",
            user_id=guard.user_id,
            ip=meta.ip,
            user_agent=meta.user_agent,
        )
        stored.status = "attached"
        file_ids.append(stored.id)

    late = is_late(due_at=homework.due_at, at=now)
    if existing is None:
        submission = HomeworkSubmission(
            homework_id=homework.id,
            class_id=homework.class_id,
            institute_id=homework.institute_id,
            student_user_id=guard.user_id,
            text=text,
            file_ids=file_ids,
            submitted_at=now,
            is_late=late,
        )
        db.add(submission)
    else:
        submission = existing
        submission.text = text
        if file_ids:  # new files replace the old ones; a text-only resubmit keeps them
            submission.file_ids = file_ids
        submission.submitted_at = now
        submission.is_late = late
        submission.attempts += 1
        submission.status = "submitted"
        # A redo is a fresh piece of work: the previous check no longer describes it, and
        # leaving it showed the old marks against an unchecked resubmission.
        submission.marks = None
        submission.grade = None
        submission.remark = None
        submission.checked_by = None
        submission.checked_at = None
    _record(
        db,
        guard.user_id,
        meta,
        events.HOMEWORK_SUBMITTED,
        homework,
        target_type="homework_submission",
        target_id=submission.id,
        extra={
            "homework_id": str(homework.id),
            "attempt": submission.attempts,
            "late": late,
            "files": len(file_ids),
        },
    )
    return submission


# ------------------------------------------------------------------------------- sharing


def deep_link(homework_id: uuid.UUID) -> str:
    return f"{settings.frontend_url.rstrip('/')}/homework/{homework_id}"


async def share_text(db: Db, *, guard: Authorized, homework_id: uuid.UUID) -> schemas.ShareTextOut:
    """The WhatsApp message kept from the old site: title, class, due date and a link.

    Never a student's name or marks — a forwarded WhatsApp message goes wherever the
    group's members send it.
    """
    from urllib.parse import quote

    from app.modules.ai.pricing import IST

    homework = await access.require_manageable(db, guard.context, homework_id)
    klass = await db.get(Class, homework.class_id)
    due = homework.due_at.astimezone(IST).strftime("%d-%m-%Y %I:%M %p")
    url = deep_link(homework.id)
    text = (
        f"📚 Homework: {homework.title}\n"
        f"Class: {class_label(klass)} · {homework.subject}\n"
        f"Due: {due}\n"
        f"Open it here: {url}"
    )
    return schemas.ShareTextOut(
        text=text, url=url, whatsapp_url=f"https://wa.me/?text={quote(text)}"
    )


async def _publish_messages(db: Db, homework: Homework) -> list[EmailMessage]:
    from app.modules.notifications.templates import homework_published

    klass = await db.get(Class, homework.class_id)
    homework.notified_at = utcnow()
    return [
        homework_published(
            s["email"],
            s["full_name"],
            title=homework.title,
            class_name=class_label(klass),
            subject=homework.subject,
            due_at=homework.due_at,
            link=deep_link(homework.id),
        )
        for s in await _active_students(db, homework.class_id)
        if s.get("status") == "active"
    ]


# --------------------------------------------------------------------------- file access


async def _attachment_readable(db: Db, context: AuthContext, stored: StoredFile) -> bool:
    match = await access.reader_match(db, context, utcnow())
    return await db.exists(Homework, {"$and": [{"attachment_ids": stored.id}, match]})


async def _submission_readable(db: Db, context: AuthContext, stored: StoredFile) -> bool:
    """The student who sent it (covered by ``uploaded_by``), their guardians, and whoever
    may manage the homework it belongs to."""
    from app.modules.users import repository as users_repo

    submission = await db.find_one(HomeworkSubmission, {"file_ids": stored.id})
    if submission is None:
        return False
    if await users_repo.guardian_link(db, context.user_id, submission.student_user_id):
        return True
    return await access.can_manage_class(db, context, submission.class_id)


files.register_access("homework_attachment", _attachment_readable)
files.register_access("submission", _submission_readable)


async def send_scheduled_notices(db: Db) -> int:
    """Email students about scheduled homework whose publish time has passed.

    Run every few minutes by a scheduler (``python -m app.cli homework-notify``). Only the
    last day is looked at, so homework published before this existed is never announced
    late, and a scheduler that was down for an hour catches up.

    Sent before being marked, per homework: a crash part-way re-sends one homework's
    emails rather than silently dropping them — the same choice the digest makes.
    """
    from app.modules.notifications.email import send_email

    now = utcnow()
    due = await db.find(
        Homework,
        {
            "status": "published",
            "notified_at": None,
            "publish_at": {"$lte": now, "$gte": now - timedelta(days=1)},
            "institute_id": ids_in(await access.enabled_institutes(db)),
        },
    )
    sent = 0
    for homework in due:
        for message in await _publish_messages(db, homework):
            await send_email(message)
            sent += 1
        await db.commit()
    return sent
