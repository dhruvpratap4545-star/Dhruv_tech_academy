"""Organisation endpoints: institutes, branches, sessions, classes, faculty, enrolment.

Paths follow PRD §8. Every handler resolves its target, hands the scope to the guard, and
lets the service do the work — no business rules and no SQL in this file.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from app.core.errors import Forbidden
from app.core.pagination import Page, clamp_limit
from app.modules.auth.service import RequestMeta
from app.modules.notifications.email import send_email
from app.modules.org import schemas
from app.modules.org import service as org
from app.modules.rbac.deps import DbSession, client_ip, require_permission, user_agent
from app.modules.rbac.service import Authorized

institutes_router = APIRouter()
branches_router = APIRouter()
classes_router = APIRouter()

Limit = Annotated[int, Query(ge=1, le=100, description="Rows per page (max 100).")]
Cursor = Annotated[str | None, Query(description="Opaque cursor from the previous page.")]
StatusFilter = Annotated[str | None, Query(alias="status", pattern="^(active|archived)$")]


def _meta(request: Request) -> RequestMeta:
    return RequestMeta(ip=client_ip(request), user_agent=user_agent(request))


# --------------------------------------------------------------------------- institutes


@institutes_router.get(
    "", response_model=Page[schemas.InstituteOut], summary="List institutes in your scope"
)
async def list_institutes(
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("institute:read"))],
    search: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: StatusFilter = None,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> Page[schemas.InstituteOut]:
    size = clamp_limit(limit)
    rows, next_cursor = await org.list_institutes(
        db, guard=guard, search=search, status=status_filter, cursor=cursor, limit=size
    )
    return Page[schemas.InstituteOut](
        items=[schemas.InstituteOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )


@institutes_router.post(
    "",
    response_model=schemas.InstituteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an institute",
)
async def create_institute(
    payload: schemas.InstituteCreate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("institute:create"))],
) -> schemas.InstituteOut:
    institute = await org.create_institute(db, guard=guard, payload=payload, meta=_meta(request))
    await db.commit()
    return schemas.InstituteOut.model_validate(institute)


@institutes_router.post(
    "/with-admin",
    response_model=schemas.InstituteWithAdminOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an institute and invite its first Institute Admin",
    description="One transaction: if the invitation fails, the institute is not created "
    "either, so there is never an institute nobody can administer.",
)
async def create_institute_with_admin(
    payload: schemas.InstituteWithAdminCreate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("institute:create"))],
) -> schemas.InstituteWithAdminOut:
    from app.modules.rbac.catalog import INSTITUTE_ADMIN
    from app.modules.users import schemas as user_schemas
    from app.modules.users import service as users

    institute = await org.create_institute(
        db, guard=guard, payload=payload.institute, meta=_meta(request)
    )
    # A guard carries the permission it was built for, and every check inside
    # `invite_user` asks about `guard.permission`. Passing the `institute:create` guard
    # would silently evaluate the invite rules — scope, rank, faculty classes — against
    # the wrong permission, so a block on `user:invite` would not stop this path. Today
    # everyone holding `institute:create` also holds `user:invite`, so it is a bypass
    # primitive rather than a live hole; it stops being either one here.
    invite_guard = Authorized(db, guard.context, "user:invite")
    if not guard.context.holds("user:invite"):
        raise Forbidden("You cannot invite the administrator for this institute.")

    admin, message = await users.invite_user(
        db,
        guard=invite_guard,
        payload=user_schemas.InviteUserRequest(
            full_name=payload.admin_full_name,
            email=payload.admin_email,
            role_key=INSTITUTE_ADMIN,
            institute_id=institute.id,
        ),
        meta=_meta(request),
    )
    if message is not None:
        background.add_task(send_email, message)
    return schemas.InstituteWithAdminOut(
        institute=schemas.InstituteOut.model_validate(institute),
        admin_user_id=admin.id,
        admin_email=admin.email,
    )


@institutes_router.get(
    "/{institute_id}", response_model=schemas.InstituteOut, summary="Read one institute"
)
async def get_institute(
    institute_id: uuid.UUID,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("institute:read"))],
) -> schemas.InstituteOut:
    return schemas.InstituteOut.model_validate(
        await org.get_institute(db, guard=guard, institute_id=institute_id)
    )


@institutes_router.patch(
    "/{institute_id}", response_model=schemas.InstituteOut, summary="Update an institute"
)
async def update_institute(
    institute_id: uuid.UUID,
    payload: schemas.InstituteUpdate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("institute:update"))],
) -> schemas.InstituteOut:
    institute = await org.update_institute(
        db, guard=guard, institute_id=institute_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.InstituteOut.model_validate(institute)


@institutes_router.post(
    "/{institute_id}/archive",
    response_model=schemas.InstituteOut,
    summary="Archive an institute",
    description="Nothing is deleted. The institute and all its data remain, marked archived.",
)
async def archive_institute(
    institute_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("institute:archive"))],
) -> schemas.InstituteOut:
    institute = await org.archive_institute(
        db, guard=guard, institute_id=institute_id, meta=_meta(request)
    )
    await db.commit()
    return schemas.InstituteOut.model_validate(institute)


# ---------------------------------------------------------------- branches and sessions


@institutes_router.get(
    "/{institute_id}/branches", response_model=Page[schemas.BranchOut], summary="List branches"
)
async def list_branches(
    institute_id: uuid.UUID,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("branch:read"))],
    status_filter: StatusFilter = None,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> Page[schemas.BranchOut]:
    size = clamp_limit(limit)
    rows, next_cursor = await org.list_branches(
        db,
        guard=guard,
        institute_id=institute_id,
        status=status_filter,
        cursor=cursor,
        limit=size,
    )
    return Page[schemas.BranchOut](
        items=[schemas.BranchOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )


@institutes_router.post(
    "/{institute_id}/branches",
    response_model=schemas.BranchOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a branch",
)
async def create_branch(
    institute_id: uuid.UUID,
    payload: schemas.BranchCreate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("branch:create"))],
) -> schemas.BranchOut:
    branch = await org.create_branch(
        db, guard=guard, institute_id=institute_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.BranchOut.model_validate(branch)


@institutes_router.patch(
    "/{institute_id}/branches/{branch_id}",
    response_model=schemas.BranchOut,
    summary="Update or archive a branch",
)
async def update_branch(
    institute_id: uuid.UUID,
    branch_id: uuid.UUID,
    payload: schemas.BranchUpdate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("branch:update"))],
) -> schemas.BranchOut:
    branch = await org.update_branch(
        db,
        guard=guard,
        institute_id=institute_id,
        branch_id=branch_id,
        payload=payload,
        meta=_meta(request),
    )
    await db.commit()
    return schemas.BranchOut.model_validate(branch)


@institutes_router.get(
    "/{institute_id}/sessions",
    response_model=Page[schemas.AcademicSessionOut],
    summary="List academic sessions",
)
async def list_sessions(
    institute_id: uuid.UUID,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("session:read"))],
    cursor: Cursor = None,
    limit: Limit = 20,
) -> Page[schemas.AcademicSessionOut]:
    size = clamp_limit(limit)
    rows, next_cursor = await org.list_sessions(
        db, guard=guard, institute_id=institute_id, cursor=cursor, limit=size
    )
    return Page[schemas.AcademicSessionOut](
        items=[schemas.AcademicSessionOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@institutes_router.post(
    "/{institute_id}/sessions",
    response_model=schemas.AcademicSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an academic session",
)
async def create_session(
    institute_id: uuid.UUID,
    payload: schemas.AcademicSessionCreate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("session:create"))],
) -> schemas.AcademicSessionOut:
    session = await org.create_session(
        db, guard=guard, institute_id=institute_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.AcademicSessionOut.model_validate(session)


@institutes_router.patch(
    "/{institute_id}/sessions/{session_id}",
    response_model=schemas.AcademicSessionOut,
    summary="Update an academic session",
)
async def update_session(
    institute_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: schemas.AcademicSessionUpdate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("session:update"))],
) -> schemas.AcademicSessionOut:
    session = await org.update_session(
        db,
        guard=guard,
        institute_id=institute_id,
        session_id=session_id,
        payload=payload,
        meta=_meta(request),
    )
    await db.commit()
    return schemas.AcademicSessionOut.model_validate(session)


@institutes_router.get(
    "/{institute_id}/classes", response_model=Page[schemas.ClassOut], summary="List classes"
)
async def list_classes(
    institute_id: uuid.UUID,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("class:read"))],
    branch_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    status_filter: StatusFilter = None,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> Page[schemas.ClassOut]:
    size = clamp_limit(limit)
    rows, next_cursor = await org.list_classes(
        db,
        guard=guard,
        institute_id=institute_id,
        branch_id=branch_id,
        session_id=session_id,
        status=status_filter,
        cursor=cursor,
        limit=size,
    )
    return Page[schemas.ClassOut](
        items=[schemas.ClassOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )


# ------------------------------------------------------------------------------ classes


@branches_router.post(
    "/{branch_id}/classes",
    response_model=schemas.ClassOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a class in a branch",
)
async def create_class(
    branch_id: uuid.UUID,
    payload: schemas.ClassCreate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("class:create"))],
) -> schemas.ClassOut:
    created = await org.create_class(
        db, guard=guard, branch_id=branch_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.ClassOut.model_validate(created)


@classes_router.patch(
    "/{class_id}", response_model=schemas.ClassOut, summary="Update or archive a class"
)
async def update_class(
    class_id: uuid.UUID,
    payload: schemas.ClassUpdate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("class:update"))],
) -> schemas.ClassOut:
    updated = await org.update_class(
        db, guard=guard, class_id=class_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.ClassOut.model_validate(updated)


@classes_router.post(
    "/{class_id}/faculty",
    response_model=schemas.ClassFacultyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a faculty member to a class",
)
async def assign_faculty(
    class_id: uuid.UUID,
    payload: schemas.ClassFacultyCreate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("class_faculty:manage"))],
) -> schemas.ClassFacultyOut:
    link = await org.assign_faculty(
        db, guard=guard, class_id=class_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.ClassFacultyOut.model_validate(link)


@classes_router.delete(
    "/{class_id}/faculty/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a faculty member from a class",
)
async def remove_faculty(
    class_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("class_faculty:manage"))],
) -> None:
    await org.remove_faculty(
        db, guard=guard, class_id=class_id, user_id=user_id, meta=_meta(request)
    )
    await db.commit()


@classes_router.post(
    "/{class_id}/students",
    response_model=schemas.EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Enrol a student in a class",
    description="Faculty can only enrol students into classes they themselves teach.",
)
async def enrol_student(
    class_id: uuid.UUID,
    payload: schemas.EnrollmentCreate,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("enrollment:manage"))],
) -> schemas.EnrollmentOut:
    enrollment = await org.enrol_student(
        db, guard=guard, class_id=class_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.EnrollmentOut.model_validate(enrollment)


@classes_router.delete(
    "/{class_id}/students/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a student from a class",
    description="Marks the enrolment as left; the history is kept.",
)
async def unenrol_student(
    class_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("enrollment:manage"))],
) -> None:
    await org.unenrol_student(
        db, guard=guard, class_id=class_id, user_id=user_id, meta=_meta(request)
    )
    await db.commit()
