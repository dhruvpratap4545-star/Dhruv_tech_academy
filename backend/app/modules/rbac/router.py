"""Access-control endpoints: the role catalogue, custom roles, and per-user exceptions.

Routers here do what every other router in this service does — resolve the target, hand it
to the service, return the shape. Every rule about who may do what lives in ``admin.py``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.errors import NotFound
from app.modules.auth.service import RequestMeta
from app.modules.rbac import admin, schemas
from app.modules.rbac.deps import (
    AuthContextDep,
    CurrentUser,
    DbSession,
    client_ip,
    require_permission,
    user_agent,
)
from app.modules.rbac.service import Authorized
from app.modules.users.models import User

roles_router = APIRouter()
permissions_router = APIRouter()
grants_router = APIRouter()


def _meta(request: Request) -> RequestMeta:
    return RequestMeta(ip=client_ip(request), user_agent=user_agent(request))


async def _target_user(db: DbSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("That user does not exist.")
    return user


# -------------------------------------------------------------------------------- roles


@roles_router.get(
    "",
    response_model=list[schemas.RoleOut],
    summary="Every role you can see, and what each one allows",
    description="The six built-in roles, plus any custom roles belonging to institutes you "
    "work in. Each row says whether you may edit it, so the interface never offers a "
    "button the API would refuse.",
)
async def list_roles(
    db: DbSession,
    context: AuthContextDep,
    _: Annotated[Authorized, Depends(require_permission("role:read"))],
    institute_id: Annotated[
        uuid.UUID | None,
        Query(description="Show each role as this institute sees it, after its own changes."),
    ] = None,
) -> list[schemas.RoleOut]:
    # Default to the caller's own institute: an institute admin asking "what does Faculty
    # allow?" means in their institute, and answering with the untouched definition would
    # be answering a question nobody asked.
    if institute_id is None and not context.is_platform_staff:
        institute_id = context.primary_institute_id
    return await admin.list_roles(db, context, institute_id)


@roles_router.post(
    "",
    response_model=schemas.RoleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a role for one institute",
)
async def create_role(
    payload: schemas.RoleCreateRequest,
    request: Request,
    db: DbSession,
    actor: CurrentUser,
    context: AuthContextDep,
    guard: Annotated[Authorized, Depends(require_permission("role:manage"))],
) -> schemas.RoleOut:
    role = await admin.create_role(
        db, actor=actor, guard=guard, payload=payload, meta=_meta(request)
    )
    return await _one_role(db, context, role.id)


@roles_router.put(
    "/{role_id}/institutes/{institute_id}/permissions",
    response_model=schemas.RoleOut,
    summary="Change what a role allows inside one institute",
    description="Adjusts the role for this institute only — holders of the same role in "
    "other institutes are unaffected. Send the full set the role should allow here; the "
    "server stores the difference from the role's own definition. Sending exactly that "
    "definition clears the customisation.",
)
async def set_institute_role_permissions(
    role_id: uuid.UUID,
    institute_id: uuid.UUID,
    payload: schemas.InstituteRolePermissionsRequest,
    request: Request,
    db: DbSession,
    actor: CurrentUser,
    context: AuthContextDep,
    guard: Annotated[Authorized, Depends(require_permission("role:manage"))],
) -> schemas.RoleOut:
    await admin.set_role_permissions_for_institute(
        db,
        actor=actor,
        guard=guard,
        institute_id=institute_id,
        role_id=role_id,
        permissions=payload.permissions,
        meta=_meta(request),
    )
    return await _one_role(db, context, role_id, institute_id)


@roles_router.patch(
    "/{role_id}",
    response_model=schemas.RoleOut,
    summary="Rename a custom role or change what it allows",
)
async def update_role(
    role_id: uuid.UUID,
    payload: schemas.RoleUpdateRequest,
    request: Request,
    db: DbSession,
    actor: CurrentUser,
    context: AuthContextDep,
    guard: Annotated[Authorized, Depends(require_permission("role:manage"))],
) -> schemas.RoleOut:
    await admin.update_role(
        db, actor=actor, guard=guard, role_id=role_id, payload=payload, meta=_meta(request)
    )
    return await _one_role(db, context, role_id)


@roles_router.post(
    "/{role_id}/archive",
    response_model=schemas.RoleOut,
    summary="Retire a custom role",
    description="Refused while anyone still holds it — move those people first. The role is "
    "archived, never deleted, so past assignments can still name it.",
)
async def archive_role(
    role_id: uuid.UUID,
    request: Request,
    db: DbSession,
    actor: CurrentUser,
    context: AuthContextDep,
    guard: Annotated[Authorized, Depends(require_permission("role:manage"))],
) -> schemas.RoleOut:
    await admin.archive_role(db, actor=actor, guard=guard, role_id=role_id, meta=_meta(request))
    return await _one_role(db, context, role_id)


async def _one_role(
    db: DbSession,
    context: AuthContextDep,
    role_id: uuid.UUID,
    institute_id: uuid.UUID | None = None,
) -> schemas.RoleOut:
    """Re-read through the list builder so a single role and a listed role are the same
    shape — including ``editable``, ``customisable`` and ``holder_count``, none of which
    the ORM object has got."""
    for row in await admin.list_roles(db, context, institute_id):
        if row.id == role_id:
            return row
    raise NotFound("That role does not exist.")


# -------------------------------------------------------------------------- permissions


@permissions_router.get(
    "",
    response_model=list[schemas.PermissionOut],
    summary="Every permission the platform understands",
    description="Grouped for display. This is the vocabulary custom roles are built from.",
)
async def list_permissions(
    _: Annotated[Authorized, Depends(require_permission("role:read"))],
) -> list[schemas.PermissionOut]:
    return admin.list_permissions()


# ------------------------------------------------------------------ per-user exceptions


@grants_router.get(
    "/{user_id}/grants",
    response_model=list[schemas.GrantOut],
    summary="Extra permissions and blocks that apply to one person",
)
async def list_grants(
    user_id: uuid.UUID,
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("user:read"))],
) -> list[schemas.GrantOut]:
    from app.modules.users import service as users

    # Routed through the user read-guard so scoping and the not-found/forbidden split
    # behave exactly as they do everywhere else a user is addressed.
    await users.get_user(db, guard=guard, user_id=user_id)
    return await admin.list_grants(db, user_id)


@grants_router.post(
    "/{user_id}/grants",
    response_model=schemas.GrantOut,
    status_code=status.HTTP_201_CREATED,
    summary="Give one person an extra permission, or block one for them",
    description="A block beats every role, including a Super Admin's. Granting is limited "
    "to permissions you hold yourself at that scope; blocking is not, because it only ever "
    "takes access away.",
)
async def create_grant(
    user_id: uuid.UUID,
    payload: schemas.GrantCreateRequest,
    request: Request,
    db: DbSession,
    actor: CurrentUser,
    guard: Annotated[Authorized, Depends(require_permission("permission:grant"))],
) -> schemas.GrantOut:
    target = await _target_user(db, user_id)
    await admin.create_grant(
        db, actor=actor, guard=guard, target=target, payload=payload, meta=_meta(request)
    )
    return await _one_grant(db, user_id, payload.permission)


@grants_router.delete(
    "/{user_id}/grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an extra permission or a block",
)
async def revoke_grant(
    user_id: uuid.UUID,
    grant_id: uuid.UUID,
    request: Request,
    db: DbSession,
    actor: CurrentUser,
    guard: Annotated[Authorized, Depends(require_permission("permission:grant"))],
) -> None:
    target = await _target_user(db, user_id)
    await admin.revoke_grant(
        db, actor=actor, guard=guard, target=target, grant_id=grant_id, meta=_meta(request)
    )


async def _one_grant(db: DbSession, user_id: uuid.UUID, permission: str) -> schemas.GrantOut:
    for row in await admin.list_grants(db, user_id):
        if row.permission == permission:
            return row
    raise NotFound("That grant does not exist.")
