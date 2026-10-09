"""Organisation hierarchy use cases (PRD §2, §8).

Two invariants are enforced here and nowhere else:

* **Nothing is hard-deleted.** Archive moves a status; the rows and their history stay.
* **Every lookup is tenant-qualified.** A caller asking for a branch must say which
  institute it belongs to, so a wrong-tenant id returns 404 rather than someone else's data.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.modules.audit import events
from app.modules.audit import service as audit
from app.modules.auth.service import RequestMeta
from app.modules.org import repository as repo
from app.modules.org import schemas
from app.modules.org.models import (
    AcademicSession,
    Branch,
    Class,
    ClassEnrollment,
    ClassFaculty,
    Institute,
)
from app.modules.rbac.scopes import Scope
from app.modules.rbac.service import Authorized


async def _require_institute(db: AsyncSession, institute_id: uuid.UUID) -> Institute:
    institute = await repo.get_institute(db, institute_id)
    if institute is None:
        raise NotFound("That institute does not exist.")
    return institute


async def _require_branch(
    db: AsyncSession, institute_id: uuid.UUID, branch_id: uuid.UUID
) -> Branch:
    branch = await repo.get_branch(db, branch_id, institute_id=institute_id)
    if branch is None:
        raise NotFound("That branch does not exist.")
    return branch


async def _require_class(db: AsyncSession, class_id: uuid.UUID) -> Class:
    found = await repo.get_class(db, class_id)
    if found is None:
        raise NotFound("That class does not exist.")
    return found


# --------------------------------------------------------------------------- institutes


async def create_institute(
    db: AsyncSession, *, guard: Authorized, payload: schemas.InstituteCreate, meta: RequestMeta
) -> Institute:
    await guard.ensure(Scope())  # institute:create is platform-only (PRD §5.3)

    if await repo.institute_code_taken(db, payload.code):
        raise Conflict("An institute with that code already exists.")

    institute = Institute(
        name=payload.name,
        code=payload.code,
        type=payload.type,
        contact_email=payload.contact_email,
        logo_url=payload.logo_url,
        status="active",
    )
    db.add(institute)
    await db.flush()

    await enable_core_modules(db, institute.id)
    audit.record(
        db,
        action=events.INSTITUTE_CREATED,
        actor_user_id=guard.user_id,
        target_type="institute",
        target_id=institute.id,
        institute_id=institute.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"code": institute.code, "type": institute.type},
    )
    return institute


async def enable_core_modules(db: AsyncSession, institute_id: uuid.UUID) -> None:
    """Core is on for every institute from the moment it exists — auth, org and users are
    not optional extras (PRD §5.2 step 5)."""
    from app.modules.rbac.catalog import CORE_MODULE
    from app.modules.rbac.models import InstituteModule

    db.add(InstituteModule(institute_id=institute_id, module_key=CORE_MODULE, enabled=True))


async def update_institute(
    db: AsyncSession,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    payload: schemas.InstituteUpdate,
    meta: RequestMeta,
) -> Institute:
    await guard.ensure(Scope(institute_id=institute_id))
    institute = await _require_institute(db, institute_id)

    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changed.items():
        setattr(institute, field, value)

    audit.record(
        db,
        action=events.INSTITUTE_UPDATED,
        actor_user_id=guard.user_id,
        target_type="institute",
        target_id=institute.id,
        institute_id=institute.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"fields": sorted(changed)},
    )
    return institute


async def archive_institute(
    db: AsyncSession, *, guard: Authorized, institute_id: uuid.UUID, meta: RequestMeta
) -> Institute:
    await guard.ensure(Scope())
    institute = await _require_institute(db, institute_id)
    if institute.is_system:
        raise Forbidden("The built-in Direct institute cannot be archived.")

    institute.status = "archived"
    audit.record(
        db,
        action=events.INSTITUTE_ARCHIVED,
        actor_user_id=guard.user_id,
        target_type="institute",
        target_id=institute.id,
        institute_id=institute.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    return institute


async def list_institutes(
    db: AsyncSession,
    *,
    guard: Authorized,
    search: str | None,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[Sequence[Institute], str | None, int]:
    """Platform staff see everything; everyone else sees only institutes they hold a role in.

    Derived from the permission's own usable scopes, so a deny on ``institute:read``
    removes that institute from the list instead of only from the detail endpoint.
    """
    visible = guard.visible_institute_ids()
    return await repo.list_institutes(
        db, visible_ids=visible, search=search, status=status, cursor=cursor, limit=limit
    )


async def get_institute(
    db: AsyncSession, *, guard: Authorized, institute_id: uuid.UUID
) -> Institute:
    await guard.ensure(Scope(institute_id=institute_id))
    return await _require_institute(db, institute_id)


# ----------------------------------------------------------------------------- branches


async def create_branch(
    db: AsyncSession,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    payload: schemas.BranchCreate,
    meta: RequestMeta,
) -> Branch:
    await guard.ensure(Scope(institute_id=institute_id))
    await _require_institute(db, institute_id)

    if await repo.branch_code_taken(db, institute_id, payload.code):
        raise Conflict("A branch with that code already exists in this institute.")

    branch = Branch(
        institute_id=institute_id,
        name=payload.name,
        code=payload.code,
        city=payload.city,
        address=payload.address,
    )
    db.add(branch)
    await db.flush()

    audit.record(
        db,
        action=events.BRANCH_CREATED,
        actor_user_id=guard.user_id,
        target_type="branch",
        target_id=branch.id,
        institute_id=institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"code": branch.code},
    )
    return branch


async def update_branch(
    db: AsyncSession,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    branch_id: uuid.UUID,
    payload: schemas.BranchUpdate,
    meta: RequestMeta,
) -> Branch:
    await guard.ensure(Scope(institute_id=institute_id, branch_id=branch_id))
    branch = await _require_branch(db, institute_id, branch_id)

    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    archiving = changed.get("status") == "archived" and branch.status != "archived"
    for field, value in changed.items():
        setattr(branch, field, value)

    audit.record(
        db,
        action=events.BRANCH_ARCHIVED if archiving else events.BRANCH_UPDATED,
        actor_user_id=guard.user_id,
        target_type="branch",
        target_id=branch.id,
        institute_id=institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"fields": sorted(changed)},
    )
    return branch


async def list_branches(
    db: AsyncSession,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[Sequence[Branch], str | None, int]:
    # Listing is authorised by holding the permission *somewhere inside* this institute;
    # the result is then narrowed to exactly the branches those grants cover.
    scopes = await guard.ensure_within(institute_id)
    branch_ids = (
        None
        if guard.covers_whole_institute(scopes, institute_id)
        else frozenset(s.branch_id for s in scopes if s.branch_id)
    )
    return await repo.list_branches(
        db,
        institute_id=institute_id,
        branch_ids=branch_ids,
        status=status,
        cursor=cursor,
        limit=limit,
    )


# --------------------------------------------------------------------- academic sessions


async def create_session(
    db: AsyncSession,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    payload: schemas.AcademicSessionCreate,
    meta: RequestMeta,
) -> AcademicSession:
    await guard.ensure(Scope(institute_id=institute_id))
    await _require_institute(db, institute_id)

    if await repo.session_name_taken(db, institute_id, payload.name):
        raise Conflict("An academic session with that name already exists.")

    if payload.is_current:
        await repo.clear_current_session(db, institute_id)

    session = AcademicSession(
        institute_id=institute_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_current=payload.is_current,
    )
    db.add(session)
    await db.flush()

    audit.record(
        db,
        action=events.SESSION_CREATED,
        actor_user_id=guard.user_id,
        target_type="academic_session",
        target_id=session.id,
        institute_id=institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    return session


async def update_session(
    db: AsyncSession,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: schemas.AcademicSessionUpdate,
    meta: RequestMeta,
) -> AcademicSession:
    await guard.ensure(Scope(institute_id=institute_id))
    session = await repo.get_session(db, session_id, institute_id=institute_id)
    if session is None:
        raise NotFound("That academic session does not exist.")

    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    if changed.get("is_current"):
        await repo.clear_current_session(db, institute_id)
    for field, value in changed.items():
        setattr(session, field, value)

    _validate_session_dates(session.start_date, session.end_date)

    audit.record(
        db,
        action=events.SESSION_UPDATED,
        actor_user_id=guard.user_id,
        target_type="academic_session",
        target_id=session.id,
        institute_id=institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"fields": sorted(changed)},
    )
    return session


def _validate_session_dates(start: date, end: date) -> None:
    if end < start:
        raise ValidationFailed("End date cannot be before the start date.")


async def list_sessions(
    db: AsyncSession, *, guard: Authorized, institute_id: uuid.UUID, cursor: str | None, limit: int
) -> tuple[Sequence[AcademicSession], str | None, int]:
    await guard.ensure_within(institute_id)
    return await repo.list_sessions(db, institute_id=institute_id, cursor=cursor, limit=limit)


# ------------------------------------------------------------------------------ classes


async def create_class(
    db: AsyncSession,
    *,
    guard: Authorized,
    branch_id: uuid.UUID,
    payload: schemas.ClassCreate,
    meta: RequestMeta,
) -> Class:
    branch = await repo.get_branch(db, branch_id)
    if branch is None:
        raise NotFound("That branch does not exist.")
    await guard.ensure(Scope(institute_id=branch.institute_id, branch_id=branch_id))

    session = await repo.get_session(
        db, payload.academic_session_id, institute_id=branch.institute_id
    )
    if session is None:
        raise ValidationFailed("That academic session does not belong to this institute.")

    if await repo.class_code_taken(db, branch_id, session.id, payload.code):
        raise Conflict("A class with that code already exists in this branch and session.")

    new_class = Class(
        institute_id=branch.institute_id,
        branch_id=branch_id,
        academic_session_id=session.id,
        name=payload.name,
        code=payload.code,
        section=payload.section,
    )
    db.add(new_class)
    await db.flush()

    audit.record(
        db,
        action=events.CLASS_CREATED,
        actor_user_id=guard.user_id,
        target_type="class",
        target_id=new_class.id,
        institute_id=branch.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"code": new_class.code, "branch_id": str(branch_id)},
    )
    return new_class


async def update_class(
    db: AsyncSession,
    *,
    guard: Authorized,
    class_id: uuid.UUID,
    payload: schemas.ClassUpdate,
    meta: RequestMeta,
) -> Class:
    target = await _require_class(db, class_id)
    await guard.ensure(Scope(institute_id=target.institute_id, branch_id=target.branch_id))

    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    archiving = changed.get("status") == "archived" and target.status != "archived"
    for field, value in changed.items():
        setattr(target, field, value)

    audit.record(
        db,
        action=events.CLASS_ARCHIVED if archiving else events.CLASS_UPDATED,
        actor_user_id=guard.user_id,
        target_type="class",
        target_id=target.id,
        institute_id=target.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"fields": sorted(changed)},
    )
    return target


async def list_classes(
    db: AsyncSession,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[Sequence[Class], str | None, int]:
    """Faculty and students see only the classes they are linked to (PRD §5.3 ``class:read``)."""
    from app.modules.rbac import repository as rbac_repo
    from app.modules.rbac.catalog import FACULTY, STUDENT

    scopes = await guard.ensure_within(institute_id)

    # Narrow to the branches the caller's grants cover, unless they asked for one
    # explicitly — in which case it must be inside those grants.
    if not guard.covers_whole_institute(scopes, institute_id):
        allowed_branches = frozenset(s.branch_id for s in scopes if s.branch_id)
        if branch_id is not None and branch_id not in allowed_branches:
            raise Forbidden()
        if branch_id is None and len(allowed_branches) == 1:
            branch_id = next(iter(allowed_branches))

    role_keys = {a.role_key for a in guard.context.assignments}
    class_ids: frozenset[uuid.UUID] | None = None
    if role_keys and role_keys <= {FACULTY, STUDENT}:
        class_ids = frozenset()
        if FACULTY in role_keys:
            class_ids |= await rbac_repo.faculty_class_ids(db, guard.user_id)
        if STUDENT in role_keys:
            class_ids |= await rbac_repo.student_class_ids(db, guard.user_id)

    return await repo.list_classes(
        db,
        institute_id=institute_id,
        branch_id=branch_id,
        session_id=session_id,
        class_ids=class_ids,
        status=status,
        cursor=cursor,
        limit=limit,
    )


# ------------------------------------------------------------- faculty and enrolment


async def assign_faculty(
    db: AsyncSession,
    *,
    guard: Authorized,
    class_id: uuid.UUID,
    payload: schemas.ClassFacultyCreate,
    meta: RequestMeta,
) -> ClassFaculty:
    target = await _require_class(db, class_id)
    await guard.ensure(Scope(institute_id=target.institute_id, branch_id=target.branch_id))
    await _require_user_in_institute(db, payload.user_id, target.institute_id)

    existing = await repo.get_class_faculty(db, class_id, payload.user_id)
    if existing is not None:
        raise Conflict("That person is already assigned to this class.")

    link = ClassFaculty(
        class_id=class_id,
        faculty_user_id=payload.user_id,
        subject=payload.subject,
        is_class_teacher=payload.is_class_teacher,
    )
    db.add(link)
    await db.flush()

    audit.record(
        db,
        action=events.FACULTY_ASSIGNED,
        actor_user_id=guard.user_id,
        target_type="class",
        target_id=class_id,
        institute_id=target.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"faculty_user_id": str(payload.user_id)},
    )
    return link


async def remove_faculty(
    db: AsyncSession,
    *,
    guard: Authorized,
    class_id: uuid.UUID,
    user_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    target = await _require_class(db, class_id)
    await guard.ensure(Scope(institute_id=target.institute_id, branch_id=target.branch_id))

    link = await repo.get_class_faculty(db, class_id, user_id)
    if link is None:
        raise NotFound("That person is not assigned to this class.")

    # A link row, not a core entity: removing it is correct, and the audit row is the history.
    await db.delete(link)
    audit.record(
        db,
        action=events.FACULTY_REMOVED,
        actor_user_id=guard.user_id,
        target_type="class",
        target_id=class_id,
        institute_id=target.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"faculty_user_id": str(user_id)},
    )


async def enrol_student(
    db: AsyncSession,
    *,
    guard: Authorized,
    class_id: uuid.UUID,
    payload: schemas.EnrollmentCreate,
    meta: RequestMeta,
) -> ClassEnrollment:
    """Faculty may only enrol into classes they teach — ``ensure_class`` applies that check."""
    target = await _require_class(db, class_id)
    await guard.ensure(
        Scope(institute_id=target.institute_id, branch_id=target.branch_id), class_id=class_id
    )
    await _require_user_in_institute(db, payload.user_id, target.institute_id)

    existing = await repo.get_enrollment(db, class_id, payload.user_id)
    if existing is not None:
        if existing.status == "active":
            raise Conflict("That student is already enrolled in this class.")
        # Re-enrolling someone who left reuses the row, keeping one history per pair.
        existing.status = "active"
        existing.roll_no = payload.roll_no or existing.roll_no
        _record_enrolment(db, guard, target, payload.user_id, meta, events.STUDENT_ENROLLED)
        return existing

    enrollment = ClassEnrollment(
        class_id=class_id,
        student_user_id=payload.user_id,
        roll_no=payload.roll_no,
        status="active",
    )
    db.add(enrollment)
    await db.flush()
    _record_enrolment(db, guard, target, payload.user_id, meta, events.STUDENT_ENROLLED)
    return enrollment


async def unenrol_student(
    db: AsyncSession,
    *,
    guard: Authorized,
    class_id: uuid.UUID,
    user_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    """Marks the enrolment as left. The row stays — moving classes keeps history (PRD §2)."""
    target = await _require_class(db, class_id)
    await guard.ensure(
        Scope(institute_id=target.institute_id, branch_id=target.branch_id), class_id=class_id
    )

    enrollment = await repo.get_enrollment(db, class_id, user_id)
    if enrollment is None or enrollment.status != "active":
        raise NotFound("That student is not enrolled in this class.")

    enrollment.status = "left"
    _record_enrolment(db, guard, target, user_id, meta, events.STUDENT_UNENROLLED)


def _record_enrolment(
    db: AsyncSession,
    guard: Authorized,
    target: Class,
    student_id: uuid.UUID,
    meta: RequestMeta,
    action: str,
) -> None:
    audit.record(
        db,
        action=action,
        actor_user_id=guard.user_id,
        target_type="class",
        target_id=target.id,
        institute_id=target.institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"student_user_id": str(student_id)},
    )


async def _require_user_in_institute(
    db: AsyncSession, user_id: uuid.UUID, institute_id: uuid.UUID
) -> None:
    """Cross-tenant guard: you cannot attach a user from another institute to your class."""
    from sqlalchemy import exists, select

    from app.modules.rbac.models import UserRoleAssignment

    stmt = select(
        exists().where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.institute_id == institute_id,
            UserRoleAssignment.revoked_at.is_(None),
        )
    )
    if not await db.scalar(stmt):
        raise NotFound("That user is not part of this institute.")
