"""User queries.

The list endpoint is the one with real performance pressure: an institute admin filtering
thousands of users. The scope test runs in MongoDB as a ``$lookup`` over live role
assignments, rather than fetching ids and filtering in Python.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.db import Db, ids_in, ilike, utcnow
from app.core.pagination import paginate
from app.modules.org.models import Branch, Institute, Organisation
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.users.models import Guardian, User, UserPreference


async def get_user(db: Db, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_preferences(db: Db, user_id: uuid.UUID) -> UserPreference | None:
    return await db.find_one(UserPreference, {"user_id": user_id})


async def upsert_preferences(db: Db, user_id: uuid.UUID) -> UserPreference:
    """The user's preferences, created with defaults on first use.

    Written straight away rather than at commit: two first requests can race, and the
    loser must read the winner's document instead of failing its whole request on the
    unique index.
    """
    existing = await get_preferences(db, user_id)
    if existing is not None:
        return existing
    created = UserPreference(user_id=user_id)
    try:
        await created.insert()
    except DuplicateKeyError:
        winner = await get_preferences(db, user_id)
        assert winner is not None
        return winner
    return db.track(created)


#: Which people a caller may see, as the caller's own scopes describe it.
#:
#: ``None`` means platform staff, who see everybody. Otherwise one entry per institute the
#: caller can reach, mapped to the branches they hold there — or ``None`` for that
#: institute, meaning they hold it institute-wide and every branch in it is theirs.
VisibleScope = dict[uuid.UUID, frozenset[uuid.UUID] | None] | None


def visible_assignment_filter(scope: VisibleScope) -> dict[str, Any] | None:
    """The one definition of "which assignments put a user in this caller's view".

    A user is visible if *any* of their live roles sits in the caller's scope. Keyed per
    institute: somebody who is Institute Admin of one college and Branch Admin of one
    branch of another must not have the branch restriction lifted on the second college
    just because the first one is theirs entirely.

    ``None`` means no restriction (platform staff); an empty ``$or`` is never produced —
    a caller with no reachable institute gets a filter that matches nothing.
    """
    if scope is None:
        return {"revoked_at": None}
    per_institute: list[dict[str, Any]] = []
    for institute_id, branch_ids in scope.items():
        test: dict[str, Any] = {"institute_id": institute_id}
        if branch_ids is not None:
            # Branch only. Admitting assignments with no branch at all would hand a Branch
            # Admin every institute-scoped member of staff, from every other branch.
            test["branch_id"] = ids_in(branch_ids)
        per_institute.append(test)
    if not per_institute:
        return None
    return {"revoked_at": None, "$or": per_institute}


async def visible_user_ids(db: Db, scope: VisibleScope) -> list[uuid.UUID] | None:
    """User ids the caller may see, or ``None`` for "everybody" (platform staff).

    Public because the dashboard counts the same people the list shows. Two callers with
    one rule between them is how the list and the count stay in agreement.
    """
    if scope is None:
        return None
    match = visible_assignment_filter(scope)
    if match is None:
        return []
    return await db.distinct(UserRoleAssignment, "user_id", match)


async def list_users(
    db: Db,
    *,
    scope: VisibleScope,
    user_ids: frozenset[uuid.UUID] | None = None,
    search: str | None = None,
    status: str | None = None,
    role_key: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
    include_total: bool = True,
) -> tuple[Sequence[User], str | None, int]:
    """``scope=None`` means platform staff, who see every user."""
    conditions: list[dict[str, Any]] = [{"status": {"$ne": "deleted"}}]

    if user_ids is not None:
        if not user_ids:
            return [], None, 0
        conditions.append({"_id": ids_in(user_ids)})
    elif scope is not None:
        if not scope:
            return [], None, 0
        visible = await visible_user_ids(db, scope)
        if not visible:
            return [], None, 0
        conditions.append({"_id": ids_in(visible)})

    if status:
        conditions.append({"status": status})

    if search:
        pattern = ilike(search)
        conditions.append({"$or": [{"full_name": pattern}, {"email": pattern}]})

    if role_key:
        role = await db.find_one(Role, {"key": role_key})
        if role is None:
            return [], None, 0
        holders = await db.distinct(
            UserRoleAssignment, "user_id", {"role_id": role.id, "revoked_at": None}
        )
        conditions.append({"_id": ids_in(holders)})

    return await paginate(
        db,
        User,
        {"$and": conditions},
        cursor=cursor,
        limit=limit,
        include_total=include_total,
    )


RoleRow = tuple[
    str,  # role key
    str,  # role name
    int,  # rank
    uuid.UUID | None,  # organisation id
    uuid.UUID | None,  # institute id
    uuid.UUID | None,  # branch id
    str | None,  # organisation name
    str | None,  # institute name
    str | None,  # branch name
]


async def roles_for_users(db: Db, user_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[RoleRow]]:
    """Role assignments for a page of users, in a fixed number of queries.

    This is the N+1 that list endpoints usually fall into: loading roles per user. One
    query for the whole page's assignments, then one each for the roles, institutes and
    branches they name, joined in Python.
    """
    if not user_ids:
        return {}
    assignments = await db.raw(
        UserRoleAssignment,
        {"user_id": ids_in(user_ids), "revoked_at": None},
        {"user_id": 1, "role_id": 1, "organisation_id": 1, "institute_id": 1, "branch_id": 1},
    )
    if not assignments:
        return {}

    role_ids = {a["role_id"] for a in assignments}
    institute_ids = {a["institute_id"] for a in assignments if a.get("institute_id")}
    branch_ids = {a["branch_id"] for a in assignments if a.get("branch_id")}
    roles = {
        r["_id"]: r
        for r in await db.raw(Role, {"_id": ids_in(role_ids)}, {"key": 1, "name": 1, "rank": 1})
    }
    institutes = {
        r["_id"]: r["name"]
        for r in await db.raw(Institute, {"_id": ids_in(institute_ids)}, {"name": 1})
    }
    branches = {
        r["_id"]: r["name"] for r in await db.raw(Branch, {"_id": ids_in(branch_ids)}, {"name": 1})
    }
    organisation_ids = {a["organisation_id"] for a in assignments if a.get("organisation_id")}
    organisations = {
        r["_id"]: r["name"]
        for r in await db.raw(Organisation, {"_id": ids_in(organisation_ids)}, {"name": 1})
    }

    grouped: dict[uuid.UUID, list[RoleRow]] = {}
    for a in assignments:
        role = roles.get(a["role_id"])
        if role is None:
            continue
        organisation_id = a.get("organisation_id")
        institute_id, branch_id = a.get("institute_id"), a.get("branch_id")
        grouped.setdefault(a["user_id"], []).append(
            (
                role["key"],
                role["name"],
                role["rank"],
                organisation_id,
                institute_id,
                branch_id,
                organisations.get(organisation_id),
                institutes.get(institute_id),
                branches.get(branch_id),
            )
        )
    return grouped


async def email_taken(db: Db, email: str) -> bool:
    return await db.exists(User, {"email": email.strip().lower()})


async def get_user_by_email(db: Db, email: str) -> User | None:
    return await db.find_one(User, {"email": email.strip().lower()})


async def get_users(db: Db, user_ids: Sequence[uuid.UUID]) -> Sequence[User]:
    """A page of users by id, in one round trip rather than one per row."""
    if not user_ids:
        return []
    return await db.find(User, {"_id": ids_in(user_ids)})


# --------------------------------------------------------------------------- guardians


async def children_of(db: Db, parent_user_id: uuid.UUID) -> frozenset[uuid.UUID]:
    """The learners this adult is responsible for. Empty for everybody else."""
    found = await db.distinct(Guardian, "student_user_id", {"parent_user_id": parent_user_id})
    return frozenset(found)


async def guardians_of(db: Db, student_user_id: uuid.UUID) -> Sequence[Guardian]:
    return await db.find(
        Guardian,
        {"student_user_id": student_user_id},
        sort=[("is_primary", -1), ("created_at", 1)],
    )


async def guardians_for_parent(db: Db, parent_user_id: uuid.UUID) -> Sequence[Guardian]:
    return await db.find(Guardian, {"parent_user_id": parent_user_id}, sort=[("created_at", 1)])


async def guardian_link(
    db: Db, parent_user_id: uuid.UUID, student_user_id: uuid.UUID
) -> Guardian | None:
    return await db.find_one(
        Guardian, {"parent_user_id": parent_user_id, "student_user_id": student_user_id}
    )


async def mark_guardians_verified(db: Db, parent_user_id: uuid.UUID) -> int:
    """Record that this adult has proved they control their own address.

    Called once, when they complete password setup. Until then the link exists but the
    consent behind it is only asserted by whoever typed the row in.
    """
    match = {"parent_user_id": parent_user_id, "verified_at": None}
    pending = await db.count(Guardian, match)
    if pending:
        db.update_many(Guardian, match, {"verified_at": utcnow()})
    return pending
