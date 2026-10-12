"""Queries for the organisation hierarchy.

Every function that reads institute-scoped data takes an ``institute_id`` and filters on it.
That is the tenant boundary: a caller cannot ask this layer for "class X" without also
saying which institute it expects X to belong to, so a cross-tenant read returns nothing
rather than someone else's document.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from app.core.db import Db, ids_in, iexact, ilike
from app.core.pagination import paginate
from app.modules.org.models import (
    AcademicSession,
    Branch,
    Class,
    ClassEnrollment,
    ClassFaculty,
    Institute,
)
from app.modules.rbac.catalog import DIRECT_INSTITUTE_CODE

# --------------------------------------------------------------------------- institutes


async def get_institute(db: Db, institute_id: uuid.UUID) -> Institute | None:
    return await db.get(Institute, institute_id)


async def get_direct_institute(db: Db) -> Institute | None:
    return await db.find_one(Institute, {"code": DIRECT_INSTITUTE_CODE})


async def institute_code_taken(db: Db, code: str) -> bool:
    return await db.exists(Institute, {"code": iexact(code)})


async def list_institutes(
    db: Db,
    *,
    visible_ids: frozenset[uuid.UUID] | None,
    search: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
    include_total: bool = True,
) -> tuple[Sequence[Institute], str | None, int]:
    """``visible_ids=None`` means platform staff, who see every institute."""
    match: dict[str, Any] = {}
    if visible_ids is not None:
        if not visible_ids:
            return [], None, 0
        match["_id"] = ids_in(visible_ids)
    if status:
        match["status"] = status
    if search:
        pattern = ilike(search)
        match["$or"] = [{"name": pattern}, {"code": pattern}]

    return await paginate(
        db, Institute, match, cursor=cursor, limit=limit, include_total=include_total
    )


# ----------------------------------------------------------------------------- branches


async def get_branch(
    db: Db, branch_id: uuid.UUID, *, institute_id: uuid.UUID | None = None
) -> Branch | None:
    match: dict[str, Any] = {"_id": branch_id}
    if institute_id is not None:
        match["institute_id"] = institute_id
    return await db.find_one(Branch, match)


async def branch_code_taken(db: Db, institute_id: uuid.UUID, code: str) -> bool:
    return await db.exists(Branch, {"institute_id": institute_id, "code": iexact(code)})


async def list_branches(
    db: Db,
    *,
    institute_id: uuid.UUID,
    branch_ids: frozenset[uuid.UUID] | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[Branch], str | None, int]:
    """``branch_ids`` narrows the result for a Branch Admin, who sees only their own."""
    match: dict[str, Any] = {"institute_id": institute_id}
    if branch_ids is not None:
        if not branch_ids:
            return [], None, 0
        match["_id"] = ids_in(branch_ids)
    if status:
        match["status"] = status
    return await paginate(db, Branch, match, cursor=cursor, limit=limit)


# --------------------------------------------------------------------- academic sessions


async def get_session(
    db: Db, session_id: uuid.UUID, *, institute_id: uuid.UUID | None = None
) -> AcademicSession | None:
    match: dict[str, Any] = {"_id": session_id}
    if institute_id is not None:
        match["institute_id"] = institute_id
    return await db.find_one(AcademicSession, match)


async def session_name_taken(db: Db, institute_id: uuid.UUID, name: str) -> bool:
    return await db.exists(AcademicSession, {"institute_id": institute_id, "name": iexact(name)})


async def list_sessions(
    db: Db,
    *,
    institute_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[AcademicSession], str | None, int]:
    return await paginate(
        db, AcademicSession, {"institute_id": institute_id}, cursor=cursor, limit=limit
    )


async def clear_current_session(
    db: Db, institute_id: uuid.UUID, *, keep: uuid.UUID | None = None
) -> None:
    """Only one session is current per institute.

    ``keep`` is the session being made current. It is excluded here rather than relying on
    its own save to put the flag back: a session that was *already* current has no change
    to save, and would otherwise be switched off by this very call.
    """
    match: dict[str, Any] = {"institute_id": institute_id, "is_current": True}
    if keep is not None:
        match["_id"] = {"$ne": keep}
    db.update_many(AcademicSession, match, {"is_current": False})


# ------------------------------------------------------------------------------ classes


async def get_class(
    db: Db, class_id: uuid.UUID, *, institute_id: uuid.UUID | None = None
) -> Class | None:
    match: dict[str, Any] = {"_id": class_id}
    if institute_id is not None:
        match["institute_id"] = institute_id
    return await db.find_one(Class, match)


async def class_code_taken(db: Db, branch_id: uuid.UUID, session_id: uuid.UUID, code: str) -> bool:
    return await db.exists(
        Class, {"branch_id": branch_id, "academic_session_id": session_id, "code": iexact(code)}
    )


async def list_classes(
    db: Db,
    *,
    institute_id: uuid.UUID,
    branch_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    class_ids: frozenset[uuid.UUID] | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[Class], str | None, int]:
    """``class_ids`` restricts to a faculty's assigned classes or a student's enrolments."""
    match: dict[str, Any] = {"institute_id": institute_id}
    if branch_id is not None:
        match["branch_id"] = branch_id
    if session_id is not None:
        match["academic_session_id"] = session_id
    if class_ids is not None:
        if not class_ids:
            return [], None, 0
        match["_id"] = ids_in(class_ids)
    if status:
        match["status"] = status
    return await paginate(db, Class, match, cursor=cursor, limit=limit)


async def current_session_id(db: Db, institute_id: uuid.UUID) -> uuid.UUID | None:
    rows = await db.raw(
        AcademicSession, {"institute_id": institute_id, "is_current": True}, {"_id": 1}
    )
    return rows[0]["_id"] if rows else None


# ------------------------------------------------------------- class faculty / enrolment


async def get_class_faculty(db: Db, class_id: uuid.UUID, user_id: uuid.UUID) -> ClassFaculty | None:
    return await db.find_one(ClassFaculty, {"class_id": class_id, "faculty_user_id": user_id})


async def list_class_faculty(db: Db, class_id: uuid.UUID) -> Sequence[ClassFaculty]:
    return await db.find(ClassFaculty, {"class_id": class_id})


async def get_enrollment(db: Db, class_id: uuid.UUID, user_id: uuid.UUID) -> ClassEnrollment | None:
    return await db.find_one(ClassEnrollment, {"class_id": class_id, "student_user_id": user_id})


async def list_enrollments(
    db: Db,
    *,
    class_id: uuid.UUID,
    status: str | None = "active",
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[ClassEnrollment], str | None, int]:
    match: dict[str, Any] = {"class_id": class_id}
    if status:
        match["status"] = status
    return await paginate(db, ClassEnrollment, match, cursor=cursor, limit=limit, descending=False)


async def sessions_overlapping(db: Db, institute_id: uuid.UUID, start: date, end: date) -> int:
    """Overlapping sessions are allowed (a coaching institute may run several), but the
    count is surfaced so the service can warn rather than silently accept a typo."""
    return await db.count(
        AcademicSession,
        {
            "institute_id": institute_id,
            "start_date": {"$lte": end.isoformat()},
            "end_date": {"$gte": start.isoformat()},
        },
    )


async def search_branches(
    db: Db,
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    branch_ids: frozenset[uuid.UUID] | None,
    term: str,
    limit: int,
) -> Sequence[Branch]:
    """Name or code match across every institute the caller can reach.

    ``None`` for either id set means "no restriction at this level" — platform staff, or a
    grant that covers whole institutes rather than named branches.
    """
    pattern = ilike(term)
    match: dict[str, Any] = {"$or": [{"name": pattern}, {"code": pattern}]}
    if institute_ids is not None:
        if not institute_ids:
            return []
        match["institute_id"] = ids_in(institute_ids)
    if branch_ids is not None:
        if not branch_ids:
            return []
        match["_id"] = ids_in(branch_ids)
    return await db.find(Branch, match, sort=[("name", 1)], limit=limit)


async def search_classes(
    db: Db,
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    branch_ids: frozenset[uuid.UUID] | None,
    class_ids: frozenset[uuid.UUID] | None,
    term: str,
    limit: int,
) -> Sequence[Class]:
    """Same shape as ``search_branches``; ``class_ids`` additionally pins a faculty member
    or student to the classes they are actually attached to."""
    pattern = ilike(term)
    match: dict[str, Any] = {"$or": [{"name": pattern}, {"code": pattern}]}
    if institute_ids is not None:
        if not institute_ids:
            return []
        match["institute_id"] = ids_in(institute_ids)
    if branch_ids is not None:
        if not branch_ids:
            return []
        match["branch_id"] = ids_in(branch_ids)
    if class_ids is not None:
        if not class_ids:
            return []
        match["_id"] = ids_in(class_ids)
    return await db.find(Class, match, sort=[("name", 1)], limit=limit)
