"""Queries for the organisation hierarchy.

Every function that reads institute-scoped data takes an ``institute_id`` and filters on it.
That is the tenant boundary: a caller cannot ask this layer for "class X" without also
saying which institute it expects X to belong to, so a cross-tenant read returns nothing
rather than someone else's row.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import like_pattern, paginate
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


async def get_institute(db: AsyncSession, institute_id: uuid.UUID) -> Institute | None:
    return await db.get(Institute, institute_id)


async def get_direct_institute(db: AsyncSession) -> Institute | None:
    return await db.scalar(select(Institute).where(Institute.code == DIRECT_INSTITUTE_CODE))


async def institute_code_taken(db: AsyncSession, code: str) -> bool:
    stmt = select(Institute.id).where(func.upper(Institute.code) == code.upper()).limit(1)
    return await db.scalar(stmt) is not None


async def list_institutes(
    db: AsyncSession,
    *,
    visible_ids: frozenset[uuid.UUID] | None,
    search: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
    include_total: bool = True,
) -> tuple[Sequence[Institute], str | None, int]:
    """``visible_ids=None`` means platform staff, who see every institute."""
    stmt: Select[tuple[Institute]] = select(Institute)
    if visible_ids is not None:
        if not visible_ids:
            return [], None, 0
        stmt = stmt.where(Institute.id.in_(visible_ids))
    if status:
        stmt = stmt.where(Institute.status == status)
    if search:
        pattern = like_pattern(search)
        stmt = stmt.where(Institute.name.ilike(pattern) | Institute.code.ilike(pattern))

    return await paginate(
        db,
        stmt,
        created_at_col=Institute.created_at,
        id_col=Institute.id,
        cursor=cursor,
        limit=limit,
        include_total=include_total,
    )


# ----------------------------------------------------------------------------- branches


async def get_branch(
    db: AsyncSession, branch_id: uuid.UUID, *, institute_id: uuid.UUID | None = None
) -> Branch | None:
    stmt = select(Branch).where(Branch.id == branch_id)
    if institute_id is not None:
        stmt = stmt.where(Branch.institute_id == institute_id)
    return await db.scalar(stmt)


async def branch_code_taken(db: AsyncSession, institute_id: uuid.UUID, code: str) -> bool:
    stmt = (
        select(Branch.id)
        .where(Branch.institute_id == institute_id, func.upper(Branch.code) == code.upper())
        .limit(1)
    )
    return await db.scalar(stmt) is not None


async def list_branches(
    db: AsyncSession,
    *,
    institute_id: uuid.UUID,
    branch_ids: frozenset[uuid.UUID] | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[Branch], str | None, int]:
    """``branch_ids`` narrows the result for a Branch Admin, who sees only their own."""
    stmt = select(Branch).where(Branch.institute_id == institute_id)
    if branch_ids is not None:
        if not branch_ids:
            return [], None, 0
        stmt = stmt.where(Branch.id.in_(branch_ids))
    if status:
        stmt = stmt.where(Branch.status == status)

    return await paginate(
        db, stmt, created_at_col=Branch.created_at, id_col=Branch.id, cursor=cursor, limit=limit
    )


# --------------------------------------------------------------------- academic sessions


async def get_session(
    db: AsyncSession, session_id: uuid.UUID, *, institute_id: uuid.UUID | None = None
) -> AcademicSession | None:
    stmt = select(AcademicSession).where(AcademicSession.id == session_id)
    if institute_id is not None:
        stmt = stmt.where(AcademicSession.institute_id == institute_id)
    return await db.scalar(stmt)


async def session_name_taken(db: AsyncSession, institute_id: uuid.UUID, name: str) -> bool:
    stmt = (
        select(AcademicSession.id)
        .where(
            AcademicSession.institute_id == institute_id,
            func.lower(AcademicSession.name) == name.strip().lower(),
        )
        .limit(1)
    )
    return await db.scalar(stmt) is not None


async def list_sessions(
    db: AsyncSession,
    *,
    institute_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[AcademicSession], str | None, int]:
    return await paginate(
        db,
        select(AcademicSession).where(AcademicSession.institute_id == institute_id),
        created_at_col=AcademicSession.created_at,
        id_col=AcademicSession.id,
        cursor=cursor,
        limit=limit,
    )


async def clear_current_session(db: AsyncSession, institute_id: uuid.UUID) -> None:
    """Only one session is current per institute."""
    from sqlalchemy import update

    await db.execute(
        update(AcademicSession)
        .where(
            AcademicSession.institute_id == institute_id,
            AcademicSession.is_current.is_(True),
        )
        .values(is_current=False)
    )


# ------------------------------------------------------------------------------ classes


async def get_class(
    db: AsyncSession, class_id: uuid.UUID, *, institute_id: uuid.UUID | None = None
) -> Class | None:
    stmt = select(Class).where(Class.id == class_id)
    if institute_id is not None:
        stmt = stmt.where(Class.institute_id == institute_id)
    return await db.scalar(stmt)


async def class_code_taken(
    db: AsyncSession, branch_id: uuid.UUID, session_id: uuid.UUID, code: str
) -> bool:
    stmt = (
        select(Class.id)
        .where(
            Class.branch_id == branch_id,
            Class.academic_session_id == session_id,
            func.upper(Class.code) == code.upper(),
        )
        .limit(1)
    )
    return await db.scalar(stmt) is not None


async def list_classes(
    db: AsyncSession,
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
    stmt = select(Class).where(Class.institute_id == institute_id)
    if branch_id is not None:
        stmt = stmt.where(Class.branch_id == branch_id)
    if session_id is not None:
        stmt = stmt.where(Class.academic_session_id == session_id)
    if class_ids is not None:
        if not class_ids:
            return [], None, 0
        stmt = stmt.where(Class.id.in_(class_ids))
    if status:
        stmt = stmt.where(Class.status == status)

    return await paginate(
        db, stmt, created_at_col=Class.created_at, id_col=Class.id, cursor=cursor, limit=limit
    )


async def current_session_id(db: AsyncSession, institute_id: uuid.UUID) -> uuid.UUID | None:
    stmt = select(AcademicSession.id).where(
        AcademicSession.institute_id == institute_id,
        AcademicSession.is_current.is_(True),
    )
    return await db.scalar(stmt)


# ------------------------------------------------------------- class faculty / enrolment


async def get_class_faculty(
    db: AsyncSession, class_id: uuid.UUID, user_id: uuid.UUID
) -> ClassFaculty | None:
    return await db.scalar(
        select(ClassFaculty).where(
            ClassFaculty.class_id == class_id, ClassFaculty.faculty_user_id == user_id
        )
    )


async def list_class_faculty(db: AsyncSession, class_id: uuid.UUID) -> Sequence[ClassFaculty]:
    result = await db.execute(select(ClassFaculty).where(ClassFaculty.class_id == class_id))
    return result.scalars().all()


async def get_enrollment(
    db: AsyncSession, class_id: uuid.UUID, user_id: uuid.UUID
) -> ClassEnrollment | None:
    return await db.scalar(
        select(ClassEnrollment).where(
            ClassEnrollment.class_id == class_id,
            ClassEnrollment.student_user_id == user_id,
        )
    )


async def list_enrollments(
    db: AsyncSession,
    *,
    class_id: uuid.UUID,
    status: str | None = "active",
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[ClassEnrollment], str | None, int]:
    stmt = select(ClassEnrollment).where(ClassEnrollment.class_id == class_id)
    if status:
        stmt = stmt.where(ClassEnrollment.status == status)
    return await paginate(
        db,
        stmt,
        created_at_col=ClassEnrollment.created_at,
        id_col=ClassEnrollment.id,
        cursor=cursor,
        limit=limit,
        descending=False,
    )


async def sessions_overlapping(
    db: AsyncSession, institute_id: uuid.UUID, start: date, end: date
) -> int:
    """Overlapping sessions are allowed (a coaching institute may run several), but the
    count is surfaced so the service can warn rather than silently accept a typo."""
    stmt = select(func.count()).where(
        AcademicSession.institute_id == institute_id,
        AcademicSession.start_date <= end,
        AcademicSession.end_date >= start,
    )
    return int(await db.scalar(stmt) or 0)


async def search_branches(
    db: AsyncSession,
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
    pattern = like_pattern(term)
    stmt = select(Branch).where(or_(Branch.name.ilike(pattern), Branch.code.ilike(pattern)))
    if institute_ids is not None:
        if not institute_ids:
            return []
        stmt = stmt.where(Branch.institute_id.in_(institute_ids))
    if branch_ids is not None:
        if not branch_ids:
            return []
        stmt = stmt.where(Branch.id.in_(branch_ids))
    stmt = stmt.order_by(Branch.name).limit(limit)
    return (await db.execute(stmt)).scalars().all()


async def search_classes(
    db: AsyncSession,
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    branch_ids: frozenset[uuid.UUID] | None,
    class_ids: frozenset[uuid.UUID] | None,
    term: str,
    limit: int,
) -> Sequence[Class]:
    """Same shape as ``search_branches``; ``class_ids`` additionally pins a faculty member
    or student to the classes they are actually attached to."""
    pattern = like_pattern(term)
    stmt = select(Class).where(or_(Class.name.ilike(pattern), Class.code.ilike(pattern)))
    if institute_ids is not None:
        if not institute_ids:
            return []
        stmt = stmt.where(Class.institute_id.in_(institute_ids))
    if branch_ids is not None:
        if not branch_ids:
            return []
        stmt = stmt.where(Class.branch_id.in_(branch_ids))
    if class_ids is not None:
        if not class_ids:
            return []
        stmt = stmt.where(Class.id.in_(class_ids))
    stmt = stmt.order_by(Class.name).limit(limit)
    return (await db.execute(stmt)).scalars().all()
