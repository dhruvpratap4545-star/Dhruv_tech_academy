"""User, profile and role endpoints (PRD §8)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

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
from app.modules.users import schemas
from app.modules.users import service as users

router = APIRouter()
me_router = APIRouter()

Limit = Annotated[int, Query(ge=1, le=100, description="Rows per page (max 100).")]
Cursor = Annotated[str | None, Query(description="Opaque cursor from the previous page.")]


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
    rows, next_cursor = await users.list_users(
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
    return Page[schemas.UserDetailOut](items=items, next_cursor=next_cursor)


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
