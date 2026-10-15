"""User, profile and role endpoints (PRD §8)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response

from app.core.errors import ValidationFailed
from app.core.pagination import Page, clamp_limit
from app.modules.auth.service import RequestMeta
from app.modules.notifications.email import send_email
from app.modules.rbac import schemas as rbac_schemas
from app.modules.rbac.deps import (
    AuthContextDep,
    CurrentUser,
    DbSession,
    client_ip,
    require_permission,
    user_agent,
)
from app.modules.rbac.service import Authorized
from app.modules.users import bulk, schemas, spreadsheet
from app.modules.users import service as users

router = APIRouter()
me_router = APIRouter()

Limit = Annotated[int, Query(ge=1, le=100, description="Rows per page (max 100).")]
Cursor = Annotated[str | None, Query(description="Opaque cursor from the previous page.")]

#: The media type Excel itself writes. Named once so the download header and the OpenAPI
#: description cannot drift apart.
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _read_upload(file: UploadFile) -> bytes:
    """The uploaded bytes, refused early if the file is obviously not a workbook.

    The size is checked again inside the import, against the bytes actually read: a
    `content-length` header is whatever the client said, and a streamed upload has none.
    """
    if file.size is not None and file.size > bulk.MAX_BYTES:
        raise ValidationFailed(
            "That file is too large. Export just the learner list as .xlsx and try again."
        )
    return await file.read()


def _meta(request: Request) -> RequestMeta:
    return RequestMeta(ip=client_ip(request), user_agent=user_agent(request))


# --------------------------------------------------------------------------------- me


@me_router.get(
    "",
    response_model=schemas.MeOut,
    summary="Who am I",
    description="Profile, roles, institutes and the permission keys the UI uses to decide "
    "which menus to show. Authorization itself is always checked server-side.",
)
async def get_me(user: CurrentUser, db: DbSession) -> schemas.MeOut:
    return await users.build_me(db, user)


@me_router.get(
    "/access",
    response_model=rbac_schemas.MyAccessOut,
    summary="What you can do, and where",
    description="Your roles with their scopes, every permission in the platform marked "
    "granted or not, and any personal exceptions that apply to you. Needs no permission: "
    "it only ever describes the caller's own access.",
)
async def get_my_access(db: DbSession, context: AuthContextDep) -> rbac_schemas.MyAccessOut:
    from app.modules.rbac import admin as rbac_admin

    return await rbac_admin.build_my_access(db, context)


@me_router.get(
    "/children",
    response_model=list[schemas.ChildOut],
    summary="The learners you are responsible for",
    description="A parent's own family. No permission is required because the answer is "
    "about them: it lists exactly the learners they are the recorded guardian of, and is "
    "empty for everybody else.",
)
async def my_children(db: DbSession, actor: CurrentUser) -> list[schemas.ChildOut]:
    return await users.list_my_children(db, user_id=actor.id)


@me_router.patch("", response_model=schemas.UserOut, summary="Update your own profile")
async def update_me(
    payload: schemas.UpdateProfileRequest, user: CurrentUser, db: DbSession
) -> schemas.UserOut:
    updated = await users.update_profile(db, user=user, payload=payload)
    return schemas.UserOut.model_validate(updated)


@me_router.get(
    "/overview",
    response_model=schemas.OverviewOut,
    summary="Counts for the dashboard, scoped to what you can see",
)
async def get_overview(
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:read"))],
) -> schemas.OverviewOut:
    return await users.build_overview(db, guard=guard)


@me_router.patch(
    "/preferences",
    response_model=schemas.PreferencesOut,
    summary="Update your theme and language",
    description="Saved per user, so the choice follows them to any device.",
)
async def update_my_preferences(
    payload: schemas.UpdatePreferencesRequest, user: CurrentUser, db: DbSession
) -> schemas.PreferencesOut:
    preferences = await users.update_preferences(db, user_id=user.id, payload=payload)
    return schemas.PreferencesOut.model_validate(preferences)


# ------------------------------------------------------------------------------ users


@router.get(
    "",
    response_model=Page[schemas.UserDetailOut],
    summary="List and search users in your scope",
    description="Institute and branch admins see their own scope only; faculty see the "
    "students of the classes they teach.",
)
async def list_users(
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:read"))],
    search: Annotated[str | None, Query(max_length=120)] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    role_key: Annotated[str | None, Query(max_length=40)] = None,
    institute_id: uuid.UUID | None = None,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> Page[schemas.UserDetailOut]:
    size = clamp_limit(limit)
    rows, next_cursor, total = await users.list_users(
        db,
        guard=guard,
        search=search,
        status=status_filter,
        role_key=role_key,
        institute_id=institute_id,
        cursor=cursor,
        limit=size,
    )
    roles = await users.attach_roles(db, rows)
    items = [
        schemas.UserDetailOut(
            **schemas.UserOut.model_validate(row).model_dump(), roles=roles.get(row.id, [])
        )
        for row in rows
    ]
    return Page[schemas.UserDetailOut](items=items, next_cursor=next_cursor, total=total)


@router.get("/{user_id}", response_model=schemas.UserDetailOut, summary="Read one user")
async def get_user(
    user_id: uuid.UUID,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:read"))],
) -> schemas.UserDetailOut:
    row = await users.get_user(db, guard=guard, user_id=user_id)
    roles = await users.attach_roles(db, [row])
    return schemas.UserDetailOut(
        **schemas.UserOut.model_validate(row).model_dump(), roles=roles.get(row.id, [])
    )


@router.post(
    "/invite",
    response_model=schemas.InviteUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user and give them a role",
    description="Creates the account as `invited` and emails a setup code. You can only "
    "invite someone below your own level, inside your own scope.",
)
async def invite_user(
    request: Request,
    payload: schemas.InviteUserRequest,
    background: BackgroundTasks,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:invite"))],
) -> schemas.InviteUserResponse:
    user, message = await users.invite_user(db, guard=guard, payload=payload, meta=_meta(request))
    if message is not None:
        background.add_task(send_email, message)
    return schemas.InviteUserResponse(user=schemas.UserOut.model_validate(user))


@router.post(
    "/{user_id}/resend-invite",
    response_model=schemas.InviteUserResponse,
    summary="Send a fresh setup code",
)
async def resend_invite(
    user_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:invite"))],
) -> schemas.InviteUserResponse:
    message = await users.resend_invitation(db, guard=guard, user_id=user_id, meta=_meta(request))
    background.add_task(send_email, message)
    row = await users.get_user(db, guard=guard, user_id=user_id)
    return schemas.InviteUserResponse(user=schemas.UserOut.model_validate(row))


@router.post(
    "/bulk-status",
    response_model=schemas.BulkStatusResponse,
    summary="Suspend or re-activate up to 100 users at once",
    description="Each person is checked individually against the same rules as the single "
    "endpoint — your permission, your scope, and their role being strictly below yours — "
    "and you can never change your own status. Anyone you may not act on is skipped with "
    "the reason, rather than failing the whole request.",
)
async def bulk_update_status(
    payload: schemas.BulkStatusRequest,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:update_status"))],
) -> schemas.BulkStatusResponse:
    results = await users.bulk_update_status(db, guard=guard, payload=payload, meta=_meta(request))
    return schemas.BulkStatusResponse(
        results=results,
        succeeded=sum(1 for r in results if r.outcome == "succeeded"),
        skipped=sum(1 for r in results if r.outcome == "skipped"),
    )


@router.patch(
    "/{user_id}/status",
    response_model=schemas.UserOut,
    summary="Suspend or re-activate a user",
    description="Suspending ends every session that user has open, immediately.",
)
async def update_status(
    user_id: uuid.UUID,
    payload: schemas.UpdateStatusRequest,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:update_status"))],
) -> schemas.UserOut:
    row = await users.update_status(
        db, guard=guard, user_id=user_id, payload=payload, meta=_meta(request)
    )
    return schemas.UserOut.model_validate(row)


@router.post(
    "/{user_id}/roles",
    response_model=schemas.UserDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Give a user a role at a scope",
)
async def assign_role(
    user_id: uuid.UUID,
    payload: schemas.AssignRoleRequest,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("role:assign"))],
) -> schemas.UserDetailOut:
    await users.assign_role(db, guard=guard, user_id=user_id, payload=payload, meta=_meta(request))
    row = await users.get_user(db, guard=guard, user_id=user_id)
    roles = await users.attach_roles(db, [row])
    return schemas.UserDetailOut(
        **schemas.UserOut.model_validate(row).model_dump(), roles=roles.get(row.id, [])
    )


@router.delete(
    "/{user_id}/roles",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Take a role away from a user",
)
async def revoke_role(
    user_id: uuid.UUID,
    payload: schemas.RevokeRoleRequest,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("role:revoke"))],
) -> None:
    await users.revoke_role(db, guard=guard, user_id=user_id, payload=payload, meta=_meta(request))


@router.get(
    "/roles/catalogue",
    response_model=list[schemas.RoleOut],
    summary="Roles you are allowed to give out",
    description="Filtered to roles strictly below your own level, so the UI cannot offer "
    "a choice the backend would reject.",
)
async def list_assignable_roles(
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("role:assign"))],
    purpose: Annotated[
        Literal["assign", "invite"],
        Query(description="'invite' hides platform roles, which a new invitation may not carry."),
    ] = "assign",
) -> list[schemas.RoleOut]:
    from app.modules.rbac import repository as rbac_repo
    from app.modules.rbac.catalog import grantable_ceiling

    ceiling = grantable_ceiling(guard.context.max_rank)
    # Scoped as well as ranked. Custom roles belong to one institute, and
    # offering another institute's inventions here would both leak their structure and
    # produce a choice the assign endpoint goes on to refuse.
    visible_to = None if guard.context.is_platform_staff else guard.context.institute_ids
    roles = await rbac_repo.roles_visible_to(db, visible_to)
    return [
        schemas.RoleOut.model_validate(r)
        for r in roles
        if r.is_active
        and r.rank <= ceiling
        # An invitation creates an account for an unproven address, so it never carries
        # platform-wide authority. The service refuses it too; this keeps the form from
        # offering a choice that would be rejected.
        and not (purpose == "invite" and r.scope_level == "platform")
    ]


# --------------------------------------------------------------------------- guardians


@router.get(
    "/{user_id}/guardians",
    response_model=list[schemas.GuardianOut],
    summary="Who is responsible for this learner",
)
async def list_guardians(
    user_id: uuid.UUID,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:read"))],
) -> list[schemas.GuardianOut]:
    return await users.list_guardians(db, guard=guard, student_id=user_id)


@router.post(
    "/{user_id}/guardians",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a parent or guardian to a learner",
    description="Names the adult by email. If no account exists for that address one is "
    "invited and emailed a setup code; if one does, it is linked rather than duplicated, "
    "so a parent with two children at the school keeps one account.",
)
async def link_guardian(
    user_id: uuid.UUID,
    payload: schemas.GuardianLinkRequest,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:invite"))],
) -> schemas.UserOut:
    parent, message = await users.link_guardian(
        db, guard=guard, student_id=user_id, payload=payload, meta=_meta(request)
    )
    if message is not None:
        background.add_task(send_email, message)
    return schemas.UserOut.model_validate(parent)


@router.delete(
    "/{user_id}/guardians/{parent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a guardian from a learner",
    description="The adult's account is untouched — they may be responsible for other learners.",
)
async def unlink_guardian(
    user_id: uuid.UUID,
    parent_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:invite"))],
) -> None:
    await users.unlink_guardian(
        db, guard=guard, student_id=user_id, parent_id=parent_id, meta=_meta(request)
    )


# ------------------------------------------------------------------- bulk invitation


@router.get(
    "/bulk-invite/template",
    summary="Download the spreadsheet to fill in",
    description="One row per learner, with the parent's details beside the child's. Only "
    "the name and email columns are required; branch, class and parent are used when they "
    "are there.",
    response_class=Response,
    responses={200: {"content": {_XLSX: {}}, "description": "An .xlsx workbook."}},
)
async def bulk_invite_template(
    _: Annotated[Authorized, Depends(require_permission("user:invite"))],
) -> Response:
    return Response(
        content=spreadsheet.build_template(),
        media_type=_XLSX,
        headers={"Content-Disposition": 'attachment; filename="invite-learners.xlsx"'},
    )


@router.post(
    "/bulk-invite/preview",
    response_model=schemas.BulkInviteResponse,
    summary="Check a spreadsheet without inviting anybody",
    description="Reads the file and reports, row by row, what would happen. Nothing is "
    "written and no email is sent.",
)
async def bulk_invite_preview(
    request: Request,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:invite"))],
    file: Annotated[UploadFile, File(description="The filled-in .xlsx template.")],
    institute_id: Annotated[uuid.UUID | None, Form()] = None,
) -> schemas.BulkInviteResponse:
    report, _ = await bulk.run(
        db,
        guard=guard,
        data=await _read_upload(file),
        institute_id=institute_id,
        meta=_meta(request),
        dry_run=True,
    )
    return report


@router.post(
    "/bulk-invite",
    response_model=schemas.BulkInviteResponse,
    summary="Invite everybody in a spreadsheet",
    description="Each row is checked against the same rules as a single invitation, and a "
    "row that fails is reported rather than taking the rest of the file down with it.",
)
async def bulk_invite(
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:invite"))],
    file: Annotated[UploadFile, File(description="The filled-in .xlsx template.")],
    institute_id: Annotated[uuid.UUID | None, Form()] = None,
) -> schemas.BulkInviteResponse:
    report, messages = await bulk.run(
        db,
        guard=guard,
        data=await _read_upload(file),
        institute_id=institute_id,
        meta=_meta(request),
        dry_run=False,
    )
    for message in messages:
        background.add_task(send_email, message)
    return report
