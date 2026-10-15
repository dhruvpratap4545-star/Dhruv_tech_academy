"""Queries for sessions, OTPs and user lookup during authentication."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.core.db import Db, utcnow
from app.modules.auth.models import PasswordOtp, RefreshToken
from app.modules.users.models import User


def _normalise(email: str) -> str:
    return email.strip().lower()


async def get_user_by_email(db: Db, email: str) -> User | None:
    """Emails are stored lowercased, so equality is the case-insensitive lookup and it uses
    the unique index."""
    return await db.find_one(User, {"email": _normalise(email)})


async def email_exists(db: Db, email: str) -> bool:
    return await db.exists(User, {"email": _normalise(email)})


# --------------------------------------------------------------------------- sessions


async def get_refresh_token(db: Db, token_hash: str) -> RefreshToken | None:
    return await db.find_one(RefreshToken, {"token_hash": token_hash})


def add_refresh_token(
    db: Db,
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


async def _revoke(db: Db, match: dict, reason: str) -> int:
    """Revoke every live token matching ``match``; returns how many that was.

    Counted first and written at commit, so a request that fails afterwards revokes
    nothing — the same outcome as the UPDATE being rolled back.
    """
    live = {**match, "revoked_at": None}
    count = await db.count(RefreshToken, live)
    if count:
        db.update_many(RefreshToken, live, {"revoked_at": utcnow(), "revoked_reason": reason})
    return count


async def revoke_token_family(db: Db, family_id: uuid.UUID, reason: str) -> int:
    """Revoke every live token in a family.

    Used both for normal rotation cleanup and for reuse detection, where speed matters —
    the attacker and the real user are racing.
    """
    return await _revoke(db, {"family_id": family_id}, reason)


async def revoke_all_user_tokens(db: Db, user_id: uuid.UUID, reason: str) -> int:
    """Logout everywhere. One update, no matter how many devices."""
    return await _revoke(db, {"user_id": user_id}, reason)


async def revoke_single_token(db: Db, token_id: uuid.UUID, reason: str) -> None:
    await _revoke(db, {"_id": token_id}, reason)


# ------------------------------------------------------------------------------- OTPs


async def supersede_live_otps(db: Db, user_id: uuid.UUID, purpose: str) -> None:
    """A new code cancels the previous one (PRD §7.3), so a forwarded old email is useless."""
    db.update_many(
        PasswordOtp,
        {"user_id": user_id, "purpose": purpose, "used_at": None, "superseded_at": None},
        {"superseded_at": utcnow()},
    )


def add_otp(
    db: Db,
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


async def get_live_otp(db: Db, user_id: uuid.UUID, purpose: str) -> PasswordOtp | None:
    """The one code still in play for this user and purpose."""
    return await db.find_one(
        PasswordOtp,
        {"user_id": user_id, "purpose": purpose, "used_at": None, "superseded_at": None},
        sort=[("created_at", -1)],
    )


async def latest_otp(db: Db, user_id: uuid.UUID, purpose: str) -> PasswordOtp | None:
    """Most recent code of any state — used for the resend cooldown (PRD §7.3)."""
    return await db.find_one(
        PasswordOtp, {"user_id": user_id, "purpose": purpose}, sort=[("created_at", -1)]
    )


async def count_otp_requests_since(
    db: Db, user_id: uuid.UUID, purpose: str, since: datetime
) -> int:
    """Per-account request cap (PRD §7.3: 3 per email per hour).

    Counted in the database rather than in memory so the cap holds across instances and
    survives a restart — unlike the IP-based limiter, which is best-effort by design.
    """
    return await db.count(
        PasswordOtp, {"user_id": user_id, "purpose": purpose, "created_at": {"$gte": since}}
    )


async def live_sessions(db: Db, user_id: uuid.UUID) -> list[RefreshToken]:
    return await db.find(
        RefreshToken,
        {"user_id": user_id, "revoked_at": None, "expires_at": {"$gt": utcnow()}},
    )
