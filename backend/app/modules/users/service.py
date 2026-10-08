"""User management use cases (PRD §4.2, §4.5, §4.6).

The rule that shapes this whole file is PRD §3.1: **a user can only add or promote someone
below their own level, inside their own scope.** It is enforced in two places that must both
hold — ``guard.ensure(scope)`` proves the caller may act there at all, and
``guard.ensure_can_grant(rank, scope)`` proves they are senior enough to hand out that role.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.modules.audit import events
from app.modules.audit import service as audit
from app.modules.auth import repository as auth_repo
from app.modules.auth import service as auth_service
from app.modules.auth.service import PURPOSE_SETUP, RequestMeta
from app.modules.notifications import templates
from app.modules.notifications.email import EmailMessage
from app.modules.rbac import repository as rbac_repo
from app.modules.rbac import service as rbac
from app.modules.rbac.catalog import FACULTY, ROLES_BY_KEY, STUDENT
from app.modules.rbac.models import UserRoleAssignment
from app.modules.rbac.scopes import Scope
from app.modules.rbac.service import Authorized
from app.modules.users import repository as repo
from app.modules.users import schemas
from app.modules.users.models import User, UserPreference

FACULTY_RANK = ROLES_BY_KEY[FACULTY].rank


def _scope_of(institute_id: uuid.UUID | None, branch_id: uuid.UUID | None) -> Scope:
    if branch_id is not None and institute_id is None:
        raise ValidationFailed("A branch role must also name its institute.")
    return Scope(institute_id=institute_id, branch_id=branch_id)


async def _require_role(db: AsyncSession, role_key: str):
    role = await rbac_repo.get_role_by_key(db, role_key)
    if role is None or not role.is_active:
        raise ValidationFailed("That role does not exist.")
    return role


def _validate_scope_for_role(role, scope: Scope) -> None:
    """A role's ``scope_level`` says exactly where it may be granted (PRD §3.1).

    Each clause closes a privilege hole:

    * a platform role pinned to one institute would be meaningless;
    * an institute role granted at platform scope would hand the holder every institute;
    * a **branch** role granted without a branch would make a Branch Admin or a Faculty
      member effective across every branch of the institute — the exact escalation the
      hierarchy exists to prevent.
    """
    if role.scope_level == "platform" and scope.institute_id is not None:
        raise ValidationFailed(
            f"{role.name} is a platform role and cannot be given to one institute."
        )
    if role.scope_level == "institute" and scope.institute_id is None:
        raise ValidationFailed(f"{role.name} must be given within an institute.")
    if role.scope_level == "branch":
        if scope.institute_id is None:
            raise ValidationFailed(f"{role.name} must be given within an institute.")
        if scope.branch_id is None:
            raise ValidationFailed(f"{role.name} must be given within a specific branch.")


def _refuse_platform_role_on_invite(role) -> None:
    """Platform-wide authority is never created by an invitation.

    An invitation makes an account for an address nobody has proved they control, and the
    account exists before anyone has signed in to it. Both of those are fine for a student
    or a faculty member. For Super Admin or Platform Admin they are not: a single typo in
    the email field would hand the whole platform — every institute, every record — to a
    mailbox the inviter does not own, and the mistake is invisible until it is exploited.

    Succession still works, and PRD §3.1 still holds: an existing, active account can be
    promoted to any role its grantor may give. The two steps are the point. Promotion acts
    on somebody who has already proved they can receive mail at that address and sign in.
    """
    if role.scope_level == "platform":
        raise ValidationFailed(
            f"{role.name} cannot be given to a new invitation. Invite the person with a "
            "role inside an institute first, then change their role once their account "
            "is active."
        )


# -------------------------------------------------------------------------- invitation


async def invite_user(
    db: AsyncSession, *, guard: Authorized, payload: schemas.InviteUserRequest, meta: RequestMeta
) -> tuple[User, EmailMessage | None]:
    """PRD §4.2. Creates an ``invited`` user, grants the role, emails a setup code.

    Idempotent-ish by design: inviting an email that already exists is a conflict rather
    than a silent second account, because one person is one user row (PRD §2 rule 4).
    """
    scope = _scope_of(payload.institute_id, payload.branch_id)
    await guard.ensure(scope)

    role = await _require_role(db, payload.role_key)
    _refuse_platform_role_on_invite(role)
    _validate_scope_for_role(role, scope)
    guard.ensure_can_grant(role.rank, scope)

    email = payload.email.strip().lower()
    if await repo.email_taken(db, email):
        raise Conflict("Someone with that email address is already on the platform.")

    user = User(
        email=email,
        full_name=payload.full_name,
        phone=payload.phone,
        status="invited",
        password_hash=None,
    )
    db.add(user)
    await db.flush()
    db.add(UserPreference(user_id=user.id))

    await _grant_role(db, user_id=user.id, role=role, scope=scope, granted_by=guard.user_id)

    _require_classes_when_faculty(guard, scope, payload.class_ids)
    if payload.class_ids:
        await _link_classes(
            db, guard=guard, user=user, role_key=role.key, class_ids=payload.class_ids
        )

    _, code = await auth_service.issue_otp(db, user=user, purpose=PURPOSE_SETUP, meta=meta)

    inviter = await repo.get_user(db, guard.user_id)
    audit.record(
        db,
        action=events.USER_INVITED,
        actor_user_id=guard.user_id,
        target_type="user",
        target_id=user.id,
        institute_id=scope.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={
            "role_key": role.key,
            "branch_id": str(scope.branch_id) if scope.branch_id else None,
        },
    )
    await db.commit()
    return user, templates.password_setup(
        user.email, user.full_name, code, inviter.full_name if inviter else None
    )


def _require_classes_when_faculty(
    guard: Authorized, scope: Scope, class_ids: Sequence[uuid.UUID]
) -> None:
    """PRD §3.1: "Faculty | Student | Own assigned classes only".

    A faculty member's authority is the classes they teach, not the branch they sit in. If
    they could invite a student with no class attached, they would be adding people to the
    branch at large — which is a Branch Admin's job. Anyone senior to Faculty at this scope
    is unaffected; ``_link_classes`` then authorises each class individually.
    """
    if guard.context.max_rank_within(scope) > FACULTY_RANK:
        return
    if not class_ids:
        raise ValidationFailed("Please choose at least one of your classes to add this student to.")


async def _link_classes(
    db: AsyncSession,
    *,
    guard: Authorized,
    user: User,
    role_key: str,
    class_ids: Sequence[uuid.UUID],
) -> None:
    """Attach a new student or faculty member to the classes named in the invitation.

    Each class is authorised individually: a faculty member inviting students may only do so
    into classes they themselves teach (PRD §13 criterion 6a).
    """
    from app.modules.org.models import ClassEnrollment, ClassFaculty

    if role_key not in (STUDENT, FACULTY):
        raise ValidationFailed("Classes can only be given to a student or a faculty member.")

    for class_id in dict.fromkeys(class_ids):  # de-duplicate, preserve order
        await guard.ensure_class(class_id)
        if role_key == STUDENT:
            db.add(ClassEnrollment(class_id=class_id, student_user_id=user.id, status="active"))
        else:
            db.add(ClassFaculty(class_id=class_id, faculty_user_id=user.id))


async def resend_invitation(
    db: AsyncSession, *, guard: Authorized, user_id: uuid.UUID, meta: RequestMeta
) -> EmailMessage:
    user = await _require_visible_user(db, guard, user_id)
    if user.status != "invited":
        raise ValidationFailed("That person has already set their password.")

    await auth_service._guard_otp_quota(db, user, PURPOSE_SETUP)
    _, code = await auth_service.issue_otp(db, user=user, purpose=PURPOSE_SETUP, meta=meta)

    audit.record(
        db,
        action=events.INVITE_RESENT,
        actor_user_id=guard.user_id,
        target_type="user",
        target_id=user.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    await db.commit()
    return templates.password_setup(user.email, user.full_name, code)


# ------------------------------------------------------------------------------- roles


async def _grant_role(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    role,
    scope: Scope,
    granted_by: uuid.UUID | None,
) -> UserRoleAssignment:
    existing = await rbac_repo.find_assignment(
        db,
        user_id=user_id,
        role_id=role.id,
        institute_id=scope.institute_id,
        branch_id=scope.branch_id,
    )
    if existing is not None:
        return existing

    assignment = UserRoleAssignment(
        user_id=user_id,
        role_id=role.id,
        institute_id=scope.institute_id,
        branch_id=scope.branch_id,
        granted_by=granted_by,
    )
    db.add(assignment)
    await db.flush()
    rbac.invalidate_context(user_id)
    return assignment


async def grant_student_role(
    db: AsyncSession, *, user_id: uuid.UUID, institute_id: uuid.UUID, granted_by: uuid.UUID | None
) -> None:
    """Used by Direct Learner sign-up, which has no acting admin to authorise against."""
    role = await _require_role(db, STUDENT)
    await _grant_role(
        db,
        user_id=user_id,
        role=role,
        scope=Scope(institute_id=institute_id),
        granted_by=granted_by,
    )


async def assign_role(
    db: AsyncSession,
    *,
    guard: Authorized,
    user_id: uuid.UUID,
    payload: schemas.AssignRoleRequest,
    meta: RequestMeta,
) -> UserRoleAssignment:
    scope = _scope_of(payload.institute_id, payload.branch_id)
    await guard.ensure(scope)

    role = await _require_role(db, payload.role_key)
    _validate_scope_for_role(role, scope)
    guard.ensure_can_grant(role.rank, scope)

    user = await repo.get_user(db, user_id)
    if user is None or user.status == "deleted":
        raise NotFound("That user does not exist.")

    assignment = await _grant_role(
        db, user_id=user_id, role=role, scope=scope, granted_by=guard.user_id
    )
    audit.record(
        db,
        action=events.ROLE_ASSIGNED,
        actor_user_id=guard.user_id,
        target_type="user",
        target_id=user_id,
        institute_id=scope.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"role_key": role.key},
    )
    await db.commit()
    return assignment


async def revoke_role(
    db: AsyncSession,
    *,
    guard: Authorized,
    user_id: uuid.UUID,
    payload: schemas.RevokeRoleRequest,
    meta: RequestMeta,
) -> None:
    scope = _scope_of(payload.institute_id, payload.branch_id)
    await guard.ensure(scope)

    role = await _require_role(db, payload.role_key)
    guard.ensure_can_grant(role.rank, scope)

    assignment = await rbac_repo.find_assignment(
        db,
        user_id=user_id,
        role_id=role.id,
        institute_id=scope.institute_id,
        branch_id=scope.branch_id,
    )
    if assignment is None:
        raise NotFound("That person does not hold this role here.")

    await _guard_last_super_admin(db, role)

    assignment.revoked_at = datetime.now(UTC)
    assignment.revoked_by = guard.user_id
    rbac.invalidate_context(user_id)

    audit.record(
        db,
        action=events.ROLE_REVOKED,
        actor_user_id=guard.user_id,
        target_type="user",
        target_id=user_id,
        institute_id=scope.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"role_key": role.key},
    )
    await db.commit()


async def _guard_last_super_admin(db: AsyncSession, role) -> None:
    """PRD §3: "At least one Super Admin must always exist".

    "Exist" has to mean "can sign in". An invited Super Admin who has not yet set a
    password holds the role but cannot use it, so counting them would let the last working
    administrator revoke their own access and leave nobody able to administer the platform.
    """
    from app.modules.rbac.catalog import SUPER_ADMIN

    if role.key != SUPER_ADMIN:
        return
    if await rbac_repo.count_usable_role_holders(db, role.id) <= 1:
        raise Conflict(
            "There must always be at least one Super Admin who can sign in. "
            "Ask the other Super Admin to set their password first."
        )


# ------------------------------------------------------------------------------ status


async def update_status(
    db: AsyncSession,
    *,
    guard: Authorized,
    user_id: uuid.UUID,
    payload: schemas.UpdateStatusRequest,
    meta: RequestMeta,
) -> User:
    """Suspend or re-activate. Suspension revokes every session immediately (PRD §13.9)."""
    if user_id == guard.user_id:
        raise Forbidden("You cannot change your own account status.")

    user = await _require_visible_user(db, guard, user_id)
    target_rank = await _highest_rank_of(db, user_id)
    scope = await _primary_scope_of(db, user_id)
    guard.ensure_can_grant(target_rank, scope)

    if payload.status == "suspended":
        user.status = "suspended"
        await auth_repo.revoke_all_user_tokens(db, user.id, "suspended")
        action = events.USER_SUSPENDED
    else:
        # An invited user who never set a password must not jump straight to active.
        user.status = "active" if user.password_hash else "invited"
        user.failed_login_count = 0
        user.locked_until = None
        action = events.USER_REACTIVATED

    rbac.invalidate_context(user.id)
    audit.record(
        db,
        action=action,
        actor_user_id=guard.user_id,
        target_type="user",
        target_id=user.id,
        institute_id=scope.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"reason": payload.reason} if payload.reason else None,
    )
    await db.commit()
    return user


async def _highest_rank_of(db: AsyncSession, user_id: uuid.UUID) -> int:
    context = await rbac.get_context(db, user_id)
    return context.max_rank


async def _primary_scope_of(db: AsyncSession, user_id: uuid.UUID) -> Scope:
    """The scope a user's actions are audited against. Their first live assignment is a
    good enough answer; a user with roles in several institutes is rare and the audit row
    records the acting admin anyway."""
    assignments = await rbac_repo.live_assignments_for_user(db, user_id)
    if not assignments:
        return Scope()
    first = assignments[0]
    return Scope(institute_id=first.institute_id, branch_id=first.branch_id)


# -------------------------------------------------------------------------- reading


async def _require_visible_user(db: AsyncSession, guard: Authorized, user_id: uuid.UUID) -> User:
    """404, not 403, when the target is outside the caller's scope.

    Returning 403 would confirm the account exists, which is a cross-tenant information
    leak (PRD §13 criterion 8).
    """
    user = await repo.get_user(db, user_id)
    if user is None or user.status == "deleted":
        raise NotFound("That user does not exist.")

    if guard.context.is_platform_staff:
        return user

    target_scope = await _primary_scope_of(db, user_id)
    if not any(s.contains(target_scope) for s in guard.context.scopes_for(guard.permission)):
        raise NotFound("That user does not exist.")
    return user


async def get_user(db: AsyncSession, *, guard: Authorized, user_id: uuid.UUID) -> User:
    return await _require_visible_user(db, guard, user_id)


async def list_users(
    db: AsyncSession,
    *,
    guard: Authorized,
    search: str | None,
    status: str | None,
    role_key: str | None,
    institute_id: uuid.UUID | None,
    cursor: str | None,
    limit: int,
) -> tuple[Sequence[User], str | None]:
    """Scope the query to what the caller may see, then let PostgreSQL do the filtering.

    ``usable_scopes`` rather than the raw grants: an explicit deny has to narrow
    the list as well as the per-row check, or the rows somebody blocked show up anyway.
    """
    scopes = guard.usable_scopes()
    role_keys = {a.role_key for a in guard.context.assignments}

    # Faculty see only students of the classes they teach.
    if role_keys and role_keys <= {FACULTY, STUDENT}:
        class_ids = await rbac_repo.faculty_class_ids(db, guard.user_id)
        user_ids = await _students_in_classes(db, class_ids)
        return await repo.list_users(
            db,
            institute_ids=None,
            user_ids=user_ids | {guard.user_id},
            search=search,
            status=status,
            role_key=role_key,
            cursor=cursor,
            limit=limit,
        )

    platform_wide = guard.context.is_platform_staff and any(s.institute_id is None for s in scopes)
    if platform_wide:
        institute_ids = frozenset({institute_id}) if institute_id else None
        branch_ids = None
    else:
        institute_ids = frozenset(s.institute_id for s in scopes if s.institute_id)
        if institute_id:
            if institute_id not in institute_ids:
                raise Forbidden()
            institute_ids = frozenset({institute_id})
        branch_scoped = [s for s in scopes if s.branch_id]
        institute_wide = any(s.institute_id and s.branch_id is None for s in scopes)
        branch_ids = (
            None if institute_wide else frozenset(s.branch_id for s in branch_scoped if s.branch_id)
        )

    return await repo.list_users(
        db,
        institute_ids=institute_ids,
        branch_ids=branch_ids,
        search=search,
        status=status,
        role_key=role_key,
        cursor=cursor,
        limit=limit,
    )


async def _students_in_classes(
    db: AsyncSession, class_ids: frozenset[uuid.UUID]
) -> frozenset[uuid.UUID]:
    if not class_ids:
        return frozenset()
    from sqlalchemy import select

    from app.modules.org.models import ClassEnrollment

    result = await db.execute(
        select(ClassEnrollment.student_user_id).where(
            ClassEnrollment.class_id.in_(class_ids),
            ClassEnrollment.status == "active",
        )
    )
    return frozenset(result.scalars())


async def attach_roles(
    db: AsyncSession, users: Sequence[User]
) -> dict[uuid.UUID, list[schemas.RoleAssignmentOut]]:
    """One query for a whole page of users — see ``repository.roles_for_users``."""
    grouped = await repo.roles_for_users(db, [u.id for u in users])
    return {
        user_id: [
            schemas.RoleAssignmentOut(
                role_key=key,
                role_name=name,
                rank=rank,
                institute_id=inst,
                branch_id=branch,
                institute_name=inst_name,
                branch_name=branch_name,
            )
            for key, name, rank, inst, branch, inst_name, branch_name in rows
        ]
        for user_id, rows in grouped.items()
    }


# ------------------------------------------------------------- profile and preferences


async def update_profile(
    db: AsyncSession, *, user: User, payload: schemas.UpdateProfileRequest
) -> User:
    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changed.items():
        setattr(user, field, value)
    await db.commit()
    return user


async def update_preferences(
    db: AsyncSession, *, user_id: uuid.UUID, payload: schemas.UpdatePreferencesRequest
) -> UserPreference:
    """Theme follows the user across devices (PRD §4.6, §13 criterion 10)."""
    preferences = await repo.upsert_preferences(db, user_id)
    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changed.items():
        setattr(preferences, field, value)
    await db.commit()
    return preferences


async def build_me(db: AsyncSession, user: User) -> schemas.MeOut:
    context = await rbac.get_context(db, user.id)
    preferences = await repo.upsert_preferences(db, user.id)
    named = await attach_roles(db, [user])
    by_scope = {(r.role_key, r.institute_id, r.branch_id): r for r in named.get(user.id, [])}
    return schemas.MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        status=user.status,
        permissions=sorted(context.permissions),
        roles=[
            by_scope.get(
                (a.role_key, a.scope.institute_id, a.scope.branch_id),
                schemas.RoleAssignmentOut(
                    role_key=a.role_key,
                    role_name=a.role_name,
                    rank=a.rank,
                    institute_id=a.scope.institute_id,
                    branch_id=a.scope.branch_id,
                ),
            )
            for a in context.assignments
        ],
        institute_ids=sorted(context.institute_ids),
        preferences=schemas.PreferencesOut.model_validate(preferences),
    )


# ---------------------------------------------------------------------- overview


async def build_overview(db: AsyncSession, *, guard: Authorized) -> schemas.OverviewOut:
    """Real counts for the dashboard tiles, over exactly the caller's scope.

    These are COUNTs, not the length of a first page: a tile reading "20 people" for an
    institute with four hundred would be worse than no tile at all.
    """
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.modules.audit.models import AuditLog
    from app.modules.org.models import Institute

    scopes = guard.context.scopes_for(guard.permission)
    platform = guard.context.is_platform_staff
    institute_ids = frozenset(s.institute_id for s in scopes if s.institute_id)

    base = select(func.count()).select_from(User).where(User.status != "deleted")
    if not platform:
        if not institute_ids:
            return schemas.OverviewOut(
                users_total=0,
                users_active=0,
                users_invited=0,
                users_suspended=0,
                institutes_total=0,
                security_events_24h=0,
            )
        branch_scoped = [s for s in scopes if s.branch_id]
        institute_wide = any(s.institute_id and s.branch_id is None for s in scopes)
        branch_ids = (
            None if institute_wide else frozenset(s.branch_id for s in branch_scoped if s.branch_id)
        )
        base = base.where(repo._scope_filter(institute_ids=institute_ids, branch_ids=branch_ids))

    async def count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    total = await count(base)
    active = await count(base.where(User.status == "active"))
    invited = await count(base.where(User.status == "invited"))
    suspended = await count(base.where(User.status == "suspended"))

    institutes_stmt = select(func.count()).select_from(Institute)
    if not platform:
        institutes_stmt = institutes_stmt.where(Institute.id.in_(institute_ids))
    institutes = await count(institutes_stmt)

    since = datetime.now(UTC) - timedelta(hours=24)
    events_stmt = (
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.created_at >= since,
            AuditLog.action.in_(("login_failure", "account_locked", "token_reuse_detected")),
        )
    )
    if not platform:
        events_stmt = events_stmt.where(AuditLog.institute_id.in_(institute_ids))

    return schemas.OverviewOut(
        users_total=total,
        users_active=active,
        users_invited=invited,
        users_suspended=suspended,
        institutes_total=institutes,
        security_events_24h=await count(events_stmt),
    )
