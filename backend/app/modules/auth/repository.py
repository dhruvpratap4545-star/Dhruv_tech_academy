"""Queries for sessions, OTPs and user lookup during authentication."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import PasswordOtp, RefreshToken
from app.modules.users.models import User


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Case-insensitive, matching the ``lower(email)`` unique index so PostgreSQL can use it."""
    stmt = select(User).where(func.lower(User.email) == email.strip().lower())
    return await db.scalar(stmt)


async def email_exists(db: AsyncSession, email: str) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.strip().lower()).limit(1)
    return await db.scalar(stmt) is not None


# --------------------------------------------------------------------------- sessions


async def get_refresh_token(db: AsyncSession, token_hash: str) -> RefreshToken | None:
    return await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))


def add_refresh_token(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    token_hash: str,
    family_id: uuid.UUID,
    session_id: uuid.UUID,
    expires_at: datetime,
    user_agent: str | None,
    ip: str | None,
) -> RefreshToken:
    row = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        family_id=family_id,
        session_id=session_id,
        expires_at=expires_at,
        user_agent=user_agent,
        ip=ip,
    )
    db.add(row)
    return row


async def revoke_token_family(db: AsyncSession, family_id: uuid.UUID, reason: str) -> int:
    """Revoke every live token in a family in one statement.

    Used both for normal rotation cleanup and for reuse detection, where speed matters —
    the attacker and the real user are racing.
    """
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    return result.rowcount or 0


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID, reason: str) -> int:
    """Logout everywhere. One UPDATE, no matter how many devices."""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    return result.rowcount or 0


async def revoke_single_token(db: AsyncSession, token_id: uuid.UUID, reason: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == token_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )


# ------------------------------------------------------------------------------- OTPs


async def supersede_live_otps(db: AsyncSession, user_id: uuid.UUID, purpose: str) -> None:
    """A new code cancels the previous one (PRD §7.3), so a forwarded old email is useless."""
    await db.execute(
        update(PasswordOtp)
        .where(
            PasswordOtp.user_id == user_id,
            PasswordOtp.purpose == purpose,
            PasswordOtp.used_at.is_(None),
            PasswordOtp.superseded_at.is_(None),
        )
        .values(superseded_at=datetime.now(UTC))
    )


def add_otp(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    purpose: str,
    otp_hash: str,
    expires_at: datetime,
    request_ip: str | None,
) -> PasswordOtp:
    row = PasswordOtp(
        user_id=user_id,
        purpose=purpose,
        otp_hash=otp_hash,
        expires_at=expires_at,
        request_ip=request_ip,
    )
    db.add(row)
    return row


async def get_live_otp(db: AsyncSession, user_id: uuid.UUID, purpose: str) -> PasswordOtp | None:
    """The one code still in play for this user and purpose."""
    stmt = (
        select(PasswordOtp)
        .where(
            PasswordOtp.user_id == user_id,
            PasswordOtp.purpose == purpose,
            PasswordOtp.used_at.is_(None),
            PasswordOtp.superseded_at.is_(None),
        )
        .order_by(PasswordOtp.created_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt)


async def latest_otp(db: AsyncSession, user_id: uuid.UUID, purpose: str) -> PasswordOtp | None:
    """Most recent code of any state — used for the resend cooldown (PRD §7.3)."""
    stmt = (
        select(PasswordOtp)
        .where(PasswordOtp.user_id == user_id, PasswordOtp.purpose == purpose)
        .order_by(PasswordOtp.created_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt)


async def count_otp_requests_since(
    db: AsyncSession, user_id: uuid.UUID, purpose: str, since: datetime
) -> int:
    """Per-account request cap (PRD §7.3: 3 per email per hour).

    Counted in the database rather than in memory so the cap holds across instances and
    survives a restart — unlike the IP-based limiter, which is best-effort by design.
    """
    stmt = select(func.count()).where(
        PasswordOtp.user_id == user_id,
        PasswordOtp.purpose == purpose,
        PasswordOtp.created_at >= since,
    )
    return int(await db.scalar(stmt) or 0)
