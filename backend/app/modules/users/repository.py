"""User queries.

The list endpoint is the one with real performance pressure: an institute admin filtering
thousands of users. It is written as a single statement with an EXISTS sub-query so the
scope filter runs inside PostgreSQL, rather than fetching ids and filtering in Python.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate
from app.modules.org.models import Branch, Institute
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.users.models import User, UserPreference


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_preferences(db: AsyncSession, user_id: uuid.UUID) -> UserPreference | None:
    return await db.get(UserPreference, user_id)


async def upsert_preferences(db: AsyncSession, user_id: uuid.UUID) -> UserPreference:
    existing = await db.get(UserPreference, user_id)
    if existing is not None:
        return existing
    created = UserPreference(user_id=user_id)
    db.add(created)
    await db.flush()
    return created


def visible_users_filter(
    *, institute_ids: frozenset[uuid.UUID] | None, branch_ids: frozenset[uuid.UUID] | None
):
    """The one definition of "which users may this caller see".

    EXISTS over live assignments, so a user is visible if *any* of their roles sits in the
    caller's scope. A correlated sub-query rather than a join, because a user holding three
    roles must not appear three times.

    Public because the dashboard counts the same people this filters, and it reached in and
    used the private name to do it. Two callers with one rule between them is fine; two
    callers where one is quietly depending on the other's internals is how the list and the
    count drift apart and nobody notices until the numbers disagree on screen.
    """
    conditions = [
        UserRoleAssignment.user_id == User.id,
        UserRoleAssignment.revoked_at.is_(None),
    ]
    if institute_ids is not None:
        conditions.append(UserRoleAssignment.institute_id.in_(institute_ids))
    if branch_ids is not None:
        # Branch only. This used to also admit assignments with no branch at all, on the
        # reasoning that an institute-wide role still sits inside the caller's institute —
        # but a caller reaching this line holds *no* institute-wide scope of their own, so
        # what it actually admitted was every institute-scoped member of staff, from every
        # other branch, to a Branch Admin who cannot act on any of them. Opening one of
        # those rows already returned "That user does not exist", because the per-row check
        # compares scopes properly; the list was the half that disagreed.
        #
        # Reading somebody's name and email address is as much a use of authority as
        # changing them, so the two now answer the same question.
        conditions.append(UserRoleAssignment.branch_id.in_(branch_ids))
    return exists().where(*conditions)


async def list_users(
    db: AsyncSession,
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    branch_ids: frozenset[uuid.UUID] | None = None,
    user_ids: frozenset[uuid.UUID] | None = None,
    search: str | None = None,
    status: str | None = None,
    role_key: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[User], str | None, int]:
    """``institute_ids=None`` means platform staff, who see every user."""
    stmt: Select[tuple[User]] = select(User).where(User.status != "deleted")

    if user_ids is not None:
        if not user_ids:
            return [], None, 0
        stmt = stmt.where(User.id.in_(user_ids))
    elif institute_ids is not None:
        if not institute_ids:
            return [], None, 0
        stmt = stmt.where(visible_users_filter(institute_ids=institute_ids, branch_ids=branch_ids))

    if status:
        stmt = stmt.where(User.status == status)

    if search:
        pattern = f"%{search.strip()}%"
        # ILIKE with a leading wildcard cannot use a btree index. Acceptable at this scale;
        # the fix when it stops being acceptable is a pg_trgm index, not a rewrite.
        stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))

    if role_key:
        stmt = stmt.where(
            exists().where(
                UserRoleAssignment.user_id == User.id,
                UserRoleAssignment.revoked_at.is_(None),
                UserRoleAssignment.role_id
                == select(Role.id).where(Role.key == role_key).scalar_subquery(),
            )
        )

    return await paginate(
        db, stmt, created_at_col=User.created_at, id_col=User.id, cursor=cursor, limit=limit
    )


RoleRow = tuple[str, str, int, uuid.UUID | None, uuid.UUID | None, str | None, str | None]


async def roles_for_users(
    db: AsyncSession, user_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[RoleRow]]:
    """Role assignments for a page of users, in one query.

    This is the N+1 that list endpoints usually fall into: loading roles per user. One
    IN-query for the whole page instead, grouped in Python.
    """
    if not user_ids:
        return {}

    stmt = (
        select(
            UserRoleAssignment.user_id,
            Role.key,
            Role.name,
            Role.rank,
            UserRoleAssignment.institute_id,
            UserRoleAssignment.branch_id,
            Institute.name,
            Branch.name,
        )
        .join(Role, Role.id == UserRoleAssignment.role_id)
        # Outer joins: a platform role has no institute, and an institute role no branch.
        .outerjoin(Institute, Institute.id == UserRoleAssignment.institute_id)
        .outerjoin(Branch, Branch.id == UserRoleAssignment.branch_id)
        .where(
            UserRoleAssignment.user_id.in_(user_ids),
            UserRoleAssignment.revoked_at.is_(None),
        )
    )
    grouped: dict[uuid.UUID, list[RoleRow]] = {}
    for user_id, key, name, rank, institute_id, branch_id, inst, branch in await db.execute(stmt):
        grouped.setdefault(user_id, []).append(
            (key, name, rank, institute_id, branch_id, inst, branch)
        )
    return grouped


async def email_taken(db: AsyncSession, email: str) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.strip().lower()).limit(1)
    return await db.scalar(stmt) is not None
