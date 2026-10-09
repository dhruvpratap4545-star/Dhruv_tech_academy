"""One search box over people, institutes, branches and classes.

The rule that shapes this file: **search must never be a way around authorization.** A
global search box is the classic place where tenant isolation quietly fails, because it is
written as "query everything, then filter", and the filter is forgotten or is subtly wider
than the one the list endpoints use.

So nothing here queries without a scope. Users and institutes reuse the very same service
functions the list endpoints call, which means their scoping cannot drift from the lists;
branches and classes use dedicated queries that take the caller's usable grant scopes
(explicit denials included) and refuse to run at all when those are empty.

Each group is also independently permission-gated: someone without ``class:read`` gets no
class group, rather than an empty one, because an empty group tells you a thing exists to
be empty.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org import repository as org_repo
from app.modules.org import service as org
from app.modules.rbac.catalog import FACULTY, STUDENT
from app.modules.rbac.context import AuthContext
from app.modules.rbac.service import Authorized
from app.modules.search import schemas
from app.modules.users import service as users

PER_GROUP = 5


def _guard(db: AsyncSession, context: AuthContext, permission: str) -> Authorized | None:
    """An ``Authorized`` for a permission the caller actually holds, else ``None``.

    Built by hand rather than through ``require_permission`` because search asks about
    four permissions at once and must degrade group by group, not 403 the whole request.
    """
    return Authorized(db, context, permission) if context.holds(permission) else None


async def _scope_sets(
    guard: Authorized, institute_ids: frozenset[uuid.UUID] | None
) -> tuple[frozenset[uuid.UUID] | None, frozenset[uuid.UUID] | None]:
    """Turn the caller's usable grants into (institute ids, branch ids) filters.

    ``None`` means "unrestricted at this level". A branch filter is only produced when
    *every* grant is branch-scoped — one institute-wide grant makes branch filtering wrong,
    because it legitimately covers branches the caller holds no named grant on.
    """
    scopes = guard.usable_scopes()
    if any(s.institute_id is None for s in scopes):
        return None, None
    institutes = frozenset(s.institute_id for s in scopes if s.institute_id)
    if institute_ids is not None:
        institutes &= institute_ids
    institute_wide = any(s.institute_id and s.branch_id is None for s in scopes)
    branches = None if institute_wide else frozenset(s.branch_id for s in scopes if s.branch_id)
    return institutes, branches


async def search(db: AsyncSession, *, context: AuthContext, term: str) -> schemas.SearchResults:
    term = term.strip()
    groups: list[schemas.SearchGroup] = []
    if len(term) < 2:
        # One character matches most of the database and helps nobody.
        return schemas.SearchResults(query=term, groups=groups)

    groups.extend(await _people(db, context, term))
    groups.extend(await _institutes(db, context, term))
    groups.extend(await _branches(db, context, term))
    groups.extend(await _classes(db, context, term))
    return schemas.SearchResults(query=term, groups=[g for g in groups if g.items])


async def _people(db: AsyncSession, context: AuthContext, term: str) -> list[schemas.SearchGroup]:
    guard = _guard(db, context, "user:read")
    if guard is None:
        return []
    # No total: global search fires on every keystroke and displays no count.
    rows, _, _ = await users.list_users(
        db,
        guard=guard,
        search=term,
        status=None,
        role_key=None,
        institute_id=None,
        cursor=None,
        limit=PER_GROUP,
        include_total=False,
    )
    return [
        schemas.SearchGroup(
            kind="user",
            label="People",
            items=[
                schemas.SearchHit(
                    id=row.id, title=row.full_name, subtitle=row.email, href=f"/users?q={row.email}"
                )
                for row in rows
            ],
        )
    ]


async def _institutes(
    db: AsyncSession, context: AuthContext, term: str
) -> list[schemas.SearchGroup]:
    guard = _guard(db, context, "institute:read")
    if guard is None:
        return []
    rows, _, _ = await org.list_institutes(
        db,
        guard=guard,
        search=term,
        status=None,
        cursor=None,
        limit=PER_GROUP,
        include_total=False,
    )
    return [
        schemas.SearchGroup(
            kind="institute",
            label="Institutes",
            items=[
                schemas.SearchHit(
                    id=row.id,
                    title=row.name,
                    subtitle=row.code,
                    href=f"/institutes?institute={row.id}",
                )
                for row in rows
            ],
        )
    ]


async def _branches(db: AsyncSession, context: AuthContext, term: str) -> list[schemas.SearchGroup]:
    guard = _guard(db, context, "branch:read")
    if guard is None:
        return []
    institutes, branches = await _scope_sets(guard, None)
    rows = await org_repo.search_branches(
        db, institute_ids=institutes, branch_ids=branches, term=term, limit=PER_GROUP
    )
    return [
        schemas.SearchGroup(
            kind="branch",
            label="Branches",
            items=[
                schemas.SearchHit(
                    id=row.id,
                    title=row.name,
                    subtitle=row.code,
                    href=f"/institutes?institute={row.institute_id}&branch={row.id}",
                )
                for row in rows
            ],
        )
    ]


async def _classes(db: AsyncSession, context: AuthContext, term: str) -> list[schemas.SearchGroup]:
    guard = _guard(db, context, "class:read")
    if guard is None:
        return []
    from app.modules.rbac import repository as rbac_repo

    institutes, branches = await _scope_sets(guard, None)

    # Faculty and students are pinned to the classes they are actually attached to —
    # the same rule ``list_classes`` applies, for the same reason.
    role_keys = {a.role_key for a in context.assignments}
    class_ids: frozenset[uuid.UUID] | None = None
    if role_keys and role_keys <= {FACULTY, STUDENT}:
        class_ids = frozenset()
        if FACULTY in role_keys:
            class_ids |= await rbac_repo.faculty_class_ids(db, context.user_id)
        if STUDENT in role_keys:
            class_ids |= await rbac_repo.student_class_ids(db, context.user_id)

    rows = await org_repo.search_classes(
        db,
        institute_ids=institutes,
        branch_ids=branches,
        class_ids=class_ids,
        term=term,
        limit=PER_GROUP,
    )
    return [
        schemas.SearchGroup(
            kind="class",
            label="Classes",
            items=[
                schemas.SearchHit(
                    id=row.id,
                    title=row.name,
                    subtitle=row.code,
                    href=f"/institutes?institute={row.institute_id}&branch={row.branch_id}",
                )
                for row in rows
            ],
        )
    ]
