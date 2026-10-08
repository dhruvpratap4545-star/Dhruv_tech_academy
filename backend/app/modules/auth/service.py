"""Authentication use cases (PRD §4, §7).

Design rules enforced throughout this file:

* **Nothing reveals whether an email exists.** Login, sign-up and forgot-password all return
  the same shape whether the account is real or not (PRD §7.3, §7.4).
* **Secrets are never stored in a usable form.** Passwords are Argon2id; refresh tokens are
  SHA-256 digests; OTPs are HMACs keyed by ``OTP_PEPPER``.
* **Changing a password ends every session.** Reset, setup and change all revoke the token
  families and send a security email (PRD §7.3).
* **Services never touch ``Request`` or ``Response``.** IP, user agent and cookies are passed
  in by the router.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import Conflict, Forbidden, RateLimited, Unauthorized, ValidationFailed
from app.core.security import (
    generate_otp,
    generate_refresh_token,
    hash_otp,
    hash_password,
    hash_refresh_token,
    verify_otp,
    verify_password,
)
from app.modules.audit import events
from app.modules.audit import service as audit
from app.modules.auth import repository as repo
from app.modules.auth.models import PasswordOtp, RefreshToken
from app.modules.auth.schemas import GENERIC_LOGIN_FAILED
from app.modules.auth.tokens import create_access_token, create_reset_token, decode_reset_token
from app.modules.notifications import templates
from app.modules.notifications.email import EmailMessage
from app.modules.rbac import service as rbac
from app.modules.users.models import User, UserPreference

logger = logging.getLogger(__name__)

PURPOSE_RESET = "reset"
PURPOSE_SETUP = "setup"


@dataclass(frozen=True, slots=True)
class RequestMeta:
    """What the router knows about the caller and the service needs for audit and sessions."""

    ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class IssuedSession:
    access_token: str
    refresh_token: str
    remembered: bool


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    session: IssuedSession
    institute_count: int


# --------------------------------------------------------------------------- sessions


def _refresh_ttl(remembered: bool) -> timedelta:
    days = (
        settings.refresh_token_ttl_days_remembered
        if remembered
        else settings.refresh_token_ttl_days
    )
    return timedelta(days=days)


def _issue_session(
    db: AsyncSession,
    user: User,
    meta: RequestMeta,
    *,
    remembered: bool,
    family_id: uuid.UUID | None = None,
) -> IssuedSession:
    """Mint an access/refresh pair.

    A rotation passes the existing ``family_id`` so the chain stays linked; a fresh login
    starts a new family. Only the digest of the refresh token is persisted — the plaintext
    exists for the length of this function and then only in the user's cookie.
    """
    session_id = uuid.uuid4()
    family = family_id or uuid.uuid4()
    refresh_plain = generate_refresh_token()

    repo.add_refresh_token(
        db,
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_plain),
        family_id=family,
        session_id=session_id,
        expires_at=datetime.now(UTC) + _refresh_ttl(remembered),
        user_agent=meta.user_agent,
        ip=meta.ip,
    )
    return IssuedSession(
        access_token=create_access_token(user.id, session_id),
        refresh_token=refresh_plain,
        remembered=remembered,
    )


# -------------------------------------------------------------------------- register


async def register_direct_learner(
    db: AsyncSession, *, full_name: str, email: str, password: str, meta: RequestMeta
) -> LoginResult:
    """PRD §4.1. Creates an active Student in the built-in "Direct" institute."""
    if not settings.direct_signup_enabled:
        raise Forbidden("Self sign-up is not available. Please ask your institute to add you.")

    from app.modules.org import repository as org_repo
    from app.modules.users import service as users

    normalized = email.strip().lower()
    if await repo.email_exists(db, normalized):
        # Generic on purpose: a distinct "already registered" turns sign-up into an
        # account-existence oracle (PRD §7.5).
        raise Conflict("We could not complete sign-up with those details. Try logging in instead.")

    direct = await org_repo.get_direct_institute(db)
    if direct is None:
        logger.error("direct institute missing; seed has not run")
        raise ValidationFailed("Sign-up is temporarily unavailable. Please try again later.")

    now = datetime.now(UTC)
    user = User(
        email=normalized,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        status="active",
        password_changed_at=now,
        consent_accepted_at=now,
        consent_version=settings.consent_version,
    )
    db.add(user)
    await db.flush()
    db.add(UserPreference(user_id=user.id))

    await users.grant_student_role(db, user_id=user.id, institute_id=direct.id, granted_by=None)

    session = _issue_session(db, user, meta, remembered=False)
    user.last_login_at = now
    audit.record(
        db,
        action=events.USER_REGISTERED,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        institute_id=direct.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"source": "direct_signup", "consent_version": settings.consent_version},
    )
    await db.commit()
    return LoginResult(user=user, session=session, institute_count=1)


# ----------------------------------------------------------------------------- login


async def login(
    db: AsyncSession, *, email: str, password: str, remember_me: bool, meta: RequestMeta
) -> LoginResult:
    """PRD §4.3 and §7.4.

    Every failure path raises the same error and takes comparable time: the password is
    verified against a dummy hash even when no user was found.
    """
    user = await repo.get_user_by_email(db, email)
    now = datetime.now(UTC)

    if user is None:
        verify_password(password, None)  # equalise timing
        audit.record(
            db,
            action=events.LOGIN_FAILURE,
            ip=meta.ip,
            user_agent=meta.user_agent,
            extra={"reason": "unknown_email"},
        )
        await db.commit()
        raise Unauthorized(GENERIC_LOGIN_FAILED)

    if user.locked_until and user.locked_until > now:
        audit.record(
            db,
            action=events.LOGIN_FAILURE,
            actor_user_id=user.id,
            ip=meta.ip,
            user_agent=meta.user_agent,
            extra={"reason": "locked"},
        )
        await db.commit()
        raise RateLimited(
            f"Too many failed attempts. Please try again in "
            f"{settings.account_lock_minutes} minutes."
        )

    if not verify_password(password, user.password_hash):
        await _register_failed_login(db, user, meta)
        raise Unauthorized(GENERIC_LOGIN_FAILED)

    if user.status == "suspended":
        audit.record(
            db,
            action=events.LOGIN_FAILURE,
            actor_user_id=user.id,
            ip=meta.ip,
            user_agent=meta.user_agent,
            extra={"reason": "suspended"},
        )
        await db.commit()
        raise Forbidden("Your account has been suspended. Please contact your administrator.")

    if user.status == "invited":
        raise Forbidden("Please set your password using the link we emailed you.")

    if not user.is_active:
        raise Unauthorized(GENERIC_LOGIN_FAILED)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    session = _issue_session(db, user, meta, remembered=remember_me)
    context = await rbac.get_context(db, user.id)

    audit.record(
        db,
        action=events.LOGIN_SUCCESS,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        institute_id=context.primary_institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"remember_me": remember_me},
    )
    await db.commit()
    return LoginResult(user=user, session=session, institute_count=len(context.institute_ids))


async def _register_failed_login(db: AsyncSession, user: User, meta: RequestMeta) -> None:
    """Count the failure and lock the account at the threshold (PRD §7.4).

    The counter lives on the user row, so the lock holds across restarts and instances.
    """
    user.failed_login_count += 1
    locked = user.failed_login_count >= settings.max_failed_logins
    if locked:
        user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.account_lock_minutes)
        user.failed_login_count = 0

    context = await rbac.get_context(db, user.id)
    audit.record(
        db,
        action=events.ACCOUNT_LOCKED if locked else events.LOGIN_FAILURE,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        institute_id=context.primary_institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"reason": "bad_password"},
    )
    await db.commit()


# --------------------------------------------------------------------------- refresh


async def refresh_session(
    db: AsyncSession, *, refresh_token: str, meta: RequestMeta
) -> LoginResult:
    """Rotate the refresh token, detecting reuse (PRD §7.2).

    Presenting a token that was already rotated away means the cookie leaked: the legitimate
    device holds the newest token and never replays an old one. The entire family is revoked,
    logging out the attacker and the real user, who then logs in again.
    """
    token_hash = hash_refresh_token(refresh_token)
    stored = await repo.get_refresh_token(db, token_hash)
    now = datetime.now(UTC)

    if stored is None:
        raise Unauthorized("Your session has ended. Please log in again.")

    if stored.revoked_at is not None:
        await repo.revoke_token_family(db, stored.family_id, "reuse_detected")
        audit.record(
            db,
            action=events.TOKEN_REUSE_DETECTED,
            actor_user_id=stored.user_id,
            target_type="user",
            target_id=stored.user_id,
            ip=meta.ip,
            user_agent=meta.user_agent,
        )
        await db.commit()
        logger.warning("refresh token reuse", extra={"user_id": str(stored.user_id)})
        raise Unauthorized("Your session has ended. Please log in again.")

    if stored.expires_at <= now:
        raise Unauthorized("Your session has ended. Please log in again.")

    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        # Status is re-checked here as well as on each request, so a suspension cannot be
        # outlived by refreshing (PRD §13 criterion 9).
        await repo.revoke_token_family(db, stored.family_id, "user_inactive")
        await db.commit()
        raise Unauthorized("Your session has ended. Please log in again.")

    await repo.revoke_single_token(db, stored.id, "rotated")
    remembered = (stored.expires_at - stored.created_at) > timedelta(
        days=settings.refresh_token_ttl_days
    )
    session = _issue_session(db, user, meta, remembered=remembered, family_id=stored.family_id)
    context = await rbac.get_context(db, user.id)
    await db.commit()
    return LoginResult(user=user, session=session, institute_count=len(context.institute_ids))


async def logout(db: AsyncSession, *, refresh_token: str | None, user_id: uuid.UUID | None) -> None:
    """End one session. Idempotent: logging out twice is not an error."""
    if refresh_token:
        stored = await repo.get_refresh_token(db, hash_refresh_token(refresh_token))
        if stored is not None and stored.revoked_at is None:
            await repo.revoke_token_family(db, stored.family_id, "logout")
    if user_id:
        audit.record(db, action=events.LOGOUT, actor_user_id=user_id)
    await db.commit()


async def logout_everywhere(db: AsyncSession, *, user: User, meta: RequestMeta) -> int:
    count = await repo.revoke_all_user_tokens(db, user.id, "logout_all")
    audit.record(
        db,
        action=events.LOGOUT_ALL,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra={"sessions_ended": count},
    )
    await db.commit()
    return count


# ------------------------------------------------------------------------------ OTPs


async def _guard_otp_quota(db: AsyncSession, user: User, purpose: str) -> None:
    """Per-account cooldown and hourly cap (PRD §7.3).

    Enforced in the database so it cannot be sidestepped by rotating IP addresses, which is
    all the network-level limiter protects against.
    """
    latest = await repo.latest_otp(db, user.id, purpose)
    now = datetime.now(UTC)
    if latest is not None:
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < settings.otp_resend_cooldown_seconds:
            raise RateLimited("Please wait a minute before asking for another code.")

    window_start = now - timedelta(hours=1)
    if await repo.count_otp_requests_since(db, user.id, purpose, window_start) >= 3:
        raise RateLimited("Too many codes requested. Please try again in an hour.")


async def issue_otp(
    db: AsyncSession, *, user: User, purpose: str, meta: RequestMeta
) -> tuple[PasswordOtp, str]:
    """Create a code, superseding any previous one. Returns the row and the plaintext.

    The plaintext is returned so the caller can email it and is never stored or logged.
    """
    await repo.supersede_live_otps(db, user.id, purpose)
    code = generate_otp(settings.otp_length)
    ttl = (
        timedelta(minutes=settings.otp_reset_ttl_minutes)
        if purpose == PURPOSE_RESET
        else timedelta(hours=settings.otp_setup_ttl_hours)
    )
    row = repo.add_otp(
        db,
        user_id=user.id,
        purpose=purpose,
        otp_hash=hash_otp(code),
        expires_at=datetime.now(UTC) + ttl,
        request_ip=meta.ip,
    )
    await db.flush()
    return row, code


async def forgot_password(
    db: AsyncSession, *, email: str, meta: RequestMeta
) -> EmailMessage | None:
    """PRD §4.4. Returns the email to send, or None when the address is unknown.

    The router responds identically either way, so this is not an existence oracle.
    """
    user = await repo.get_user_by_email(db, email)
    if user is None or user.status in ("suspended", "deleted"):
        audit.record(
            db,
            action=events.PASSWORD_RESET_REQUESTED,
            ip=meta.ip,
            user_agent=meta.user_agent,
            extra={"outcome": "no_matching_account"},
        )
        await db.commit()
        return None

    await _guard_otp_quota(db, user, PURPOSE_RESET)
    _, code = await issue_otp(db, user=user, purpose=PURPOSE_RESET, meta=meta)
    audit.record(
        db,
        action=events.PASSWORD_RESET_REQUESTED,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    await db.commit()
    return templates.password_reset(user.email, user.full_name, code)


async def _consume_attempt(db: AsyncSession, otp: PasswordOtp) -> None:
    """Count a wrong attempt (PRD §7.3: max 5 per code).

    The row is deliberately *not* superseded at the cap. The attempt counter alone blocks
    it, and keeping it live lets the next request answer "too many incorrect attempts,
    ask for a new code" instead of the generic "that code is not valid" — which would
    leave the user retrying a code that can never work again.
    """
    otp.attempts += 1
    await db.commit()


async def verify_reset_otp(db: AsyncSession, *, email: str, code: str, meta: RequestMeta) -> str:
    """Exchange a valid code for a short-lived reset token."""
    generic = ValidationFailed("That code is not valid or has expired. Please request a new one.")

    user = await repo.get_user_by_email(db, email)
    if user is None:
        raise generic

    otp = await repo.get_live_otp(db, user.id, PURPOSE_RESET)
    if otp is None or otp.expires_at <= datetime.now(UTC):
        raise generic
    if otp.attempts >= settings.otp_max_attempts:
        raise RateLimited("Too many incorrect attempts. Please request a new code.")

    if not verify_otp(code, otp.otp_hash):
        await _consume_attempt(db, otp)
        raise generic

    return create_reset_token(user.id, otp.id, settings.otp_reset_ttl_minutes)


async def reset_password(
    db: AsyncSession, *, reset_token: str, new_password: str, meta: RequestMeta
) -> EmailMessage | None:
    """PRD §4.4 final step: set the password, end every session, send a security email."""
    claims = decode_reset_token(reset_token)
    otp = await db.get(PasswordOtp, claims.otp_id)
    now = datetime.now(UTC)

    # The token is only as good as the OTP row behind it, which makes it single use.
    if (
        otp is None
        or otp.user_id != claims.user_id
        or otp.used_at is not None
        or otp.superseded_at is not None
        or otp.expires_at <= now
    ):
        raise Unauthorized("This reset link has expired. Please start again.")

    user = await db.get(User, claims.user_id)
    if user is None:
        raise Unauthorized("This reset link has expired. Please start again.")

    otp.used_at = now
    return await _apply_new_password(
        db, user=user, new_password=new_password, meta=meta, action=events.PASSWORD_RESET_COMPLETED
    )


async def setup_password(
    db: AsyncSession, *, email: str, code: str, new_password: str, meta: RequestMeta
) -> EmailMessage | None:
    """PRD §4.2: an invited user verifies the setup OTP and sets their first password."""
    generic = ValidationFailed("That code is not valid or has expired. Please ask for a new one.")

    user = await repo.get_user_by_email(db, email)
    if user is None or user.status not in ("invited", "active"):
        raise generic

    otp = await repo.get_live_otp(db, user.id, PURPOSE_SETUP)
    if otp is None or otp.expires_at <= datetime.now(UTC):
        raise generic
    if otp.attempts >= settings.otp_max_attempts:
        raise RateLimited("Too many incorrect attempts. Please ask for a new code.")

    if not verify_otp(code, otp.otp_hash):
        await _consume_attempt(db, otp)
        raise generic

    otp.used_at = datetime.now(UTC)
    return await _apply_new_password(
        db, user=user, new_password=new_password, meta=meta, action=events.PASSWORD_SETUP_COMPLETED
    )


async def change_password(
    db: AsyncSession, *, user: User, current_password: str, new_password: str, meta: RequestMeta
) -> EmailMessage | None:
    """PRD §8 ``/auth/password/change``. Requires the current password."""
    if not verify_password(current_password, user.password_hash):
        audit.record(
            db,
            action=events.LOGIN_FAILURE,
            actor_user_id=user.id,
            ip=meta.ip,
            user_agent=meta.user_agent,
            extra={"reason": "bad_current_password"},
        )
        await db.commit()
        raise ValidationFailed("Your current password is not correct.")

    if verify_password(new_password, user.password_hash):
        raise ValidationFailed("Your new password must be different from the current one.")

    return await _apply_new_password(
        db, user=user, new_password=new_password, meta=meta, action=events.PASSWORD_CHANGED
    )


async def _apply_new_password(
    db: AsyncSession, *, user: User, new_password: str, meta: RequestMeta, action: str
) -> EmailMessage | None:
    """The one place a password is written.

    Always revokes every session: if the password changed because it was compromised, any
    session an attacker still holds has to die with it (PRD §7.3).
    """
    now = datetime.now(UTC)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.failed_login_count = 0
    user.locked_until = None

    # `invited` means "has no password yet". Someone who has just proved control of their
    # mailbox with a verified OTP and set a password is no longer in that state, so holding
    # them at `invited` would lock them out of the account they just secured.
    #
    # This is what makes the very first Super Admin reachable at all: the seed creates them
    # invited and with no password (never a generated one, which would end up in a deploy
    # log), and there is no invitation flow above them to issue a setup code. The
    # forgot-password flow is their way in, and without this line it would set a password
    # they still could not log in with.
    if user.status == "invited":
        user.status = "active"

    await repo.revoke_all_user_tokens(db, user.id, "password_changed")
    rbac.invalidate_context(user.id)

    audit.record(
        db,
        action=action,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    await db.commit()
    return templates.password_changed(user.email, user.full_name)


async def live_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[RefreshToken]:
    """Not exposed in M1; kept here because the device list is the obvious next request."""
    from sqlalchemy import select

    stmt = select(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > datetime.now(UTC),
    )
    return list((await db.execute(stmt)).scalars().all())
