"""Who may see and who may manage a homework. Every read and write asks here.

**Reading** is expressed as a MongoDB filter, not a yes/no per document. The list, the
detail page, the file download and the parent view all apply the *same* filter, so they
cannot disagree — the "list hides it but the detail endpoint shows it" defect that the
users module has already met twice.

* Faculty, students and parents hold ``homework:read`` across their branch or institute,
  so for them the scope says nothing useful. Their reach is membership: the classes a
  teacher teaches, the classes a student is enrolled in, and the classes a parent's
  guardian-linked children are enrolled in. Students and parents additionally see only
  published homework whose publish time has arrived.
* Everyone else reads by scope: platform, institute, or branch.
* Homework in an institute that has the module switched off is invisible to all.

**Managing** goes through the engine (``rbac.service.can`` with the class), plus one
narrowing the engine does not make: its membership step only applies to people who are
*purely* faculty or student, so a teacher who is also a parent at the same school would
otherwise manage every class in their branch. For anyone holding only membership-narrowed
roles, teaching the class is required here explicitly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.core.db import Db, ids_in
from app.core.errors import Forbidden, NotFound
from app.modules.homework.models import Homework
from app.modules.org.models import ClassEnrollment, ClassFaculty
from app.modules.rbac import repository as rbac_repo
from app.modules.rbac import service as rbac
from app.modules.rbac.catalog import FACULTY, HOMEWORK_MODULE, PARENT, STUDENT
from app.modules.rbac.context import AuthContext
from app.modules.rbac.models import InstituteModule
from app.modules.rbac.scopes import PLATFORM
from app.modules.rbac.service import Authorized

MEMBERSHIP_ROLES = frozenset({FACULTY, STUDENT, PARENT})
NOTHING: dict[str, Any] = {"_id": {"$in": []}}


def membership_only(context: AuthContext) -> bool:
    keys = {a.role_key for a in context.assignments}
    return bool(keys) and keys <= MEMBERSHIP_ROLES


def learner_visible(now: datetime) -> dict[str, Any]:
    return {"status": "published", "publish_at": {"$lte": now}}


async def enabled_institutes(db: Db) -> list[uuid.UUID]:
    return await db.distinct(
        InstituteModule, "institute_id", {"module_key": HOMEWORK_MODULE, "enabled": True}
    )


async def children_class_ids(db: Db, parent_id: uuid.UUID) -> set[uuid.UUID]:
    from app.modules.users import repository as users_repo

    children = await users_repo.children_of(db, parent_id)
    if not children:
        return set()
    return set(
        await db.distinct(
            ClassEnrollment,
            "class_id",
            {"student_user_id": ids_in(children), "status": "active"},
        )
    )


async def reader_match(db: Db, context: AuthContext, now: datetime) -> dict[str, Any]:
    """The filter selecting every homework this person may read."""
    if not context.holds("homework:read"):
        return NOTHING
    keys = {a.role_key for a in context.assignments}

    if membership_only(context):
        clauses: list[dict[str, Any]] = []
        if FACULTY in keys:
            taught = await rbac_repo.faculty_class_ids(db, context.user_id)
            clauses.append({"class_id": ids_in(taught)})
        learner_classes: set[uuid.UUID] = set()
        if STUDENT in keys:
            learner_classes |= await rbac_repo.student_class_ids(db, context.user_id)
        if PARENT in keys:
            learner_classes |= await children_class_ids(db, context.user_id)
        if learner_classes:
            clauses.append({"class_id": ids_in(learner_classes), **learner_visible(now)})
        if not clauses:
            return NOTHING
        match: dict[str, Any] = {"$or": clauses}
    else:
        scopes = Authorized(db, context, "homework:read").usable_scopes()
        if any(s.level == PLATFORM for s in scopes):
            match = {}
        else:
            clauses = []
            for s in scopes:
                if s.institute_id is None:
                    continue  # an organisation grant is already spread to its institutes
                clause: dict[str, Any] = {"institute_id": s.institute_id}
                if s.branch_id is not None:
                    clause["branch_id"] = s.branch_id
                clauses.append(clause)
            if not clauses:
                return NOTHING
            match = {"$or": clauses}

    gate = {"institute_id": ids_in(await enabled_institutes(db))}
    return {"$and": [match, gate]} if match else gate


async def require_readable(
    db: Db, context: AuthContext, homework_id: uuid.UUID, now: datetime
) -> Homework:
    """404 both when it does not exist and when it is not the caller's to see."""
    match = await reader_match(db, context, now)
    found = await db.find_one(Homework, {"$and": [{"_id": homework_id}, match]})
    if found is None:
        raise NotFound("That homework does not exist.")
    return found


async def can_manage_class(db: Db, context: AuthContext, class_id: uuid.UUID) -> bool:
    try:
        scope = await rbac.resolve_class_scope(db, class_id)
    except NotFound:
        return False
    if not await rbac.can(db, context, "homework:manage", scope, class_id=class_id):
        return False
    if membership_only(context):
        return await rbac_repo.faculty_teaches_class(db, context.user_id, class_id)
    return True


async def is_class_teacher(db: Db, user_id: uuid.UUID, class_id: uuid.UUID) -> bool:
    return await db.exists(
        ClassFaculty, {"class_id": class_id, "faculty_user_id": user_id, "is_class_teacher": True}
    )


async def require_manageable(
    db: Db, context: AuthContext, homework_id: uuid.UUID, *, edit: bool = False
) -> Homework:
    """The homework, if the caller may manage it; 404 otherwise.

    ``edit`` adds the authorship rule: a teacher changes only homework they set, unless
    they are the class teacher. Admins are not bound by it — the engine already confined
    them to their scope, and a principal correcting a typo is not an intrusion.
    """
    homework = await db.get(Homework, homework_id)
    if homework is None or not await can_manage_class(db, context, homework.class_id):
        raise NotFound("That homework does not exist.")
    if (
        edit
        and membership_only(context)
        and homework.created_by != context.user_id
        and not await is_class_teacher(db, context.user_id, homework.class_id)
    ):
        raise Forbidden(
            "Only the teacher who set this homework, or the class teacher, can change it."
        )
    return homework
