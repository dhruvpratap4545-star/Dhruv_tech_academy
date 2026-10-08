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

from app.core.pagination import apply_keyset, split_page
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


def _scope_filter(
    *, institute_ids: frozenset[uuid.UUID] | None, branch_ids: frozenset[uuid.UUID] | None
):
    """EXISTS over live assignments, so a user is visible if *any* of their roles sits in
    the caller's scope. Correlated sub-query rather than a join: a user with three roles
    must not appear three times."""
    conditions = [
        UserRoleAssignment.user_id == User.id,
        UserRoleAssignment.revoked_at.is_(None),
    ]
    if institute_ids is not None:
        conditions.append(UserRoleAssignment.institute_id.in_(institute_ids))
    if branch_ids is not None:
        # Institute-wide roles have no branch; they are still visible to a branch admin
        # only when the caller's own institute scope covers them, which the institute
        # filter above has already established.
        conditions.append(
            or_(
                UserRoleAssignment.branch_id.in_(branch_ids),
                UserRoleAssignment.branch_id.is_(None),
            )
        )
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
) -> tuple[Sequence[User], str | None]:
    """``institute_ids=None`` means platform staff, who see every user."""
    stmt: Select[tuple[User]] = select(User).where(User.status != "deleted")

    if user_ids is not None:
        if not user_ids:
            return [], None
        stmt = stmt.where(User.id.in_(user_ids))
    elif institute_ids is not None:
        if not institute_ids:
            return [], None
        stmt = stmt.where(_scope_filter(institute_ids=institute_ids, branch_ids=branch_ids))

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

    stmt = apply_keyset(
        stmt, created_at_col=User.created_at, id_col=User.id, cursor=cursor, limit=limit
    )
    rows = (await db.execute(stmt)).scalars().all()
    return split_page(list(rows), limit)


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
