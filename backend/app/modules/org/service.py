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

from app.core.db import Db
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
    Organisation,
)
from app.modules.rbac.scopes import Scope
from app.modules.rbac.service import Authorized


def _require_active(row, word: str) -> None:
    """Nothing new is added under something archived."""
    if row.status != "active":
        raise ValidationFailed(f"That {word} is archived.")


async def _ensure_also(guard: Authorized, permission: str, scope: Scope) -> None:
    """A second permission on the same route — archiving through the update endpoint.

    Without it ``branch:archive`` / ``class:archive`` were shown in the matrix and checked
    nowhere: removing them from a role changed nothing.
    """
    await Authorized(guard._db, guard.context, permission).ensure(scope)


async def _require_institute(db: Db, institute_id: uuid.UUID) -> Institute:
    institute = await repo.get_institute(db, institute_id)
    if institute is None:
        raise NotFound("That institute does not exist.")
    return institute


async def _require_branch(db: Db, institute_id: uuid.UUID, branch_id: uuid.UUID) -> Branch:
    branch = await repo.get_branch(db, branch_id, institute_id=institute_id)
    if branch is None:
        raise NotFound("That branch does not exist.")
    return branch


async def _require_class(db: Db, class_id: uuid.UUID) -> Class:
    found = await repo.get_class(db, class_id)
    if found is None:
        raise NotFound("That class does not exist.")
    return found


# --------------------------------------------------------------------------- institutes


async def create_institute(
    db: Db, *, guard: Authorized, payload: schemas.InstituteCreate, meta: RequestMeta
) -> Institute:
    # Platform staff create anywhere. An Organisation Admin creates only inside their own
    # organisation: `Scope(organisation_id=None)` is the platform, so a standalone institute
    # still needs platform authority.
    if payload.organisation_id is not None:
        await _require_active_organisation(db, payload.organisation_id)
    await guard.ensure(Scope(organisation_id=payload.organisation_id))

    if await repo.institute_code_taken(db, payload.code):
        raise Conflict("An institute with that code already exists.")

    institute = Institute(
        organisation_id=payload.organisation_id,
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
        extra={
            "code": institute.code,
            "type": institute.type,
            "organisation_id": str(institute.organisation_id)
            if institute.organisation_id
            else None,
        },
    )
    return institute


async def _require_active_organisation(db: Db, organisation_id: uuid.UUID) -> Organisation:
    organisation = await repo.get_organisation(db, organisation_id)
    if organisation is None:
        raise NotFound("That organisation does not exist.")
    if organisation.status != "active":
        raise ValidationFailed("That organisation is archived.")
    return organisation


def forget_organisation_snapshots() -> None:
    """Drop every cached permission context.

    A context holds a snapshot of which institutes sit in each organisation, so adding,
    moving or archiving an institute changes what Organisation Admins (and everyone inside
    the institute) may reach. Call after the change is committed.
    """
    # ponytail: clears the whole per-process cache; these events are rare. Per-organisation
    # invalidation if they ever become frequent. Other instances catch up within the TTL.
    from app.modules.rbac.context import context_cache

    context_cache.clear()


async def enable_core_modules(db: Db, institute_id: uuid.UUID) -> None:
    """Core is on for every institute from the moment it exists — auth, org and users are
    not optional extras (PRD §5.2 step 5)."""
    from app.modules.rbac.catalog import CORE_MODULE
    from app.modules.rbac.models import InstituteModule

    db.add(InstituteModule(institute_id=institute_id, module_key=CORE_MODULE, enabled=True))


async def update_institute(
    db: Db,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    payload: schemas.InstituteUpdate,
    meta: RequestMeta,
) -> Institute:
    await guard.ensure(Scope(institute_id=institute_id))
    institute = await _require_institute(db, institute_id)

    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    changed.pop("organisation_id", None)
    if "organisation_id" in payload.model_fields_set:
        target = payload.organisation_id
        if target != institute.organisation_id:
            # Moving an institute changes who administers it, so it needs platform
            # authority — an Organisation Admin cannot pull a college into their group.
            await guard.ensure(Scope())
            if institute.is_system:
                raise Forbidden("The built-in Direct institute cannot join an organisation.")
            if target is not None:
                await _require_active_organisation(db, target)
            institute.organisation_id = target
            changed["organisation_id"] = target
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
    db: Db, *, guard: Authorized, institute_id: uuid.UUID, meta: RequestMeta
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


async def restore_institute(
    db: Db, *, guard: Authorized, institute_id: uuid.UUID, meta: RequestMeta
) -> Institute:
    await guard.ensure(Scope())
    institute = await _require_institute(db, institute_id)
    if institute.organisation_id is not None:
        await _require_active_organisation(db, institute.organisation_id)
    institute.status = "active"
    audit.record(
        db,
        action=events.INSTITUTE_RESTORED,
        actor_user_id=guard.user_id,
        target_type="institute",
        target_id=institute.id,
        institute_id=institute.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    return institute


async def list_institutes(
    db: Db,
    *,
    guard: Authorized,
    search: str | None,
    status: str | None,
    cursor: str | None,
    limit: int,
    include_total: bool = True,
    organisation_id: uuid.UUID | None = None,
) -> tuple[Sequence[Institute], str | None, int]:
    """Platform staff see everything; everyone else sees only institutes they hold a role in.

    Derived from the permission's own usable scopes, so a deny on ``institute:read``
    removes that institute from the list instead of only from the detail endpoint.
    """
    # `visible_institute_ids` already expands an organisation grant into the institutes
    # inside it, so an Organisation Admin sees their four colleges and nothing else
    # without this function knowing the level exists.
    visible = guard.visible_institute_ids()
    return await repo.list_institutes(
        db,
        visible_ids=visible,
        search=search,
        status=status,
        cursor=cursor,
        limit=limit,
        include_total=include_total,
        organisation_id=organisation_id,
    )


async def get_institute(db: Db, *, guard: Authorized, institute_id: uuid.UUID) -> Institute:
    """404, not 403, when the institute is outside the caller's scope.

    The same rule the users module already follows, and it matters more here. A 403 means
    "this exists and is not yours", so anybody with an account could walk a list of ids
    and learn which institutes are on the platform — a customer list, handed out by the
    error code. 404 says nothing either way.

    `guard.ensure` is deliberately not used: it answers 403, which is the leak.
    """
    institute = await _require_institute(db, institute_id)
    # Same rule as the list: a branch-level reader (branch admin, teacher, student) sees
    # their own institute in `GET /institutes`, so opening it must not answer 404.
    visible = guard.visible_institute_ids()
    if visible is not None and institute_id not in visible:
        raise NotFound("That institute does not exist.")
    return institute


# ----------------------------------------------------------------------------- branches


async def create_branch(
    db: Db,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    payload: schemas.BranchCreate,
    meta: RequestMeta,
) -> Branch:
    await guard.ensure(Scope(institute_id=institute_id))
    _require_active(await _require_institute(db, institute_id), "institute")

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
    db: Db,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    branch_id: uuid.UUID,
    payload: schemas.BranchUpdate,
    meta: RequestMeta,
) -> Branch:
    scope = Scope(institute_id=institute_id, branch_id=branch_id)
    await guard.ensure(scope)
    branch = await _require_branch(db, institute_id, branch_id)

    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    archiving = changed.get("status") == "archived" and branch.status != "archived"
    if changed.get("status", branch.status) != branch.status:
        await _ensure_also(guard, "branch:archive", scope)
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
    db: Db,
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
    db: Db,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    payload: schemas.AcademicSessionCreate,
    meta: RequestMeta,
) -> AcademicSession:
    await guard.ensure(Scope(institute_id=institute_id))
    _require_active(await _require_institute(db, institute_id), "institute")

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
    db: Db,
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
        await repo.clear_current_session(db, institute_id, keep=session.id)
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
    db: Db, *, guard: Authorized, institute_id: uuid.UUID, cursor: str | None, limit: int
) -> tuple[Sequence[AcademicSession], str | None, int]:
    await guard.ensure_within(institute_id)
    return await repo.list_sessions(db, institute_id=institute_id, cursor=cursor, limit=limit)


# ------------------------------------------------------------------------------ classes


async def create_class(
    db: Db,
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
    _require_active(branch, "branch")

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
    db: Db,
    *,
    guard: Authorized,
    class_id: uuid.UUID,
    payload: schemas.ClassUpdate,
    meta: RequestMeta,
) -> Class:
    target = await _require_class(db, class_id)
    scope = Scope(institute_id=target.institute_id, branch_id=target.branch_id)
    await guard.ensure(scope)

    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    archiving = changed.get("status") == "archived" and target.status != "archived"
    if changed.get("status", target.status) != target.status:
        await _ensure_also(guard, "class:archive", scope)
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
    db: Db,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[Sequence[Class], str | None, int]:
    """Faculty, students and parents see only the classes they are linked to (PRD §5.3).

    Narrowed per scope: wherever the caller acts only as Faculty/Student/Parent they see
    their linked classes; wherever they hold an administrative role they see that scope's
    classes. Someone can be both, in different branches or institutes.
    """
    from app.modules.rbac.service import membership_narrowed

    scopes = await guard.ensure_within(institute_id)
    broad = tuple(s for s in scopes if not membership_narrowed(guard.context, s))

    if branch_id is not None and not any(
        s.level == "platform" or s.branch_id in (None, branch_id) for s in scopes
    ):
        raise Forbidden()

    linked: frozenset[uuid.UUID] = frozenset()
    if len(broad) < len(scopes):
        linked = await linked_class_ids(db, guard.context)

    if not broad:
        branch_ids, class_ids = None, linked
    elif guard.covers_whole_institute(broad, institute_id):
        branch_ids, class_ids = None, None
    else:
        branch_ids, class_ids = frozenset(s.branch_id for s in broad if s.branch_id), None

    return await repo.list_classes(
        db,
        institute_id=institute_id,
        branch_id=branch_id,
        branch_ids=branch_ids,
        also_class_ids=linked if branch_ids is not None else frozenset(),
        session_id=session_id,
        class_ids=class_ids,
        status=status,
        cursor=cursor,
        limit=limit,
    )


async def linked_class_ids(db: Db, context) -> frozenset[uuid.UUID]:
    """Classes someone reaches through a link: taught, enrolled in, or a child's."""
    from app.modules.rbac import repository as rbac_repo
    from app.modules.rbac.catalog import FACULTY, PARENT, STUDENT

    role_keys = {a.role_key for a in context.assignments}
    found: set[uuid.UUID] = set()
    if FACULTY in role_keys:
        found |= await rbac_repo.faculty_class_ids(db, context.user_id)
    if STUDENT in role_keys:
        found |= await rbac_repo.student_class_ids(db, context.user_id)
    if PARENT in role_keys:
        from app.modules.users import repository as users_repo

        for child in await users_repo.children_of(db, context.user_id):
            found |= await rbac_repo.student_class_ids(db, child)
    return frozenset(found)


# ------------------------------------------------------------- faculty and enrolment


async def assign_faculty(
    db: Db,
    *,
    guard: Authorized,
    class_id: uuid.UUID,
    payload: schemas.ClassFacultyCreate,
    meta: RequestMeta,
) -> ClassFaculty:
    target = await _require_class(db, class_id)
    await guard.ensure(Scope(institute_id=target.institute_id, branch_id=target.branch_id))
    _require_active(target, "class")
    await _require_user_in_institute(db, payload.user_id, target.institute_id, staff=True)

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
    db: Db,
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
    db: Db,
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
    _require_active(target, "class")
    await _require_user_in_institute(db, payload.user_id, target.institute_id, student=True)

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
    db: Db,
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
    db: Db,
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
    db: Db,
    user_id: uuid.UUID,
    institute_id: uuid.UUID,
    *,
    staff: bool = False,
    student: bool = False,
) -> None:
    """Cross-tenant guard: you cannot attach a user from another institute to your class.

    ``student`` requires the Student role there, ``staff`` any role other than Student or
    Parent — otherwise a student could be put on a class as its teacher, or the principal
    enrolled as a pupil.
    """
    from app.modules.rbac.catalog import PARENT, STUDENT
    from app.modules.rbac.models import Role, UserRoleAssignment

    role_ids = await db.distinct(
        UserRoleAssignment,
        "role_id",
        {"user_id": user_id, "institute_id": institute_id, "revoked_at": None},
    )
    if not role_ids:
        raise NotFound("That user is not part of this institute.")
    keys = set(await db.distinct(Role, "key", {"_id": {"$in": role_ids}}))
    if student and STUDENT not in keys:
        raise ValidationFailed("Only someone with the Student role here can be enrolled.")
    if staff and not keys - {STUDENT, PARENT}:
        raise ValidationFailed("Only staff of this institute can be assigned to teach a class.")


async def list_class_faculty(
    db: Db, *, guard: Authorized, class_id: uuid.UUID
) -> list[schemas.ClassMemberOut]:
    target = await _require_class(db, class_id)
    await guard.ensure(
        Scope(institute_id=target.institute_id, branch_id=target.branch_id), class_id=class_id
    )
    links = await db.find(ClassFaculty, {"class_id": class_id})
    people = await _people(db, [link.faculty_user_id for link in links])
    return [
        schemas.ClassMemberOut(
            user_id=link.faculty_user_id,
            full_name=people[link.faculty_user_id].full_name,
            email=people[link.faculty_user_id].email,
            subject=link.subject,
            is_class_teacher=link.is_class_teacher,
        )
        for link in links
        if link.faculty_user_id in people
    ]


async def list_class_students(
    db: Db, *, guard: Authorized, class_id: uuid.UUID
) -> list[schemas.ClassMemberOut]:
    target = await _require_class(db, class_id)
    await guard.ensure(
        Scope(institute_id=target.institute_id, branch_id=target.branch_id), class_id=class_id
    )
    rows = await db.find(ClassEnrollment, {"class_id": class_id, "status": "active"})
    people = await _people(db, [row.student_user_id for row in rows])
    return [
        schemas.ClassMemberOut(
            user_id=row.student_user_id,
            full_name=people[row.student_user_id].full_name,
            email=people[row.student_user_id].email,
            roll_no=row.roll_no,
            status=row.status,
        )
        for row in rows
        if row.student_user_id in people
    ]


async def _people(db: Db, ids: list[uuid.UUID]) -> dict:
    from app.modules.users.models import User

    if not ids:
        return {}
    return {u.id: u for u in await db.find(User, {"_id": {"$in": ids}})}


# ------------------------------------------------------------------------ organisations


async def create_organisation(
    db: Db,
    *,
    guard: Authorized,
    payload: schemas.OrganisationCreate,
    meta: RequestMeta,
) -> Organisation:
    """Platform-only. Creating a *new* organisation decides who else exists on the
    platform, which is not something one organisation's administrator does."""
    await guard.ensure(Scope())

    if await repo.organisation_code_taken(db, payload.code):
        raise Conflict("An organisation with that code already exists.")

    organisation = Organisation(
        name=payload.name,
        code=payload.code,
        contact_email=payload.contact_email,
        logo_url=payload.logo_url,
        status="active",
    )
    db.add(organisation)
    await db.flush()

    audit.record(
        db,
        action=events.ORGANISATION_CREATED,
        actor_user_id=guard.user_id,
        target_type="organisation",
        target_id=organisation.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"code": organisation.code},
    )
    await db.commit()
    return organisation


async def list_organisations(
    db: Db,
    *,
    guard: Authorized,
    search: str | None,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[Sequence[Organisation], str | None, int, dict[uuid.UUID, int]]:
    """Platform staff see every organisation; everyone else sees only theirs.

    Derived from the permission's own usable scopes, so a deny on ``organisation:read``
    removes it from the list and not only from the detail endpoint.
    """
    scopes = guard.usable_scopes()
    if any(s.level == "platform" for s in scopes):
        visible: frozenset[uuid.UUID] | None = None
    else:
        visible = frozenset(s.organisation_id for s in scopes if s.organisation_id is not None)

    rows, cursor_out, total = await repo.list_organisations(
        db, visible_ids=visible, search=search, status=status, cursor=cursor, limit=limit
    )
    counts = await repo.institute_counts(db, [row.id for row in rows])
    return rows, cursor_out, total, counts


async def get_organisation(
    db: Db, *, guard: Authorized, organisation_id: uuid.UUID
) -> Organisation:
    organisation = await repo.get_organisation(db, organisation_id)
    if organisation is None:
        raise NotFound("That organisation does not exist.")
    # 404 rather than 403 from here on: confirming that an organisation exists to somebody
    # outside it tells them something about a customer they have no business knowing.
    if not guard.context.can(guard.permission, Scope(organisation_id=organisation_id)):
        raise NotFound("That organisation does not exist.")
    return organisation


async def update_organisation(
    db: Db,
    *,
    guard: Authorized,
    organisation_id: uuid.UUID,
    payload: schemas.OrganisationUpdate,
    meta: RequestMeta,
) -> Organisation:
    organisation = await get_organisation(db, guard=guard, organisation_id=organisation_id)
    await guard.ensure(Scope(organisation_id=organisation_id))

    for field in ("name", "contact_email", "logo_url"):
        value = getattr(payload, field)
        if value is not None:
            setattr(organisation, field, value)

    audit.record(
        db,
        action=events.ORGANISATION_UPDATED,
        actor_user_id=guard.user_id,
        target_type="organisation",
        target_id=organisation.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    await db.commit()
    return organisation


async def archive_organisation(
    db: Db,
    *,
    guard: Authorized,
    organisation_id: uuid.UUID,
    meta: RequestMeta,
) -> Organisation:
    """Refused while institutes still hang off it.

    Archiving the group would leave four colleges pointing at something retired, and the
    administrator who did it would have no idea until somebody could not sign in. Move or
    archive the institutes first, deliberately.
    """
    await guard.ensure(Scope())
    organisation = await get_organisation(db, guard=guard, organisation_id=organisation_id)

    remaining = await repo.organisation_has_institutes(db, organisation_id)
    if remaining:
        raise Conflict(
            f"{remaining} {'institute belongs' if remaining == 1 else 'institutes belong'} "
            f"to this organisation. Move or archive them first."
        )

    organisation.status = "archived"
    audit.record(
        db,
        action=events.ORGANISATION_ARCHIVED,
        actor_user_id=guard.user_id,
        target_type="organisation",
        target_id=organisation.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    await db.commit()
    return organisation


async def restore_organisation(
    db: Db,
    *,
    guard: Authorized,
    organisation_id: uuid.UUID,
    meta: RequestMeta,
) -> Organisation:
    await guard.ensure(Scope())
    organisation = await get_organisation(db, guard=guard, organisation_id=organisation_id)
    organisation.status = "active"
    audit.record(
        db,
        action=events.ORGANISATION_RESTORED,
        actor_user_id=guard.user_id,
        target_type="organisation",
        target_id=organisation.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    await db.commit()
    return organisation


# ------------------------------------------------------------------- module switches


async def list_institute_modules(
    db: Db, *, guard: Authorized, institute_id: uuid.UUID
) -> list[schemas.InstituteModuleOut]:
    """Every optional module with this institute's switch. Core is never listed: it cannot
    be turned off, so offering a switch for it would be a control that does nothing."""
    from app.modules.rbac.models import InstituteModule, Module

    await get_institute(db, guard=guard, institute_id=institute_id)  # 404 when out of scope
    modules = await db.find(Module, {"is_core": False}, sort=[("key", 1)])
    enabled = {
        row["module_key"]
        for row in await db.raw(
            InstituteModule,
            {"institute_id": institute_id, "enabled": True},
            {"module_key": 1},
        )
    }
    return [
        schemas.InstituteModuleOut(
            key=m.key, name=m.name, description=m.description, enabled=m.key in enabled
        )
        for m in modules
    ]


async def set_institute_module(
    db: Db,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    module_key: str,
    enabled: bool,
    meta: RequestMeta,
) -> schemas.InstituteModuleOut:
    """Switch an optional module on or off for one institute.

    Allowed only from a platform- or organisation-level grant of `module:enable`. An
    institute deciding for itself which paid modules it has would make the switch a
    formality, so a grant held at institute level — which an institute could otherwise
    give itself through Roles & permissions — is not enough.
    """
    from app.modules.rbac import service as rbac
    from app.modules.rbac.models import InstituteModule, Module
    from app.modules.rbac.scopes import ORGANISATION, PLATFORM

    await _require_institute(db, institute_id)
    target = await rbac.resolve_scope(db, institute_id=institute_id)
    await guard.ensure(target)
    if not any(
        s.level in (PLATFORM, ORGANISATION) and s.contains(target) for s in guard.usable_scopes()
    ):
        raise Forbidden("Modules are switched on by the platform or the organisation.")

    module = await db.find_one(Module, {"key": module_key})
    if module is None:
        raise NotFound("That module does not exist.")
    if module.is_core:
        raise ValidationFailed("The core platform is always on and cannot be switched off.")

    row = await db.find_one(
        InstituteModule, {"institute_id": institute_id, "module_key": module_key}
    )
    changed = row is None or row.enabled != enabled
    if row is None:
        db.add(InstituteModule(institute_id=institute_id, module_key=module_key, enabled=enabled))
    else:
        row.enabled = enabled

    if changed:
        audit.record(
            db,
            action=events.MODULE_ENABLED if enabled else events.MODULE_DISABLED,
            actor_user_id=guard.user_id,
            target_type="institute",
            target_id=institute_id,
            institute_id=institute_id,
            ip=meta.ip,
            user_agent=meta.user_agent,
            extra={"module_key": module_key},
        )
    return schemas.InstituteModuleOut(
        key=module.key, name=module.name, description=module.description, enabled=enabled
    )
