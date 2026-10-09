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
    # An institute-level role granted *with* a branch is allowed on purpose, and it is
    # load-bearing. `scope_level` is the widest a role may reach, not the only shape it may
    # take. A Branch Admin inviting a Student names their branch because that is where
    # their own authority is; demand institute scope instead and `guard.ensure` refuses
    # them, so Branch Admins and Faculty could not invite students at all. The assignment
    # that results is *narrower* than institute-wide, which is the safe direction to err.
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


def _require_platform_admin_authority(guard: Authorized, role) -> None:
    """`platform_admin:manage` actually gates something now.

    It was in the catalogue, granted to Super Admin, shown in the permission matrix — and
    checked nowhere. What really stopped a Platform Admin minting another was the rank
    ceiling, which is a different rule that happens to have the same effect today. A
    permission nobody enforces is worse than one that does not exist: an administrator
    toggling that cell believes they have changed who can appoint platform staff, and they
    have not.
    """
    if role.key != "platform_admin":
        return
    if not guard.context.holds("platform_admin:manage"):
        raise Forbidden("Only a Super Admin can add or remove Platform Admins.")


def _refuse_platform_role_for_unproven_account(role, user: User) -> None:
    """The other half of the invitation rule, and without it that rule is decorative.

    Refusing platform roles on `invite` is pointless if the same account can be invited as
    a Student and promoted a second later: the account still belongs to an address nobody
    has proved they control, and whoever reads that mailbox completes the password setup
    and owns the platform. The restriction is not about which endpoint is used — it is
    about whether the person on the other end has demonstrated they are there.

    "Proved" means exactly two things: the account is active, and a password has been set.
    Both only become true after somebody received the setup code at that address and used
    it.
    """
    if role.scope_level != "platform":
        return
    if user.status != "active" or user.password_hash is None:
        raise ValidationFailed(
            f"{role.name} can only be given to an account that is already active. "
            "Ask the person to finish setting their password first."
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
    _require_platform_admin_authority(guard, role)

    user = await repo.get_user(db, user_id)
    if user is None or user.status == "deleted":
        raise NotFound("That user does not exist.")
    _refuse_platform_role_for_unproven_account(role, user)

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

    # Taking a role away is restrained by rank too, but one step more loosely than giving
    # one: equal rank is allowed, because removing a role hands the caller nothing. The
    # strict rule would have left a compromised Super Admin account with no one able to
    # strip its access — see `Authorized.ensure_can_restrain`.
    #
    # Standing down from your own role needs no check at all; it only ever reduces what
    # the person doing it can do. `_guard_last_super_admin` below still stops the final
    # working Super Admin from leaving nobody in charge.
    if user_id != guard.user_id:
        guard.ensure_can_restrain(role.rank, scope)

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
    user = await _apply_status(
        db,
        guard=guard,
        user_id=user_id,
        status=payload.status,
        reason=payload.reason,
        meta=meta,
    )
    await db.commit()
    return user


async def _apply_status(
    db: AsyncSession,
    *,
    guard: Authorized,
    user_id: uuid.UUID,
    status: str,
    reason: str | None,
    meta: RequestMeta,
) -> User:
    """Every rule that governs changing somebody's status, in one place.

    Single and bulk both go through here, which is the point: a bulk endpoint that
    re-implements the checks is a bulk endpoint that will eventually disagree with the
    single one, and the disagreement will be in the permissive direction.

    Raises rather than returning a verdict, so the single endpoint gets its 403/404 for
    free and the bulk caller can turn each exception into a per-user reason.

    Does not commit. The caller decides the transaction boundary — one row or a hundred.
    """
    if user_id == guard.user_id:
        raise Forbidden("You cannot change your own account status.")

    user = await _require_visible_user(db, guard, user_id)
    target_rank = await _highest_rank_of(db, user_id)
    scope = await _primary_scope_of(db, user_id)

    # The full authorization check, not just rank. `require_permission` only proved the
    # caller holds `user:update_status` *somewhere*; this is where the target scope is
    # known, and it is what applies the deny layer (ADR-017) and the module-enabled test.
    # Without it an explicit block on a branch is ignored by this endpoint while the list
    # endpoints honour it — the block looks applied and is not.
    await guard.ensure(scope)
    # `restrain`, not `grant`: suspending an account only ever reduces what somebody can
    # do, so it is allowed against an equal rank. The grant rule would mean a Super Admin
    # whose password was stolen could not be shut down by the other Super Admins.
    guard.ensure_can_restrain(target_rank, scope)

    if status == "suspended":
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
        extra={"reason": reason} if reason else None,
    )
    return user


async def bulk_update_status(
    db: AsyncSession,
    *,
    guard: Authorized,
    payload: schemas.BulkStatusRequest,
    meta: RequestMeta,
) -> list[schemas.BulkStatusResult]:
    """Apply a status change to many people, checking each one individually.

    Deliberately **not** all-or-nothing. An administrator selecting thirty students should
    not have the whole action fail because one of them turned out to be a colleague they
    may not touch — they would have no way to tell which one, and would end up unpicking
    the selection by hand. Each person is judged on their own and the caller is told
    exactly who was skipped and why.

    Every refusal is a reason somebody can act on, never a bare "failed": the message is
    the same one the single endpoint would have given.
    """
    results: list[schemas.BulkStatusResult] = []

    for user_id in payload.user_ids:
        try:
            user = await _apply_status(
                db,
                guard=guard,
                user_id=user_id,
                status=payload.status,
                reason=payload.reason,
                meta=meta,
            )
        except (Forbidden, NotFound, Conflict, ValidationFailed) as refusal:
            # A refusal is a verdict on one person, not a failure of the request. Nothing
            # was written for them, so the rest of the batch is unaffected.
            results.append(
                schemas.BulkStatusResult(
                    user_id=user_id, outcome="skipped", reason=str(refusal.message)
                )
            )
        else:
            results.append(
                schemas.BulkStatusResult(
                    user_id=user_id, outcome="succeeded", email=user.email, reason=None
                )
            )

    await db.commit()
    return results


async def _highest_rank_of(db: AsyncSession, user_id: uuid.UUID) -> int:
    context = await rbac.get_context(db, user_id)
    return context.max_rank


async def _live_scopes_of(db: AsyncSession, user_id: uuid.UUID) -> list[Scope]:
    """Every scope this person currently holds a role at."""
    assignments = await rbac_repo.live_assignments_for_user(db, user_id)
    return [Scope(institute_id=a.institute_id, branch_id=a.branch_id) for a in assignments]


async def _primary_scope_of(db: AsyncSession, user_id: uuid.UUID) -> Scope:
    """The scope a user's actions are audited against.

    Their most senior assignment, deliberately — not whichever row the database happened to
    return first. ``live_assignments_for_user`` has no ``ORDER BY``, so "the first one" is
    not a stable answer, and this value decides both the audit row's institute and, through
    ``ensure_can_grant``, whether an action is permitted at all. Two calls disagreeing is
    the kind of fault that shows up once a month and never reproduces.
    """
    assignments = await rbac_repo.live_assignments_for_user(db, user_id)
    if not assignments:
        return Scope()

    roles = {r.id: r for r in await rbac_repo.list_roles(db, include_inactive=True)}
    senior = max(assignments, key=lambda a: roles[a.role_id].rank if a.role_id in roles else 0)
    return Scope(institute_id=senior.institute_id, branch_id=senior.branch_id)


# -------------------------------------------------------------------------- reading


async def _require_visible_user(db: AsyncSession, guard: Authorized, user_id: uuid.UUID) -> User:
    """404, not 403, when the target is outside the caller's scope.

    Returning 403 would confirm the account exists, which is a cross-tenant information
    leak (PRD §13 criterion 8).
    """
    user = await repo.get_user(db, user_id)
    if user is None or user.status == "deleted":
        raise NotFound("That user does not exist.")

    # Every scope the target holds a role at, not one arbitrarily chosen. Picking one made
    # visibility depend on database row order: a person with roles in two institutes could
    # be listed by `list_users` (which tests all their assignments) and then 404 when
    # opened, intermittently, for the same caller.
    target_scopes = await _live_scopes_of(db, user_id)
    if not target_scopes:
        target_scopes = [Scope()]

    # `usable_scopes`, not the raw grants. An explicit deny (ADR-017) has to narrow who is
    # visible as well as what may be done to them — a deny the per-row check honours but
    # this one ignores is a deny that leaks exactly the people it was created to hide.
    # Platform staff hold a platform-level grant, which covers every scope, so they need
    # no special case here; giving them one would skip their denies too.
    mine = guard.usable_scopes()
    if not any(s.contains(target) for s in mine for target in target_scopes):
        raise NotFound("That user does not exist.")
    return user


async def get_user(db: AsyncSession, *, guard: Authorized, user_id: uuid.UUID) -> User:
    return await _require_visible_user(db, guard, user_id)


def _visible_scope(guard: Authorized, scopes, institute_id: uuid.UUID | None) -> repo.VisibleScope:
    """Turn the caller's scopes into "which institute, and which branches of it".

    One entry per institute, each mapped to the branches held there — or ``None`` when the
    caller holds that institute as a whole. Keeping them separate is the point: somebody
    who runs one college and one branch of another must not have the branch restriction
    lifted on the second college just because the first one is theirs entirely.

    ``None`` is returned for platform staff with a platform-wide scope, meaning everybody.
    """
    platform_wide = guard.context.is_platform_staff and any(s.institute_id is None for s in scopes)
    if platform_wide:
        return {institute_id: None} if institute_id else None

    scope: dict[uuid.UUID, frozenset[uuid.UUID] | None] = {}
    for s in scopes:
        if s.institute_id is None:
            continue
        if s.branch_id is None:
            # The whole institute. Overwrites any branch set already collected for it,
            # and the `None` below stops a later branch-scoped entry narrowing it again.
            scope[s.institute_id] = None
        elif scope.get(s.institute_id, frozenset()) is not None:
            scope[s.institute_id] = (scope.get(s.institute_id) or frozenset()) | {s.branch_id}

    if institute_id:
        if institute_id not in scope:
            raise Forbidden()
        return {institute_id: scope[institute_id]}
    return scope


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
    include_total: bool = True,
) -> tuple[Sequence[User], str | None, int]:
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
            scope=None,
            user_ids=user_ids | {guard.user_id},
            search=search,
            status=status,
            role_key=role_key,
            cursor=cursor,
            limit=limit,
            include_total=include_total,
        )

    return await repo.list_users(
        db,
        scope=_visible_scope(guard, scopes, institute_id),
        search=search,
        status=status,
        role_key=role_key,
        cursor=cursor,
        limit=limit,
        include_total=include_total,
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

    # `usable_scopes`, not raw grants: a deny has to narrow the counts as well as the
    # rows, or the tiles quietly report on people the caller may not see.
    scopes = guard.usable_scopes()

    # Exactly the test `list_users` applies, and for the same reason. Holding platform
    # staff *status* is not enough on its own: an explicit deny on `user:read` removes the
    # platform scope from `usable_scopes` entirely, and a Platform Admin blocked that way
    # correctly sees no rows in the user list — while this tile went on reporting the
    # platform-wide total. "There are four hundred users" told to somebody allowed to see
    # none of them is the same leak in a smaller box.
    scope = _visible_scope(guard, scopes, None)
    institute_ids = frozenset(scope) if scope is not None else frozenset()

    base = select(func.count()).select_from(User).where(User.status != "deleted")
    if scope is not None:
        if not scope:
            return schemas.OverviewOut(
                users_total=0,
                users_active=0,
                users_invited=0,
                users_suspended=0,
                institutes_total=0,
                security_events_24h=0,
            )
        base = base.where(repo.visible_users_filter(scope))

    async def count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    total = await count(base)
    active = await count(base.where(User.status == "active"))
    invited = await count(base.where(User.status == "invited"))
    suspended = await count(base.where(User.status == "suspended"))

    institutes_stmt = select(func.count()).select_from(Institute)
    if scope is not None:
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
    if scope is not None:
        events_stmt = events_stmt.where(AuditLog.institute_id.in_(institute_ids))

    return schemas.OverviewOut(
        users_total=total,
        users_active=active,
        users_invited=invited,
        users_suspended=suspended,
        institutes_total=institutes,
        security_events_24h=await count(events_stmt),
    )
