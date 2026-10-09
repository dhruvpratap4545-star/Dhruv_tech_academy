"""Managing access, as opposed to checking it (ADR-017).

``service.py`` answers "may this person do X here?". This file is the other half: creating
custom roles, and granting or blocking single permissions for single people.

Every write in here is a privilege change, so every one of them passes the same four
questions before it touches the database:

1. **Scope** — may the caller act on this institute or branch at all? (``Authorized.ensure``)
2. **Rank** — is the target strictly below the caller? Nobody edits a peer's access.
3. **Subset** — is the caller handing out only what they already hold *at that scope*?
   Without this, "create a role" is a privilege-escalation primitive: an Institute Admin
   could mint a role holding ``platform_admin:manage`` and assign it to themselves.
4. **Self** — the caller is never the target. Every escalation attack starts with
   "grant myself one more thing", and the cheapest place to stop it is here.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.modules.audit import events
from app.modules.audit import service as audit
from app.modules.auth.service import RequestMeta
from app.modules.org.models import Branch, Institute
from app.modules.rbac import repository, schemas
from app.modules.rbac import service as engine
from app.modules.rbac.catalog import (
    PERMISSIONS,
    PERMISSIONS_BY_KEY,
    grantable_ceiling,
    max_grantable_rank,
)
from app.modules.rbac.context import AuthContext
from app.modules.rbac.models import Role, UserPermissionGrant
from app.modules.rbac.scopes import Scope
from app.modules.rbac.service import Authorized
from app.modules.users.models import User

_SLUG = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG.sub("_", name.lower()).strip("_")[:24]


def scope_of(institute_id: uuid.UUID | None, branch_id: uuid.UUID | None) -> Scope:
    return Scope(institute_id=institute_id, branch_id=branch_id)


def _scope_label(scope: Scope, names: dict[uuid.UUID, str] | None = None) -> str:
    """A phrase a non-technical administrator can read without a legend."""
    names = names or {}
    if scope.institute_id is None:
        return "All institutes"
    institute = names.get(scope.institute_id, "this institute")
    if scope.branch_id is None:
        return institute
    return f"{institute} · {names.get(scope.branch_id, 'one branch')}"


async def _names_for(db: AsyncSession, scopes: list[Scope]) -> dict[uuid.UUID, str]:
    """Resolve institute and branch ids to names, in two queries regardless of how many.

    Labels are built for display only, so a missing name degrades to a generic phrase
    rather than failing the request.
    """
    institute_ids = {s.institute_id for s in scopes if s.institute_id}
    branch_ids = {s.branch_id for s in scopes if s.branch_id}
    names: dict[uuid.UUID, str] = {}
    if institute_ids:
        rows = await db.execute(
            Institute.__table__.select().with_only_columns(Institute.id, Institute.name)
        )
        names.update({i: n for i, n in rows.all() if i in institute_ids})
    if branch_ids:
        rows = await db.execute(Branch.__table__.select().with_only_columns(Branch.id, Branch.name))
        names.update({i: n for i, n in rows.all() if i in branch_ids})
    return names


# --------------------------------------------------------------------------- catalogue


def list_permissions() -> list[schemas.PermissionOut]:
    """The permission catalogue. Static seed data, so no database round trip."""
    return [
        schemas.PermissionOut(
            key=p.key,
            description=p.description,
            group=p.group,
            module_key=p.module_key,
            resource=p.resource,
            action=p.action,
        )
        for p in PERMISSIONS
    ]


def _may_edit(role: Role, context: AuthContext) -> bool:
    """A role is editable when it is custom, belongs to an institute the caller commands,
    and sits strictly below them. Built-ins are never editable by anyone: they are what
    'Institute Admin' *means*, and a product where that varies per customer cannot be
    supported."""
    if role.is_system or role.institute_id is None:
        return False
    if not context.can("role:manage", Scope(institute_id=role.institute_id)):
        return False
    return role.rank <= max_grantable_rank(
        context.max_rank_within(Scope(institute_id=role.institute_id))
    )


def _may_customise(role, context: AuthContext, institute_id: uuid.UUID | None) -> bool:
    """May this caller adjust what ``role`` allows inside ``institute_id``?

    Unlike editing a role's definition, this is open to built-ins — adjusting Faculty for
    one institute does not change what Faculty means anywhere else. The limits are the
    ordinary ones: you must command the institute, and the role must sit below you, or
    an Institute Admin could redefine Institute Admin and grant themselves the platform.
    """
    if institute_id is None or role.scope_level == "platform":
        return False
    if role.institute_id is not None and role.institute_id != institute_id:
        return False
    scope = Scope(institute_id=institute_id)
    if not context.can("role:manage", scope):
        return False
    return role.rank <= max_grantable_rank(context.max_rank_within(scope))


async def list_roles(
    db: AsyncSession, context: AuthContext, institute_id: uuid.UUID | None = None
) -> list[schemas.RoleOut]:
    """The role catalogue, seen from one institute.

    ``institute_id`` decides whose view this is. With it, each role's permissions are the
    *effective* set for that institute — its own definition, plus what the institute added,
    minus what it removed. Without it (platform staff looking across everything) the
    definitions are returned unchanged, because there is no single institute to speak for.
    """
    visible_to = None if context.is_platform_staff else context.institute_ids
    roles = await repository.roles_visible_to(db, visible_to)
    base = await repository.permission_keys_by_role(db)
    counts = await repository.holder_counts(db)
    overrides = await repository.institute_overrides(db, institute_id) if institute_id else {}

    rows: list[schemas.RoleOut] = []
    for role in roles:
        defined = base.get(role.id, [])
        adjustments = overrides.get(role.id, {})
        if adjustments:
            effective = {k for k in defined if adjustments.get(k) != "deny"}
            effective |= {k for k, effect in adjustments.items() if effect == "allow"}
            permissions = sorted(effective)
        else:
            permissions = defined

        rows.append(
            schemas.RoleOut(
                id=role.id,
                key=role.key,
                name=role.name,
                description=role.description,
                scope_level=role.scope_level,
                rank=role.rank,
                is_system=role.is_system,
                is_active=role.is_active,
                institute_id=role.institute_id,
                permissions=permissions,
                customised_here=bool(adjustments),
                holder_count=counts.get(role.id, 0),
                editable=_may_edit(role, context),
                customisable=_may_customise(role, context, institute_id),
            )
        )
    return rows


# ------------------------------------------------------------------------ custom roles


def _check_subset(context: AuthContext, keys: list[str], scope: Scope) -> None:
    """Rule 3. The caller may only hand out permissions they can use at this very scope.

    ``context.can`` rather than ``holds``: holding ``user:invite`` at branch A must not let
    someone put it into a role scoped to branch B.
    """
    unknown = [k for k in keys if k not in PERMISSIONS_BY_KEY]
    if unknown:
        raise ValidationFailed(f"No such permission: {', '.join(sorted(unknown)[:3])}.")
    beyond = [k for k in keys if not context.can(k, scope)]
    if beyond:
        raise Forbidden(
            "A role cannot include permissions you do not hold yourself here: "
            f"{', '.join(sorted(beyond)[:3])}."
        )


async def create_role(
    db: AsyncSession,
    *,
    actor: User,
    guard: Authorized,
    payload: schemas.RoleCreateRequest,
    meta: RequestMeta,
) -> Role:
    scope = Scope(institute_id=payload.institute_id)
    await guard.ensure(scope)

    holder_rank = guard.context.max_rank_within(scope)
    if payload.rank > max_grantable_rank(holder_rank):
        raise Forbidden("A role you create must sit below your own level.")
    if payload.scope_level == "platform":
        raise ValidationFailed("A custom role belongs to an institute, not to the platform.")
    _check_subset(guard.context, payload.permissions, scope)

    institute = await db.get(Institute, payload.institute_id)
    if institute is None:
        raise NotFound("That institute does not exist.")

    # Namespaced so two institutes can both have a "Lab Assistant" without colliding.
    key = f"{institute.code.lower()}.{_slugify(payload.name)}"
    existing = await repository.role_by_key(db, key)
    if existing is not None:
        # A retired role keeps its name. Letting a new role reuse it would make every past
        # audit row ambiguous — "abc.lab_assistant" would name two different sets of
        # permissions depending on when you read it.
        raise Conflict(
            "A retired role already uses that name. Choose a different one — the old name "
            "stays reserved so past records keep their meaning."
            if not existing.is_active
            else "A role with that name already exists for this institute."
        )

    role = Role(
        key=key,
        name=payload.name,
        description=payload.description,
        scope_level=payload.scope_level,
        rank=payload.rank,
        is_system=False,
        is_active=True,
        institute_id=payload.institute_id,
        created_by=actor.id,
    )
    db.add(role)
    await db.flush()

    rows = await repository.permissions_by_keys(db, payload.permissions)
    await repository.replace_role_permissions(
        db, role_id=role.id, permission_ids=[r.id for r in rows]
    )
    audit.record(
        db,
        action=events.ROLE_CREATED,
        actor_user_id=actor.id,
        target_type="role",
        target_id=role.id,
        institute_id=payload.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"key": key, "rank": payload.rank, "permissions": len(payload.permissions)},
    )
    await db.commit()
    return role


async def update_role(
    db: AsyncSession,
    *,
    actor: User,
    guard: Authorized,
    role_id: uuid.UUID,
    payload: schemas.RoleUpdateRequest,
    meta: RequestMeta,
) -> Role:
    role = await repository.get_role(db, role_id)
    if role is None or not _may_edit(role, guard.context):
        # Not found, not forbidden: a built-in role is visible to everyone, but an
        # unreachable *custom* role should not be confirmed to exist by the error.
        raise NotFound("That role does not exist, or you cannot edit it.")

    assert role.institute_id is not None  # guaranteed by _may_edit and the check constraint
    scope = Scope(institute_id=role.institute_id)
    await guard.ensure(scope)

    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.permissions is not None:
        _check_subset(guard.context, payload.permissions, scope)
        rows = await repository.permissions_by_keys(db, payload.permissions)
        await repository.replace_role_permissions(
            db, role_id=role.id, permission_ids=[r.id for r in rows]
        )

    audit.record(
        db,
        action=events.ROLE_UPDATED,
        actor_user_id=actor.id,
        target_type="role",
        target_id=role.id,
        institute_id=role.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"key": role.key, "permissions_changed": payload.permissions is not None},
    )
    await db.commit()
    # Everyone holding this role is now carrying a stale permission set.
    await _invalidate_holders(db, role.id)
    return role


async def archive_role(
    db: AsyncSession,
    *,
    actor: User,
    guard: Authorized,
    role_id: uuid.UUID,
    meta: RequestMeta,
) -> Role:
    role = await repository.get_role(db, role_id)
    if role is None or not _may_edit(role, guard.context):
        raise NotFound("That role does not exist, or you cannot edit it.")
    assert role.institute_id is not None
    await guard.ensure(Scope(institute_id=role.institute_id))

    holders = (await repository.holder_counts(db)).get(role.id, 0)
    if holders:
        raise Conflict(
            f"{holders} {'person holds' if holders == 1 else 'people hold'} this role. "
            "Move them to another role first."
        )

    role.is_active = False
    audit.record(
        db,
        action=events.ROLE_ARCHIVED,
        actor_user_id=actor.id,
        target_type="role",
        target_id=role.id,
        institute_id=role.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"key": role.key},
    )
    await db.commit()
    return role


async def _invalidate_holders(db: AsyncSession, role_id: uuid.UUID) -> None:
    """Drop the cached context of everyone holding a role whose meaning just changed.

    Without this, a permission removed from a role keeps working for up to the cache TTL —
    which is precisely the window in which somebody is removing it because it is being
    misused.
    """
    from sqlalchemy import select

    from app.modules.rbac.models import UserRoleAssignment

    rows = await db.execute(
        select(UserRoleAssignment.user_id).where(
            UserRoleAssignment.role_id == role_id,
            UserRoleAssignment.revoked_at.is_(None),
        )
    )
    for (user_id,) in rows.all():
        engine.invalidate_context(user_id)


# -------------------------------------------------------------------- personal grants


async def list_grants(db: AsyncSession, user_id: uuid.UUID) -> list[schemas.GrantOut]:
    rows = await repository.live_grants_for_user(db, user_id)
    names = await _names_for(db, [scope_of(g.institute_id, g.branch_id) for g, _, _ in rows])
    now = datetime.now(UTC)
    return [
        schemas.GrantOut(
            id=grant.id,
            permission=key,
            description=PERMISSIONS_BY_KEY[key].description if key in PERMISSIONS_BY_KEY else key,
            effect=grant.effect,
            institute_id=grant.institute_id,
            branch_id=grant.branch_id,
            scope_label=_scope_label(scope_of(grant.institute_id, grant.branch_id), names),
            reason=grant.reason,
            expires_at=grant.expires_at,
            expired=grant.expires_at is not None and grant.expires_at <= now,
            granted_by_name=granter,
            created_at=grant.created_at,
        )
        for grant, key, granter in rows
    ]


async def create_grant(
    db: AsyncSession,
    *,
    actor: User,
    guard: Authorized,
    target: User,
    payload: schemas.GrantCreateRequest,
    meta: RequestMeta,
) -> UserPermissionGrant:
    """Give one person one extra permission, or block one for them.

    The asymmetry between allow and deny is deliberate. Granting is bounded by what the
    caller holds — rule 3 — because it hands out power. Blocking is not, because it only
    ever takes power away, and an administrator who can already revoke someone's whole role
    is not escalated by being able to remove one piece of it.
    """
    if target.id == actor.id:
        raise Forbidden("You cannot change your own access.")

    scope = scope_of(payload.institute_id, payload.branch_id)
    await guard.ensure(scope)

    permission = PERMISSIONS_BY_KEY.get(payload.permission)
    if permission is None:
        raise ValidationFailed("No such permission.")

    target_context = await engine.get_context(db, target.id)
    holder_rank = guard.context.max_rank_within(scope)
    if target_context.max_rank_within(scope) >= holder_rank:
        raise Forbidden("You cannot change the access of someone at or above your own level.")

    if payload.effect == "allow" and not guard.context.can(payload.permission, scope):
        raise Forbidden("You cannot give away a permission you do not hold here yourself.")

    if payload.expires_at is not None and payload.expires_at <= datetime.now(UTC):
        raise ValidationFailed("The expiry date must be in the future.")

    rows = await repository.permissions_by_keys(db, [payload.permission])
    if not rows:
        raise ValidationFailed("No such permission.")
    permission_row = rows[0]

    existing = await repository.find_live_grant(
        db,
        user_id=target.id,
        permission_id=permission_row.id,
        institute_id=payload.institute_id,
        branch_id=payload.branch_id,
    )
    if existing is not None:
        # Same permission at the same scope: update rather than stack a second row, so
        # "what applies here?" never depends on which of two rows is read first.
        existing.effect = payload.effect
        existing.reason = payload.reason
        existing.expires_at = payload.expires_at
        existing.granted_by = actor.id
        grant = existing
    else:
        grant = UserPermissionGrant(
            user_id=target.id,
            permission_id=permission_row.id,
            effect=payload.effect,
            institute_id=payload.institute_id,
            branch_id=payload.branch_id,
            reason=payload.reason,
            expires_at=payload.expires_at,
            granted_by=actor.id,
        )
        db.add(grant)

    audit.record(
        db,
        action=events.PERMISSION_GRANTED
        if payload.effect == "allow"
        else events.PERMISSION_DENIED_SET,
        actor_user_id=actor.id,
        target_type="user",
        target_id=target.id,
        institute_id=payload.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={
            "permission": payload.permission,
            "effect": payload.effect,
            "reason": payload.reason,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
        },
    )
    await db.commit()
    engine.invalidate_context(target.id)
    return grant


async def revoke_grant(
    db: AsyncSession,
    *,
    actor: User,
    guard: Authorized,
    target: User,
    grant_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    grant = await repository.get_grant(db, grant_id)
    if grant is None or grant.user_id != target.id or grant.revoked_at is not None:
        raise NotFound("That grant does not exist.")

    await guard.ensure(scope_of(grant.institute_id, grant.branch_id))
    grant.revoked_at = datetime.now(UTC)
    grant.revoked_by = actor.id

    audit.record(
        db,
        action=events.PERMISSION_GRANT_REVOKED,
        actor_user_id=actor.id,
        target_type="user",
        target_id=target.id,
        institute_id=grant.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"grant_id": str(grant.id), "effect": grant.effect},
    )
    await db.commit()
    engine.invalidate_context(target.id)


# ------------------------------------------------------------------------- my own access


async def build_my_access(db: AsyncSession, context: AuthContext) -> schemas.MyAccessOut:
    """What the signed-in person can actually do, explained.

    Every permission in the catalogue appears, held or not. The unheld ones are the point:
    this is the one screen whose job is to describe the boundary of someone's access, and a
    boundary you cannot see is not an explanation (ADR-018).
    """
    names = await _names_for(db, [a.scope for a in context.assignments])
    roles = [
        schemas.AccessRoleOut(
            key=a.role_key,
            name=a.role_name,
            rank=a.rank,
            scope_level=a.scope.level,
            scope_label=_scope_label(a.scope, names),
            institute_id=a.scope.institute_id,
            branch_id=a.scope.branch_id,
        )
        for a in sorted(context.assignments, key=lambda a: -a.rank)
    ]

    permissions: list[schemas.EffectivePermission] = []
    for definition in PERMISSIONS:
        granted = context.holds(definition.key)
        blocked = bool(context.denials_for(definition.key))
        if granted:
            source = "direct" if definition.key in context.direct else "role"
        else:
            # Blocked and not-granted look identical from the outside, and the difference
            # matters: one means "nobody gave you this", the other "somebody took it away".
            source = "blocked" if blocked else "none"
        permissions.append(
            schemas.EffectivePermission(
                key=definition.key,
                description=definition.description,
                group=definition.group,
                granted=granted,
                scope_label=_widest_label(context.scopes_for(definition.key), names)
                if granted
                else "",
                source=source,
            )
        )

    ceiling = grantable_ceiling(context.max_rank)
    visible_to = None if context.is_platform_staff else context.institute_ids
    roles_rows = await repository.roles_visible_to(db, visible_to)
    can_grant = [r.name for r in roles_rows if r.is_active and r.rank <= ceiling]

    return schemas.MyAccessOut(
        roles=roles,
        permissions=permissions,
        granted_count=sum(1 for p in permissions if p.granted),
        total_count=len(permissions),
        can_grant_roles=can_grant,
        direct_grants=await list_grants(db, context.user_id),
    )


def _widest_label(scopes: tuple[Scope, ...], names: dict[uuid.UUID, str]) -> str:
    """The broadest scope a permission is held at — that is the honest headline.

    Someone holding `user:read` platform-wide *and* at one branch reads "All institutes";
    saying "one branch" because it happens to come first in a tuple would be a lie.
    """
    if not scopes:
        return ""
    widest = min(scopes, key=lambda s: (s.institute_id is not None, s.branch_id is not None))
    return _scope_label(widest, names)


# ------------------------------------------------- per-institute role customisation


async def set_role_permissions_for_institute(
    db: AsyncSession,
    *,
    actor: User,
    guard: Authorized,
    institute_id: uuid.UUID,
    role_id: uuid.UUID,
    permissions: list[str],
    meta: RequestMeta,
) -> None:
    """Set what a role allows **inside one institute**, as a difference from its definition.

    ``permissions`` is the effective set the caller wants, which is what their screen shows
    them. The difference against the role's own definition is computed here rather than
    asked for: an interface that made somebody think in deltas would be an interface that
    produced the wrong delta.

    The guards are the same four as everywhere else in this file, and all four matter:

    * **Scope** — the caller must command this institute.
    * **Rank** — the role must sit below them. Without this an Institute Admin could edit
      what Institute Admin means in their own institute and grant themselves anything.
    * **Subset** — every permission added must be one the caller already holds here, or
      customisation becomes a way to mint authority nobody granted.
    * **Platform roles** — refused outright. They belong to no institute, so there is no
      institute whose view of them could differ.
    """
    scope = Scope(institute_id=institute_id)
    await guard.ensure(scope)

    role = await repository.get_role(db, role_id)
    if role is None or not role.is_active:
        raise NotFound("That role does not exist.")
    if role.scope_level == "platform":
        raise ValidationFailed(
            f"{role.name} applies to the whole platform, so it cannot be changed for one institute."
        )
    if role.institute_id is not None and role.institute_id != institute_id:
        raise NotFound("That role does not exist.")

    holder_rank = guard.context.max_rank_within(scope)
    if role.rank > max_grantable_rank(holder_rank):
        raise Forbidden(
            f"{role.name} is at or above your own level, so you cannot change what it allows."
        )

    _check_subset(guard.context, permissions, scope)

    base = set((await repository.permission_keys_by_role(db)).get(role.id, []))
    wanted = set(permissions)
    added = sorted(wanted - base)
    removed = sorted(base - wanted)

    by_key = {p.key: p for p in await repository.permissions_by_keys(db, added + removed)}
    effects = {by_key[k].id: "allow" for k in added if k in by_key}
    effects.update({by_key[k].id: "deny" for k in removed if k in by_key})

    await repository.replace_institute_overrides(
        db,
        institute_id=institute_id,
        role_id=role.id,
        effects=effects,
        created_by=actor.id,
    )
    audit.record(
        db,
        action=events.ROLE_UPDATED,
        actor_user_id=actor.id,
        target_type="role",
        target_id=role.id,
        institute_id=institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"key": role.key, "added": added, "removed": removed, "scope": "institute"},
    )
    await db.commit()

    # Everyone holding this role *in this institute* is carrying a stale permission set.
    # Holders of the same role elsewhere are untouched, which is the point.
    for user_id in await repository.user_ids_holding_role_in(
        db, role_id=role.id, institute_id=institute_id
    ):
        engine.invalidate_context(user_id)
