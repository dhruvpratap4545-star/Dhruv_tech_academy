"""FastAPI dependencies for authentication and authorization.

Every protected route depends on ``require_permission("resource:action")``. Public routes
are the ones listed in PRD §8: register, login, refresh, the password flows, and healthz.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import Forbidden, Unauthorized
from app.modules.auth.tokens import decode_access_token
from app.modules.rbac import service
from app.modules.rbac.context import AuthContext
from app.modules.rbac.service import Authorized
from app.modules.users.models import User

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(request: Request, db: DbSession) -> User:
    """Resolve the access-token cookie to a live, active user.

    The user row is re-read on every request rather than trusted from the token. That is
    what makes a suspension take effect immediately (PRD §7.2 "instant effect") — the cost
    is one primary-key lookup, which PostgreSQL serves from cache.
    """
    from app.core.security import ACCESS_COOKIE

    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise Unauthorized()

    claims = decode_access_token(token)
    user = await db.get(User, claims.user_id)
    if user is None:
        raise Unauthorized()
    if user.status == "suspended":
        raise Forbidden("Your account has been suspended. Please contact your administrator.")
    if not user.is_active:
        raise Unauthorized()

    # Stashed so the audit writer can record the session without re-decoding the token.
    request.state.session_id = claims.session_id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_auth_context(user: CurrentUser, db: DbSession) -> AuthContext:
    return await service.get_context(db, user.id)


AuthContextDep = Annotated[AuthContext, Depends(get_auth_context)]


def require_permission(
    permission: str,
) -> Callable[..., Coroutine[Any, Any, Authorized]]:
    """Guard factory.

    Confirms the caller holds ``permission`` somewhere and hands back an ``Authorized``.
    The route then calls ``ensure(scope)`` once it knows which institute, branch or class
    the request actually targets — see ``rbac.service.Authorized``.
    """

    async def dependency(context: AuthContextDep, db: DbSession) -> Authorized:
        if not context.holds(permission):
            raise Forbidden()
        return Authorized(db, context, permission)

    return dependency


def require_self_or_permission(
    permission: str,
) -> Callable[..., Coroutine[Any, Any, Authorized | None]]:
    """For routes a user may call on their own record, or on others' with a permission.

    Returns ``None`` when the caller is acting on themselves, so the route can skip the
    scope check entirely.
    """

    async def dependency(context: AuthContextDep, db: DbSession) -> Authorized | None:
        return Authorized(db, context, permission) if context.holds(permission) else None

    return dependency


def client_ip(request: Request) -> str | None:
    """Caller IP, honouring Render's proxy headers.

    Uvicorn runs with ``--proxy-headers``, so ``request.client.host`` is already the real
    client address. ``X-Forwarded-For`` is read only as a fallback and never trusted for
    authorization — it is attacker-controlled. It is used for rate limiting and audit rows,
    where a wrong value costs little.
    """
    if request.client is not None and request.client.host:
        return request.client.host
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else None


def user_agent(request: Request) -> str | None:
    agent = request.headers.get("user-agent")
    return agent[:255] if agent else None


def session_id_of(request: Request) -> uuid.UUID | None:
    return getattr(request.state, "session_id", None)
