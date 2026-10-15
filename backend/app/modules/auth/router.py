"""Authentication endpoints (PRD §8).

These are the only routes that may be reached without a session. Every one of them is rate
limited, and every response is deliberately uninformative about whether an account exists.

Routers stay thin: read the request, call the service, set cookies, return a schema. Email
delivery is handed to a background task so a slow provider never delays the response.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_access_cookie,
    set_refresh_cookie,
)
from app.modules.auth import schemas
from app.modules.auth import service as auth
from app.modules.auth.service import LoginResult, RequestMeta
from app.modules.notifications.email import EmailMessage, send_email
from app.modules.rbac.deps import CurrentUser, DbSession, client_ip, user_agent

router = APIRouter()

# NOTE: every handler decorated with `@limiter.limit` must take a `response: Response`
# parameter. slowapi writes the X-RateLimit-* headers onto it and raises at request time
# if it is missing — which surfaces as a 500, not a startup error.


def _meta(request: Request) -> RequestMeta:
    return RequestMeta(ip=client_ip(request), user_agent=user_agent(request))


def _apply_session(response: Response, result: LoginResult) -> schemas.LoginResponse:
    """Tokens travel only in httpOnly cookies — never in the body (PRD §7.2)."""
    set_access_cookie(response, result.session.access_token)
    set_refresh_cookie(response, result.session.refresh_token, remembered=result.session.remembered)
    return schemas.LoginResponse(
        user_id=str(result.user.id),
        full_name=result.user.full_name,
        requires_institute_choice=result.institute_count > 1,
    )


def _queue(background: BackgroundTasks, message: EmailMessage | None) -> None:
    if message is not None:
        background.add_task(send_email, message)


@router.post(
    "/register",
    response_model=schemas.LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Direct Learner sign-up",
    description="Creates a Student in the built-in Direct institute and logs them in. "
    "Consent to the privacy policy and terms is mandatory and is recorded.",
)
@limiter.limit(settings.rate_limit_register)
async def register(
    request: Request,
    response: Response,
    payload: schemas.RegisterRequest,
    db: DbSession,
) -> schemas.LoginResponse:
    result = await auth.register_direct_learner(
        db,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        meta=_meta(request),
    )
    return _apply_session(response, result)


@router.post(
    "/login",
    response_model=schemas.LoginResponse,
    summary="Log in with email and password",
    description="Sets the access and refresh cookies. The error message is identical "
    "whether the email is unknown or the password is wrong.",
)
@limiter.limit(settings.rate_limit_login)
async def login(
    request: Request,
    response: Response,
    payload: schemas.LoginRequest,
    db: DbSession,
) -> schemas.LoginResponse:
    result = await auth.login(
        db,
        email=payload.email,
        password=payload.password,
        remember_me=payload.remember_me,
        meta=_meta(request),
    )
    return _apply_session(response, result)


@router.post(
    "/refresh",
    response_model=schemas.LoginResponse,
    summary="Rotate the session tokens",
    description="Issues a new token pair and revokes the old one. Replaying a token that "
    "has already been rotated revokes the whole session family.",
)
async def refresh(request: Request, response: Response, db: DbSession) -> schemas.LoginResponse:
    from app.core.errors import Unauthorized

    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise Unauthorized("Your session has ended. Please log in again.")

    try:
        result = await auth.refresh_session(db, refresh_token=token, meta=_meta(request))
    except Unauthorized:
        # Clear the dead cookies so the browser stops replaying them on every request.
        clear_auth_cookies(response)
        raise
    return _apply_session(response, result)


@router.post(
    "/logout",
    response_model=schemas.MessageResponse,
    summary="Log out of this device",
)
async def logout(request: Request, response: Response, db: DbSession) -> schemas.MessageResponse:
    from app.core.security import ACCESS_COOKIE
    from app.modules.auth.tokens import decode_access_token

    user_id = None
    access = request.cookies.get(ACCESS_COOKIE)
    if access:
        try:
            user_id = decode_access_token(access).user_id
        except Exception:
            user_id = None

    await auth.logout(db, refresh_token=request.cookies.get(REFRESH_COOKIE), user_id=user_id)
    clear_auth_cookies(response)
    return schemas.MessageResponse(message="You have been logged out.")


@router.post(
    "/logout-all",
    response_model=schemas.MessageResponse,
    summary="Log out of every device",
)
async def logout_all(
    request: Request, response: Response, user: CurrentUser, db: DbSession
) -> schemas.MessageResponse:
    count = await auth.logout_everywhere(db, user=user, meta=_meta(request))
    clear_auth_cookies(response)
    return schemas.MessageResponse(message=f"You have been logged out of {count} device(s).")


@router.post(
    "/password/forgot",
    response_model=schemas.MessageResponse,
    summary="Send a password reset code",
    description="Always returns the same message, whether or not the email is registered.",
)
@limiter.limit(settings.rate_limit_forgot_password)
async def forgot_password(
    request: Request,
    response: Response,
    payload: schemas.ForgotPasswordRequest,
    background: BackgroundTasks,
    db: DbSession,
) -> schemas.MessageResponse:
    message = await auth.forgot_password(db, email=payload.email, meta=_meta(request))
    _queue(background, message)
    return schemas.MessageResponse(message=schemas.GENERIC_OTP_SENT)


@router.post(
    "/password/verify-otp",
    response_model=schemas.VerifyOtpResponse,
    summary="Check a reset code",
    description="Returns a short-lived reset token. The code itself can only be used once.",
)
@limiter.limit(settings.rate_limit_verify_otp)
async def verify_otp(
    request: Request,
    response: Response,
    payload: schemas.VerifyOtpRequest,
    db: DbSession,
) -> schemas.VerifyOtpResponse:
    token = await auth.verify_reset_otp(
        db, email=payload.email, code=payload.code, meta=_meta(request)
    )
    return schemas.VerifyOtpResponse(
        reset_token=token, expires_in_seconds=settings.otp_reset_ttl_minutes * 60
    )


@router.post(
    "/password/reset",
    response_model=schemas.MessageResponse,
    summary="Set a new password using a reset token",
    description="Logs the user out of every device and emails a security notice.",
)
async def reset_password(
    request: Request,
    response: Response,
    payload: schemas.ResetPasswordRequest,
    background: BackgroundTasks,
    db: DbSession,
) -> schemas.MessageResponse:
    message = await auth.reset_password(
        db,
        reset_token=payload.reset_token,
        new_password=payload.new_password,
        meta=_meta(request),
    )
    _queue(background, message)
    clear_auth_cookies(response)
    return schemas.MessageResponse(
        message="Your password has been changed. Please log in with your new password."
    )


@router.post(
    "/password/setup",
    response_model=schemas.MessageResponse,
    summary="Set the first password after an invitation",
    description="Verifies the setup code and activates the account.",
)
@limiter.limit(settings.rate_limit_verify_otp)
async def setup_password(
    request: Request,
    response: Response,
    payload: schemas.SetupPasswordRequest,
    background: BackgroundTasks,
    db: DbSession,
) -> schemas.MessageResponse:
    message = await auth.setup_password(
        db,
        email=payload.email,
        code=payload.code,
        new_password=payload.new_password,
        meta=_meta(request),
    )
    _queue(background, message)
    return schemas.MessageResponse(message="Your password has been set. You can now log in.")


@router.post(
    "/password/change",
    response_model=schemas.MessageResponse,
    summary="Change your own password",
    description="Requires the current password. Logs you out of every other device.",
)
async def change_password(
    request: Request,
    response: Response,
    payload: schemas.ChangePasswordRequest,
    background: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
) -> schemas.MessageResponse:
    message = await auth.change_password(
        db,
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        meta=_meta(request),
    )
    _queue(background, message)
    clear_auth_cookies(response)
    return schemas.MessageResponse(message="Your password has been changed. Please log in again.")
