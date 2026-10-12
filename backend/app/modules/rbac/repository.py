"""Queries behind the authorization engine. No business rules live here.

MongoDB has no joins, so the "three joins rather than three round trips" of the SQL version
become a fixed number of small ``$in`` lookups joined in Python. Each is bounded by what one
person holds — a handful of roles, tens of permissions — so the cost stays flat however big
the platform grows.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from app.core.db import Db, ids_in, utcnow
from app.modules.org.models import Class, ClassEnrollment, ClassFaculty
from app.modules.rbac.models import (
    InstituteModule,
    InstituteRolePermission,
    Module,
    Permission,
    Role,
    RolePermission,
    UserPermissionGrant,
    UserRoleAssignment,
)

GrantRow = tuple[str, str, int, uuid.UUID | None, uuid.UUID | None, str]
PersonalGrantRow = tuple[str, str, uuid.UUID | None, uuid.UUID | None]


def _live(user_id: uuid.UUID) -> dict[str, Any]:
    return {"user_id": user_id, "revoked_at": None}


async def _permission_keys(db: Db, permission_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not permission_ids:
        return {}
    rows = await db.raw(Permission, {"_id": ids_in(permission_ids)}, {"key": 1})
    return {r["_id"]: r["key"] for r in rows}


async def load_grants(db: Db, user_id: uuid.UUID) -> Sequence[GrantRow]:
    """Every (role, scope, permission) the user currently holds, after their institute's
    own adjustments to those roles have been applied.

    Applying the difference here, rather than in the engine, is deliberate: every caller
    above this line then sees one flat truth about what the user may do, and no call site
    has to remember that institute customisation exists.
    """
    assignments = await db.raw(
        UserRoleAssignment, _live(user_id), {"role_id": 1, "institute_id": 1, "branch_id": 1}
    )
    if not assignments:
        return []

    role_ids = {a["role_id"] for a in assignments}
    roles = {
        r["_id"]: r
        for r in await db.raw(
            Role,
            {"_id": ids_in(role_ids), "is_active": True},
            {"key": 1, "name": 1, "rank": 1},
        )
    }
    links = await db.raw(
        RolePermission, {"role_id": ids_in(roles)}, {"role_id": 1, "permission_id": 1}
    )
    keys = await _permission_keys(db, {link["permission_id"] for link in links})
    by_role: dict[uuid.UUID, list[str]] = {}
    for link in links:
        if link["permission_id"] in keys:
            by_role.setdefault(link["role_id"], []).append(keys[link["permission_id"]])

    # One row per (assignment, permission). A role that currently grants nothing still
    # yields one row with a null permission, naming the assignment and its scope: an
    # institute that adds a permission to an empty role needs that assignment for the
    # addition to attach to. `_apply_role_overrides` discards those rows once read.
    rows: list[Any] = []
    for a in assignments:
        role = roles.get(a["role_id"])
        if role is None:
            continue
        head = (role["key"], role["name"], role["rank"], a.get("institute_id"), a.get("branch_id"))
        granted = by_role.get(role["_id"], [])
        if granted:
            rows.extend((*head, key) for key in granted)
        else:
            rows.append((*head, None))

    overrides = await _role_overrides_for_user(db, assignments, roles)
    if not overrides:
        return [row for row in rows if row[5] is not None]
    return _apply_role_overrides(rows, overrides)


# (role_key, role_name, rank, institute_id, branch_id) -> the assignment a grant came from
_Assignment = tuple[str, str, int, uuid.UUID | None, uuid.UUID | None]


async def _role_overrides_for_user(
    db: Db, assignments: list[dict[str, Any]], roles: dict[uuid.UUID, dict[str, Any]]
) -> dict[tuple[uuid.UUID, str], dict[str, str]]:
    """(institute id, role key) -> {permission key: effect}, for this user's institutes."""
    institute_ids = {a["institute_id"] for a in assignments if a.get("institute_id")}
    if not institute_ids:
        return {}
    rows = await db.raw(
        InstituteRolePermission,
        {
            "institute_id": ids_in(institute_ids),
            "role_id": ids_in({a["role_id"] for a in assignments}),
        },
        {"institute_id": 1, "role_id": 1, "permission_id": 1, "effect": 1},
    )
    if not rows:
        return {}
    keys = await _permission_keys(db, {r["permission_id"] for r in rows})
    found: dict[tuple[uuid.UUID, str], dict[str, str]] = {}
    for r in rows:
        role = roles.get(r["role_id"])
        if role is None or r["permission_id"] not in keys:
            continue
        found.setdefault((r["institute_id"], role["key"]), {})[keys[r["permission_id"]]] = r[
            "effect"
        ]
    return found


async def role_ids_by_key(db: Db) -> dict[str, uuid.UUID]:
    return {r["key"]: r["_id"] for r in await db.raw(Role, {}, {"key": 1})}


def _apply_role_overrides(
    rows: Sequence[Any],
    overrides: dict[tuple[uuid.UUID, str], dict[str, str]],
) -> list[GrantRow]:
    """Remove what the institute denied for a role, add what it allowed.

    Keyed on (institute, role) so one institute's adjustment cannot reach a person's roles
    in another — which is the whole reason it hangs off the institute and not the role.
    """
    kept: list[GrantRow] = []
    seen: set[GrantRow] = set()
    # Every distinct assignment, so an "allow" can be expanded against the right scope.
    assignments: set[_Assignment] = set()

    for row in rows:
        role_key, role_name, rank, institute_id, branch_id, permission_key = row
        assignments.add((role_key, role_name, rank, institute_id, branch_id))
        if permission_key is None:
            # The placeholder for a role that grants nothing. Its only job was to put the
            # assignment above into `assignments`.
            continue
        blocked_here = (
            institute_id is not None
            and overrides.get((institute_id, role_key), {}).get(permission_key) == "deny"
        )
        if not blocked_here:
            kept.append(row)
            seen.add(row)

    for role_key, role_name, rank, institute_id, branch_id in assignments:
        if institute_id is None:
            continue
        for permission_key, effect in overrides.get((institute_id, role_key), {}).items():
            if effect != "allow":
                continue
            added: GrantRow = (role_key, role_name, rank, institute_id, branch_id, permission_key)
            # A set rather than scanning `kept`: someone holding several roles across
            # several branches turns that scan into the slowest part of every request.
            if added not in seen:
                kept.append(added)
                seen.add(added)

    return kept


async def load_personal_grants(db: Db, user_id: uuid.UUID) -> Sequence[PersonalGrantRow]:
    """The per-user allow/deny layer, as (permission, effect, institute, branch).

    Expiry is evaluated at query time: a grant that lapsed while a context sat in the cache
    must not come back to life on the next rebuild.
    """
    grants = await db.raw(
        UserPermissionGrant,
        {
            **_live(user_id),
            "$or": [{"expires_at": None}, {"expires_at": {"$gt": utcnow()}}],
        },
        {"permission_id": 1, "effect": 1, "institute_id": 1, "branch_id": 1},
    )
    keys = await _permission_keys(db, {g["permission_id"] for g in grants})
    return [
        (keys[g["permission_id"]], g["effect"], g.get("institute_id"), g.get("branch_id"))
        for g in grants
        if g["permission_id"] in keys
    ]


async def load_permission_modules(db: Db) -> dict[str, str]:
    """permission key -> module key. Changes only when the seed runs, so the caller
    holds this for the life of the process."""
    return {
        r["key"]: r["module_key"] for r in await db.raw(Permission, {}, {"key": 1, "module_key": 1})
    }


async def load_core_modules(db: Db) -> frozenset[str]:
    return frozenset(r["key"] for r in await db.raw(Module, {"is_core": True}, {"key": 1}))


async def is_module_enabled(db: Db, institute_id: uuid.UUID, module_key: str) -> bool:
    """PRD §5.2 step 5. An absent document means not enabled."""
    return await db.exists(
        InstituteModule,
        {
            "institute_id": institute_id,
            "module_key": module_key,
            "enabled": True,
            # valid_till is stored as an ISO date string, which compares correctly as text.
            "$or": [{"valid_till": None}, {"valid_till": {"$gte": _today().isoformat()}}],
        },
    )


def _today():  # pragma: no cover - trivial, kept separate so tests can freeze it
    return utcnow().date()


async def faculty_teaches_class(db: Db, user_id: uuid.UUID, class_id: uuid.UUID) -> bool:
    """PRD §5.2 step 4 for Faculty. Covered by the (faculty_user_id, class_id) index."""
    return await db.exists(ClassFaculty, {"faculty_user_id": user_id, "class_id": class_id})


async def student_enrolled_in_class(db: Db, user_id: uuid.UUID, class_id: uuid.UUID) -> bool:
    """PRD §5.2 step 4 for Student. Only an active enrolment counts."""
    return await db.exists(
        ClassEnrollment, {"student_user_id": user_id, "class_id": class_id, "status": "active"}
    )


async def faculty_class_ids(db: Db, user_id: uuid.UUID) -> frozenset[uuid.UUID]:
    """Classes a faculty member teaches. Used to scope list endpoints rather than
    filtering in Python after loading everything."""
    return frozenset(await db.distinct(ClassFaculty, "class_id", {"faculty_user_id": user_id}))


async def student_class_ids(db: Db, user_id: uuid.UUID) -> frozenset[uuid.UUID]:
    return frozenset(
        await db.distinct(
            ClassEnrollment, "class_id", {"student_user_id": user_id, "status": "active"}
        )
    )


async def class_scope(db: Db, class_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID] | None:
    """(institute_id, branch_id) for a class, so a class target can be resolved to a scope."""
    rows = await db.raw(Class, {"_id": class_id}, {"institute_id": 1, "branch_id": 1})
    return (rows[0]["institute_id"], rows[0]["branch_id"]) if rows else None


async def get_role_by_key(db: Db, key: str) -> Role | None:
    return await db.find_one(Role, {"key": key})


async def list_roles(db: Db, *, include_inactive: bool = False) -> Sequence[Role]:
    return await db.find(Role, {} if include_inactive else {"is_active": True}, sort=[("rank", -1)])


async def live_assignments_for_user(db: Db, user_id: uuid.UUID) -> Sequence[UserRoleAssignment]:
    return await db.find(UserRoleAssignment, _live(user_id))


async def find_assignment(
    db: Db,
    *,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    institute_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
) -> UserRoleAssignment | None:
    """Exact-scope match, so re-granting the same role at the same scope is idempotent."""
    return await db.find_one(
        UserRoleAssignment,
        {
            **_live(user_id),
            "role_id": role_id,
            "institute_id": institute_id,
            "branch_id": branch_id,
        },
    )


async def count_usable_role_holders(db: Db, role_id: uuid.UUID) -> int:
    """How many people hold this role *and can actually sign in*.

    Guards "at least one Super Admin must always exist" (PRD §3). Counting bare assignments
    is not enough: an invited Super Admin who has never set a password holds the role but
    cannot log in, so treating them as the survivor lets the last real administrator revoke
    their own access and lock everyone out of the platform permanently.
    """
    from app.modules.users.models import User

    holders = await db.distinct(
        UserRoleAssignment, "user_id", {"role_id": role_id, "revoked_at": None}
    )
    if not holders:
        return 0
    return await db.count(
        User, {"_id": ids_in(holders), "status": "active", "password_hash": {"$ne": None}}
    )


# ------------------------------------------------------------------ role & grant admin


async def roles_visible_to(
    db: Db,
    institute_ids: frozenset[uuid.UUID] | None,
    *,
    include_retired: bool = False,
) -> Sequence[Role]:
    """Built-in roles, plus the custom roles of the institutes the caller can see.

    ``None`` means platform staff: every role, custom ones included. Everyone else sees the
    built-ins (they need to, to understand what a role means) and only their own
    institute's inventions — another institute's role names are that institute's business.

    Retired roles are left out. A permission matrix that still lists one invites somebody
    to tick a box on a role nobody can be given.
    """
    match: dict[str, Any] = {}
    if not include_retired:
        match["is_active"] = True
    if institute_ids is not None:
        match["$or"] = [{"institute_id": None}, {"institute_id": ids_in(institute_ids)}]
    return await db.find(Role, match, sort=[("rank", -1), ("name", 1)])


async def permission_keys_by_role(db: Db) -> dict[uuid.UUID, list[str]]:
    """role id -> permission keys, for every role, in two queries."""
    links = await db.raw(RolePermission, {}, {"role_id": 1, "permission_id": 1})
    keys = {r["_id"]: r["key"] for r in await db.raw(Permission, {}, {"key": 1})}
    grouped: dict[uuid.UUID, list[str]] = {}
    for link in links:
        if link["permission_id"] in keys:
            grouped.setdefault(link["role_id"], []).append(keys[link["permission_id"]])
    for permissions in grouped.values():
        permissions.sort()
    return grouped


async def holder_counts(db: Db) -> dict[uuid.UUID, int]:
    """role id -> how many people currently hold it."""
    rows = await db.aggregate(
        UserRoleAssignment,
        [{"$match": {"revoked_at": None}}, {"$group": {"_id": "$role_id", "n": {"$sum": 1}}}],
    )
    return {r["_id"]: int(r["n"]) for r in rows}


async def get_role(db: Db, role_id: uuid.UUID) -> Role | None:
    return await db.get(Role, role_id)


async def role_by_key(db: Db, key: str) -> Role | None:
    """Archived roles included — a retired role still owns its key."""
    return await db.find_one(Role, {"key": key})


async def permissions_by_keys(db: Db, keys: Sequence[str]) -> Sequence[Permission]:
    if not keys:
        return []
    return await db.find(Permission, {"key": ids_in(keys)})


async def replace_role_permissions(
    db: Db, *, role_id: uuid.UUID, permission_ids: Sequence[uuid.UUID]
) -> None:
    """Set a role's permissions to exactly this list.

    Delete-then-insert rather than a diff: the set is tens of documents, the operation is
    rare, and a diff would be more code to get subtly wrong for no measurable gain. Both
    are queued, so they land together at commit, in this order.
    """
    db.delete_many(RolePermission, {"role_id": role_id})
    db.add_all(
        RolePermission(role_id=role_id, permission_id=permission_id)
        for permission_id in dict.fromkeys(permission_ids)
    )


async def live_grants_for_user(
    db: Db, user_id: uuid.UUID
) -> Sequence[tuple[UserPermissionGrant, str, str | None]]:
    """Every grant still on the record for a user, with its permission key and granter.

    Expired grants are included — they are history an administrator reviewing access needs
    to see, and the engine ignores them separately (``load_personal_grants``).
    """
    from app.modules.users.models import User

    grants = await db.find(UserPermissionGrant, _live(user_id), sort=[("created_at", -1)])
    keys = await _permission_keys(db, {g.permission_id for g in grants})
    granter_ids = {g.granted_by for g in grants if g.granted_by}
    names = (
        {
            r["_id"]: r["full_name"]
            for r in await db.raw(User, {"_id": ids_in(granter_ids)}, {"full_name": 1})
        }
        if granter_ids
        else {}
    )
    return [
        (g, keys[g.permission_id], names.get(g.granted_by) if g.granted_by else None)
        for g in grants
        if g.permission_id in keys
    ]


async def find_live_grant(
    db: Db,
    *,
    user_id: uuid.UUID,
    permission_id: uuid.UUID,
    institute_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
) -> UserPermissionGrant | None:
    """Exact-scope match, so re-granting the same thing updates instead of stacking."""
    return await db.find_one(
        UserPermissionGrant,
        {
            **_live(user_id),
            "permission_id": permission_id,
            "institute_id": institute_id,
            "branch_id": branch_id,
        },
    )


async def get_grant(db: Db, grant_id: uuid.UUID) -> UserPermissionGrant | None:
    return await db.get(UserPermissionGrant, grant_id)


async def institute_overrides(db: Db, institute_id: uuid.UUID) -> dict[uuid.UUID, dict[str, str]]:
    """role id -> {permission key: effect} for one institute, for the roles screen."""
    rows = await db.raw(
        InstituteRolePermission,
        {"institute_id": institute_id},
        {"role_id": 1, "permission_id": 1, "effect": 1},
    )
    keys = await _permission_keys(db, {r["permission_id"] for r in rows})
    grouped: dict[uuid.UUID, dict[str, str]] = {}
    for r in rows:
        if r["permission_id"] in keys:
            grouped.setdefault(r["role_id"], {})[keys[r["permission_id"]]] = r["effect"]
    return grouped


async def customised_role_ids(db: Db) -> set[uuid.UUID]:
    """Roles that at least one institute has adjusted, so the catalogue can say so."""
    return set(await db.distinct(InstituteRolePermission, "role_id", {}))


async def replace_institute_overrides(
    db: Db,
    *,
    institute_id: uuid.UUID,
    role_id: uuid.UUID,
    effects: dict[uuid.UUID, str],
    created_by: uuid.UUID | None,
) -> None:
    """Set one institute's adjustments to one role to exactly ``effects``.

    An empty ``effects`` therefore means "this institute uses the role exactly as
    defined", and the documents disappear rather than lingering as a no-op.
    """
    db.delete_many(InstituteRolePermission, {"institute_id": institute_id, "role_id": role_id})
    db.add_all(
        InstituteRolePermission(
            institute_id=institute_id,
            role_id=role_id,
            permission_id=permission_id,
            effect=effect,
            created_by=created_by,
        )
        for permission_id, effect in effects.items()
    )


async def user_ids_holding_role(db: Db, role_id: uuid.UUID) -> set[uuid.UUID]:
    """Everyone currently holding a role, anywhere."""
    return set(
        await db.distinct(UserRoleAssignment, "user_id", {"role_id": role_id, "revoked_at": None})
    )


async def user_ids_holding_role_in(
    db: Db, *, role_id: uuid.UUID, institute_id: uuid.UUID
) -> set[uuid.UUID]:
    """Everyone whose cached permissions this role change invalidates."""
    return set(
        await db.distinct(
            UserRoleAssignment,
            "user_id",
            {"role_id": role_id, "institute_id": institute_id, "revoked_at": None},
        )
    )


async def ever_assigned_count(db: Db, role_id: uuid.UUID) -> int:
    """How many assignments of this role have ever existed, revoked ones included.

    `holder_counts` answers "who holds it now", which is the question for "can I retire
    this?". This is the question for "can I erase it?" — a role granted last term and taken
    back since has no current holder, but the audit log still refers to it.
    """
    return await db.count(UserRoleAssignment, {"role_id": role_id})


async def delete_role(db: Db, role: Role) -> None:
    """Remove a role outright, with everything that only existed because of it. Only safe
    once `ever_assigned_count` is zero.

    PostgreSQL cascaded the role's permission links and institute overrides on delete;
    MongoDB has no cascade, so they are removed here, in the same commit.
    """
    db.delete_many(RolePermission, {"role_id": role.id})
    db.delete_many(InstituteRolePermission, {"role_id": role.id})
    await db.delete(role)
