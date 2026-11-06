"""Completion reports for Institute and Branch Admins (``homework:report``).

Completion is "submissions received ÷ submissions expected", where expected is each
homework's class size counted from today's active enrolments. A student who joins mid-term
therefore counts against older homework too; that is the simple, explainable choice, and
the per-homework detail sheet in the export lets a school see exactly where the numbers
come from.
"""

from __future__ import annotations

import io
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from app.core.db import Db, ids_in
from app.core.errors import NotFound
from app.modules.ai.pricing import IST
from app.modules.homework import schemas
from app.modules.homework.access import enabled_institutes
from app.modules.homework.models import Homework, HomeworkSubmission
from app.modules.org.models import Branch, Class, ClassEnrollment
from app.modules.rbac import service as rbac
from app.modules.rbac.scopes import PLATFORM
from app.modules.rbac.service import Authorized
from app.modules.users.models import User


async def _scope_match(
    db: Db,
    guard: Authorized,
    *,
    class_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    institute_id: uuid.UUID | None,
) -> dict[str, Any]:
    if class_id is not None:
        await guard.ensure_class(class_id)
        return {"class_id": class_id}
    if branch_id is not None:
        branch = await db.get(Branch, branch_id)
        if branch is None:
            raise NotFound("That branch does not exist.")
        await guard.ensure(
            await rbac.resolve_scope(db, institute_id=branch.institute_id, branch_id=branch.id)
        )
        return {"branch_id": branch_id}
    if institute_id is not None:
        scopes = await guard.ensure_within(institute_id)
        if Authorized.covers_whole_institute(scopes, institute_id):
            return {"institute_id": institute_id}
        return {
            "institute_id": institute_id,
            "branch_id": ids_in(s.branch_id for s in scopes if s.branch_id),
        }
    scopes = guard.usable_scopes()
    if any(s.level == PLATFORM for s in scopes):
        return {}
    clauses = []
    for s in scopes:
        if s.institute_id is None:
            continue
        clause: dict[str, Any] = {"institute_id": s.institute_id}
        if s.branch_id is not None:
            clause["branch_id"] = s.branch_id
        clauses.append(clause)
    return {"$or": clauses} if clauses else {"_id": {"$in": []}}


def _window(date_from: date | None, date_to: date | None) -> dict[str, Any]:
    window: dict[str, datetime] = {}
    if date_from:
        window["$gte"] = datetime.combine(date_from, time.min, tzinfo=IST)
    if date_to:
        window["$lt"] = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=IST)
    return {"due_at": window} if window else {}


async def _load(
    db: Db, guard: Authorized, *, date_from: date | None, date_to: date | None, **scope: Any
) -> tuple[list[Homework], dict[uuid.UUID, dict[str, int]], dict[uuid.UUID, int], dict, dict]:
    match = {
        "$and": [
            await _scope_match(db, guard, **scope),
            {"status": "published", "institute_id": ids_in(await enabled_institutes(db))},
            _window(date_from, date_to),
        ]
    }
    rows = await db.find(Homework, match, sort=[("due_at", 1)], limit=5000)
    ids = [r.id for r in rows]
    class_ids = list({r.class_id for r in rows})
    enrolled = await db.aggregate(
        ClassEnrollment,
        [
            {"$match": {"class_id": {"$in": class_ids}, "status": "active"}},
            {"$group": {"_id": "$class_id", "students": {"$push": "$student_user_id"}}},
        ],
    )
    sizes = {g["_id"]: len(g["students"]) for g in enrolled}
    # Only submissions from students still in the class count, because `expected` is the
    # class as it is today — counting leavers pushed completion past 100%.
    current = list({s for g in enrolled for s in g["students"]})
    received = {
        g["_id"]: {"submitted": g["n"], "late": g["late"]}
        for g in await db.aggregate(
            HomeworkSubmission,
            [
                {"$match": {"homework_id": {"$in": ids}, "student_user_id": {"$in": current}}},
                {
                    "$group": {
                        "_id": "$homework_id",
                        "n": {"$sum": 1},
                        "late": {"$sum": {"$cond": ["$is_late", 1, 0]}},
                    }
                },
            ],
        )
    }
    classes = {
        c["_id"]: c
        for c in await db.raw(Class, {"_id": ids_in(class_ids)}, {"name": 1, "section": 1})
    }
    teachers = {
        u["_id"]: u["full_name"]
        for u in await db.raw(User, {"_id": ids_in({r.created_by for r in rows})}, {"full_name": 1})
    }
    return rows, received, sizes, classes, teachers


def _row(key: str | None, label: str, acc: dict[str, int]) -> schemas.ReportRow:
    expected = acc["expected"]
    return schemas.ReportRow(
        key=key,
        label=label,
        homework=acc["homework"],
        expected=expected,
        submitted=acc["submitted"],
        late=acc["late"],
        completion_rate=round(acc["submitted"] * 100 / expected, 1) if expected else 0.0,
    )


async def summary(
    db: Db,
    *,
    guard: Authorized,
    class_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    institute_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> schemas.ReportOut:
    from app.modules.homework.service import class_label

    rows, received, sizes, classes, teachers = await _load(
        db,
        guard,
        class_id=class_id,
        branch_id=branch_id,
        institute_id=institute_id,
        date_from=date_from,
        date_to=date_to,
    )

    def blank() -> dict[str, int]:
        return {"homework": 0, "expected": 0, "submitted": 0, "late": 0}

    totals = blank()
    by_class: dict[Any, dict[str, int]] = defaultdict(blank)
    by_subject: dict[Any, dict[str, int]] = defaultdict(blank)
    by_teacher: dict[Any, dict[str, int]] = defaultdict(blank)
    for r in rows:
        got = received.get(r.id, {"submitted": 0, "late": 0})
        for acc in (totals, by_class[r.class_id], by_subject[r.subject], by_teacher[r.created_by]):
            acc["homework"] += 1
            acc["expected"] += sizes.get(r.class_id, 0)
            acc["submitted"] += got["submitted"]
            acc["late"] += got["late"]

    return schemas.ReportOut(
        date_from=date_from,
        date_to=date_to,
        totals=_row(None, "All homework", totals),
        by_class=[_row(str(k), class_label(classes.get(k)), v) for k, v in by_class.items()],
        by_subject=[_row(k, k, v) for k, v in sorted(by_subject.items())],
        by_teacher=[_row(str(k), teachers.get(k, "Unknown"), v) for k, v in by_teacher.items()],
    )


async def export(db: Db, *, guard: Authorized, **filters: Any) -> bytes:
    from openpyxl import Workbook

    from app.modules.homework.service import class_label

    report = await summary(db, guard=guard, **filters)
    rows, received, sizes, classes, teachers = await _load(db, guard, **filters)

    book = Workbook()
    sheet = book.active
    sheet.title = "Homework"
    sheet.append(
        [
            "Title",
            "Class",
            "Subject",
            "Teacher",
            "Due (IST)",
            "Expected",
            "Submitted",
            "Late",
            "Completion %",
        ]
    )
    for r in rows:
        got = received.get(r.id, {"submitted": 0, "late": 0})
        expected = sizes.get(r.class_id, 0)
        sheet.append(
            [
                r.title,
                class_label(classes.get(r.class_id)),
                r.subject,
                teachers.get(r.created_by, ""),
                r.due_at.astimezone(IST).strftime("%d-%m-%Y %H:%M"),
                expected,
                got["submitted"],
                got["late"],
                round(got["submitted"] * 100 / expected, 1) if expected else 0,
            ]
        )
    for title, group in (
        ("By class", report.by_class),
        ("By subject", report.by_subject),
        ("By teacher", report.by_teacher),
    ):
        tab = book.create_sheet(title)
        tab.append(
            [
                title.removeprefix("By ").title(),
                "Homework",
                "Expected",
                "Submitted",
                "Late",
                "Completion %",
            ]
        )
        for g in group:
            tab.append([g.label, g.homework, g.expected, g.submitted, g.late, g.completion_rate])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
