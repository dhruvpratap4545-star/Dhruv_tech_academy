"""Queries behind the authorization engine. No business rules live here."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.auth.models import RefreshToken  # noqa: F401  (FK target for metadata)
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


def _live_assignments(user_id: uuid.UUID) -> Select[tuple[UserRoleAssignment]]:
    return select(UserRoleAssignment).where(
        UserRoleAssignment.user_id == user_id,
        UserRoleAssignment.revoked_at.is_(None),
    )


async def load_grants(db: AsyncSession, user_id: uuid.UUID) -> Sequence[GrantRow]:
    """Every (role, scope, permission) the user currently holds, after their institute's
    own adjustments to those roles have been applied.

    Two queries. The first is the base: three joins rather than three round trips, and the
    result is small (roles x permissions, so tens of rows). The second reads only the rows
    where an institute has chosen to differ from the built-in definition, which for most
    institutes is none at all.

    Applying the difference here, rather than in the engine, is deliberate: every caller
    above this line then sees one flat truth about what the user may do, and no call site
    has to remember that institute customisation exists.
    """
    stmt = (
        select(
            Role.key,
            Role.name,
            Role.rank,
            UserRoleAssignment.institute_id,
            UserRoleAssignment.branch_id,
            Permission.key,
        )
        .join(Role, Role.id == UserRoleAssignment.role_id)
        # Outer, so a role that currently grants nothing still produces one row naming the
        # assignment and its scope. An inner join drops it entirely, and then an institute
        # that adds a permission to an empty role has nothing for the addition to attach
        # to: the override row exists, the screen shows the tick, and the person it was
        # granted to still cannot do the thing. The permission column is NULL on those
        # rows and `_apply_role_overrides` discards them once it has read the scope.
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .outerjoin(Permission, Permission.id == RolePermission.permission_id)
        .where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.revoked_at.is_(None),
            Role.is_active.is_(True),
        )
    )
    rows: list[GrantRow] = list(await db.execute(stmt))  # type: ignore[arg-type]

    overrides = await _role_overrides_for_user(db, user_id)
    if not overrides:
        return [row for row in rows if row[5] is not None]
    return _apply_role_overrides(rows, overrides)


# (role_key, role_name, rank, institute_id, branch_id) -> the assignment a grant came from
_Assignment = tuple[str, str, int, uuid.UUID | None, uuid.UUID | None]


async def _role_overrides_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[tuple[uuid.UUID, str], dict[str, str]]:
    """(institute id, role key) -> {permission key: effect}, for this user's institutes."""
    stmt = (
        select(
            InstituteRolePermission.institute_id,
            Role.key,
            Permission.key,
            InstituteRolePermission.effect,
        )
        .join(Permission, Permission.id == InstituteRolePermission.permission_id)
        .join(Role, Role.id == InstituteRolePermission.role_id)
        .where(
            InstituteRolePermission.institute_id.in_(
                select(UserRoleAssignment.institute_id).where(
                    UserRoleAssignment.user_id == user_id,
                    UserRoleAssignment.revoked_at.is_(None),
                    UserRoleAssignment.institute_id.is_not(None),
                )
            ),
            InstituteRolePermission.role_id.in_(
                select(UserRoleAssignment.role_id).where(
                    UserRoleAssignment.user_id == user_id,
                    UserRoleAssignment.revoked_at.is_(None),
                )
            ),
        )
    )
    found: dict[tuple[uuid.UUID, str], dict[str, str]] = {}
    for institute_id, role_key, permission_key, effect in await db.execute(stmt):
        found.setdefault((institute_id, role_key), {})[permission_key] = effect
    return found


async def role_ids_by_key(db: AsyncSession) -> dict[str, uuid.UUID]:
    result = await db.execute(select(Role.key, Role.id))
    return dict(result.all())  # type: ignore[arg-type]


def _apply_role_overrides(
    rows: Sequence[GrantRow],
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
            # The outer join's placeholder for a role that grants nothing. Its only job was
            # to put the assignment above into `assignments`.
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
            added: GrantRow = (
                role_key,
                role_name,
                rank,
                institute_id,
                branch_id,
                permission_key,
            )
            # A set rather than scanning `kept`: someone holding several roles across
            # several branches turns that scan into the slowest part of every request.
            if added not in seen:
                kept.append(added)
                seen.add(added)

    return kept


async def load_personal_grants(db: AsyncSession, user_id: uuid.UUID) -> Sequence[PersonalGrantRow]:
    """The per-user allow/deny layer, as (permission, effect, institute, branch).

    Expiry is evaluated in PostgreSQL, not Python: a grant that lapsed while a context sat
    in the cache must not come back to life on the next rebuild, and ``now()`` on the
    database is the one clock every instance agrees on.
    """
    stmt = (
        select(
            Permission.key,
            UserPermissionGrant.effect,
            UserPermissionGrant.institute_id,
            UserPermissionGrant.branch_id,
        )
        .join(Permission, Permission.id == UserPermissionGrant.permission_id)
        .where(
            UserPermissionGrant.user_id == user_id,
            UserPermissionGrant.revoked_at.is_(None),
            or_(
                UserPermissionGrant.expires_at.is_(None),
                UserPermissionGrant.expires_at > func.now(),
            ),
        )
    )
    result = await db.execute(stmt)
    return result.all()  # type: ignore[return-value]


async def load_permission_modules(db: AsyncSession) -> dict[str, str]:
    """permission key -> module key. Changes only when the seed runs, so the caller
    holds this for the life of the process."""
    result = await db.execute(select(Permission.key, Permission.module_key))
    return dict(result.all())  # type: ignore[arg-type]


async def load_core_modules(db: AsyncSession) -> frozenset[str]:
    result = await db.execute(select(Module.key).where(Module.is_core.is_(True)))
    return frozenset(result.scalars())


async def is_module_enabled(db: AsyncSession, institute_id: uuid.UUID, module_key: str) -> bool:
    """PRD §5.2 step 5. An absent row means not enabled."""
    stmt = select(
        exists().where(
            InstituteModule.institute_id == institute_id,
            InstituteModule.module_key == module_key,
            InstituteModule.enabled.is_(True),
            or_(InstituteModule.valid_till.is_(None), InstituteModule.valid_till >= _today()),
        )
    )
    return bool(await db.scalar(stmt))


def _today():  # pragma: no cover - trivial, kept separate so tests can freeze it
    from datetime import UTC, datetime

    return datetime.now(UTC).date()


async def faculty_teaches_class(db: AsyncSession, user_id: uuid.UUID, class_id: uuid.UUID) -> bool:
    """PRD §5.2 step 4 for Faculty. Index-only lookup on (faculty_user_id, class_id)."""
    stmt = select(
        exists().where(
            ClassFaculty.faculty_user_id == user_id,
            ClassFaculty.class_id == class_id,
        )
    )
    return bool(await db.scalar(stmt))


async def student_enrolled_in_class(
    db: AsyncSession, user_id: uuid.UUID, class_id: uuid.UUID
) -> bool:
    """PRD §5.2 step 4 for Student. Only an active enrolment counts."""
    stmt = select(
        exists().where(
            ClassEnrollment.student_user_id == user_id,
            ClassEnrollment.class_id == class_id,
            ClassEnrollment.status == "active",
        )
    )
    return bool(await db.scalar(stmt))


async def faculty_class_ids(db: AsyncSession, user_id: uuid.UUID) -> frozenset[uuid.UUID]:
    """Classes a faculty member teaches. Used to scope list endpoints rather than
    filtering in Python after loading everything."""
    result = await db.execute(
        select(ClassFaculty.class_id).where(ClassFaculty.faculty_user_id == user_id)
    )
    return frozenset(result.scalars())


async def student_class_ids(db: AsyncSession, user_id: uuid.UUID) -> frozenset[uuid.UUID]:
    result = await db.execute(
        select(ClassEnrollment.class_id).where(
            ClassEnrollment.student_user_id == user_id,
            ClassEnrollment.status == "active",
        )
    )
    return frozenset(result.scalars())


async def class_scope(db: AsyncSession, class_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID] | None:
    """(institute_id, branch_id) for a class, so a class target can be resolved to a scope."""
    result = await db.execute(
        select(Class.institute_id, Class.branch_id).where(Class.id == class_id)
    )
    return result.one_or_none()  # type: ignore[return-value]


async def get_role_by_key(db: AsyncSession, key: str) -> Role | None:
    return await db.scalar(select(Role).where(Role.key == key))


async def list_roles(db: AsyncSession, *, include_inactive: bool = False) -> Sequence[Role]:
    stmt = select(Role).order_by(Role.rank.desc())
    if not include_inactive:
        stmt = stmt.where(Role.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalars().all()


async def live_assignments_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> Sequence[UserRoleAssignment]:
    result = await db.execute(_live_assignments(user_id))
    return result.scalars().all()


async def find_assignment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    institute_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
) -> UserRoleAssignment | None:
    """Exact-scope match, so re-granting the same role at the same scope is idempotent."""
    stmt = _live_assignments(user_id).where(
        UserRoleAssignment.role_id == role_id,
        UserRoleAssignment.institute_id.is_(institute_id)
        if institute_id is None
        else UserRoleAssignment.institute_id == institute_id,
        UserRoleAssignment.branch_id.is_(branch_id)
        if branch_id is None
        else UserRoleAssignment.branch_id == branch_id,
    )
    return await db.scalar(stmt)


async def count_usable_role_holders(db: AsyncSession, role_id: uuid.UUID) -> int:
    """How many people hold this role *and can actually sign in*.

    Guards "at least one Super Admin must always exist" (PRD §3). Counting bare assignment
    rows is not enough: an invited Super Admin who has never set a password holds the role
    but cannot log in, so treating them as the survivor lets the last real administrator
    revoke their own access and lock everyone out of the platform permanently.
    """
    from app.modules.users.models import User

    stmt = (
        select(func.count())
        .select_from(UserRoleAssignment)
        .join(User, User.id == UserRoleAssignment.user_id)
        .where(
            UserRoleAssignment.role_id == role_id,
            UserRoleAssignment.revoked_at.is_(None),
            User.status == "active",
            User.password_hash.is_not(None),
        )
    )
    return int(await db.scalar(stmt) or 0)


async def user_ids_in_scope(
    db: AsyncSession, *, institute_id: uuid.UUID, branch_id: uuid.UUID | None = None
) -> Select[tuple[uuid.UUID]]:
    """A *subquery* of user ids holding a live assignment inside a scope.

    Returned unexecuted on purpose: the users list endpoint composes it into its own
    statement so the filter happens in PostgreSQL instead of shipping ids to Python.
    """
    conditions = [
        UserRoleAssignment.revoked_at.is_(None),
        UserRoleAssignment.institute_id == institute_id,
    ]
    if branch_id is not None:
        conditions.append(
            or_(
                UserRoleAssignment.branch_id == branch_id,
                UserRoleAssignment.branch_id.is_(None),
            )
        )
    return select(UserRoleAssignment.user_id).where(and_(*conditions))


# ------------------------------------------------------------------ role & grant admin


async def roles_visible_to(
    db: AsyncSession,
    institute_ids: frozenset[uuid.UUID] | None,
    *,
    include_retired: bool = False,
) -> Sequence[Role]:
    """Built-in roles, plus the custom roles of the institutes the caller can see.

    ``None`` means platform staff: every role, custom ones included. Everyone else sees the
    six built-ins (they need to, to understand what a role means) and only their own
    institute's inventions — another institute's role names are that institute's business.

    Retired roles are left out. They were removed on purpose, and a permission matrix that
    still lists one invites somebody to tick a box on a role nobody can be given — the
    setting saves, nothing happens, and there is no error to explain why.
    """
    stmt = select(Role).order_by(Role.rank.desc(), Role.name)
    if not include_retired:
        stmt = stmt.where(Role.is_active.is_(True))
    if institute_ids is not None:
        stmt = stmt.where(or_(Role.institute_id.is_(None), Role.institute_id.in_(institute_ids)))
    result = await db.execute(stmt)
    return result.scalars().all()


async def permission_keys_by_role(db: AsyncSession) -> dict[uuid.UUID, list[str]]:
    """role id -> permission keys, for every role, in one query.

    The alternative — a lazy relationship per role — is the N+1 that turns a catalogue
    screen into thirty round trips.
    """
    result = await db.execute(
        select(RolePermission.role_id, Permission.key)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .order_by(Permission.key)
    )
    grouped: dict[uuid.UUID, list[str]] = {}
    for role_id, key in result.all():
        grouped.setdefault(role_id, []).append(key)
    return grouped


async def holder_counts(db: AsyncSession) -> dict[uuid.UUID, int]:
    """role id -> how many people currently hold it."""
    result = await db.execute(
        select(UserRoleAssignment.role_id, func.count())
        .where(UserRoleAssignment.revoked_at.is_(None))
        .group_by(UserRoleAssignment.role_id)
    )
    return {role_id: int(count) for role_id, count in result.all()}


async def get_role(db: AsyncSession, role_id: uuid.UUID) -> Role | None:
    return await db.get(Role, role_id)


async def role_by_key(db: AsyncSession, key: str) -> Role | None:
    """Archived roles included — a retired role still owns its key."""
    return await db.scalar(select(Role).where(Role.key == key))


async def permissions_by_keys(db: AsyncSession, keys: Sequence[str]) -> Sequence[Permission]:
    if not keys:
        return []
    result = await db.execute(select(Permission).where(Permission.key.in_(keys)))
    return result.scalars().all()


async def replace_role_permissions(
    db: AsyncSession, *, role_id: uuid.UUID, permission_ids: Sequence[uuid.UUID]
) -> None:
    """Set a role's permissions to exactly this list.

    Delete-then-insert rather than a diff: the set is tens of rows, the operation is rare,
    and a diff would be more code to get subtly wrong for no measurable gain.
    """
    await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    db.add_all(
        RolePermission(role_id=role_id, permission_id=permission_id)
        for permission_id in permission_ids
    )


async def live_grants_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> Sequence[tuple[UserPermissionGrant, str, str | None]]:
    """Every grant still on the record for a user, with its permission key and granter.

    Expired rows are included — they are history an administrator reviewing access needs
    to see, and the engine ignores them separately (``load_personal_grants``).
    """
    from app.modules.users.models import User

    granter = aliased(User)
    result = await db.execute(
        select(UserPermissionGrant, Permission.key, granter.full_name)
        .join(Permission, Permission.id == UserPermissionGrant.permission_id)
        .outerjoin(granter, granter.id == UserPermissionGrant.granted_by)
        .where(
            UserPermissionGrant.user_id == user_id,
            UserPermissionGrant.revoked_at.is_(None),
        )
        .order_by(UserPermissionGrant.created_at.desc())
    )
    return result.all()  # type: ignore[return-value]


async def find_live_grant(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    permission_id: uuid.UUID,
    institute_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
) -> UserPermissionGrant | None:
    """Exact-scope match, so re-granting the same thing updates instead of stacking."""
    stmt = select(UserPermissionGrant).where(
        UserPermissionGrant.user_id == user_id,
        UserPermissionGrant.permission_id == permission_id,
        UserPermissionGrant.revoked_at.is_(None),
        UserPermissionGrant.institute_id.is_(institute_id)
        if institute_id is None
        else UserPermissionGrant.institute_id == institute_id,
        UserPermissionGrant.branch_id.is_(branch_id)
        if branch_id is None
        else UserPermissionGrant.branch_id == branch_id,
    )
    return await db.scalar(stmt)


async def get_grant(db: AsyncSession, grant_id: uuid.UUID) -> UserPermissionGrant | None:
    return await db.get(UserPermissionGrant, grant_id)


async def institute_overrides(
    db: AsyncSession, institute_id: uuid.UUID
) -> dict[uuid.UUID, dict[str, str]]:
    """role id -> {permission key: effect} for one institute, for the roles screen."""
    stmt = (
        select(
            InstituteRolePermission.role_id,
            Permission.key,
            InstituteRolePermission.effect,
        )
        .join(Permission, Permission.id == InstituteRolePermission.permission_id)
        .where(InstituteRolePermission.institute_id == institute_id)
    )
    grouped: dict[uuid.UUID, dict[str, str]] = {}
    for role_id, key, effect in await db.execute(stmt):
        grouped.setdefault(role_id, {})[key] = effect
    return grouped


async def customised_role_ids(db: AsyncSession) -> set[uuid.UUID]:
    """Roles that at least one institute has adjusted, so the catalogue can say so."""
    result = await db.execute(select(InstituteRolePermission.role_id).distinct())
    return set(result.scalars())


async def replace_institute_overrides(
    db: AsyncSession,
    *,
    institute_id: uuid.UUID,
    role_id: uuid.UUID,
    effects: dict[uuid.UUID, str],
    created_by: uuid.UUID | None,
) -> None:
    """Set one institute's adjustments to one role to exactly ``effects``.

    Delete-then-insert rather than a diff: the set is a handful of rows, the operation is
    rare and deliberate, and a diff is more code to get subtly wrong for no gain. An empty
    ``effects`` therefore means "this institute uses the role exactly as defined", and the
    rows disappear rather than lingering as a no-op that future readers have to decode.
    """
    await db.execute(
        delete(InstituteRolePermission).where(
            InstituteRolePermission.institute_id == institute_id,
            InstituteRolePermission.role_id == role_id,
        )
    )
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


async def user_ids_holding_role_in(
    db: AsyncSession, *, role_id: uuid.UUID, institute_id: uuid.UUID
) -> set[uuid.UUID]:
    """Everyone whose cached permissions this role change invalidates."""
    result = await db.execute(
        select(UserRoleAssignment.user_id).where(
            UserRoleAssignment.role_id == role_id,
            UserRoleAssignment.institute_id == institute_id,
            UserRoleAssignment.revoked_at.is_(None),
        )
    )
    return set(result.scalars())


async def ever_assigned_count(db: AsyncSession, role_id: uuid.UUID) -> int:
    """How many assignments of this role have ever existed, revoked ones included.

    `holder_counts` answers "who holds it now", which is the question for "can I retire
    this?". This is the question for "can I erase it?" — and the two differ precisely in
    the case that matters: a role granted to someone last term and taken back since has no
    current holder, but the audit log still refers to it.
    """
    from sqlalchemy import func

    return (
        await db.scalar(
            select(func.count())
            .select_from(UserRoleAssignment)
            .where(UserRoleAssignment.role_id == role_id)
        )
    ) or 0


async def delete_role(db: AsyncSession, role: Role) -> None:
    """Remove a role row outright. Only safe once `ever_assigned_count` is zero."""
    await db.delete(role)
    await db.flush()
