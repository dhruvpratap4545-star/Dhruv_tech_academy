"""Session and one-time-code tables (PRD §6, §7.2, §7.3).

Neither table ever stores a usable secret. Refresh tokens are kept as a SHA-256 digest and
OTPs as an HMAC keyed by ``OTP_PEPPER``, so a database leak on its own yields nothing a
attacker can present back to the API.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, MediumStr, TimestampMixin, Uuid, UuidPkMixin

OTP_PURPOSES = ("reset", "setup")


class RefreshToken(UuidPkMixin, TimestampMixin, Base):
    """One row per issued refresh token.

    Rotation means every refresh writes a new row and revokes the old one, all sharing a
    ``family_id``. Presenting an already-revoked token is the signature of a stolen token,
    so the whole family is revoked at once (PRD §7.2).
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        # Logout-all and reuse detection both sweep a user's live tokens.
        Index(
            "ix_refresh_tokens_user_id_live",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_refresh_tokens_family_id", "family_id"),
        # Lets a periodic cleanup job delete expired rows without a sequential scan.
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Mirrors the access token's `sid` claim, so revoking a session invalidates both.
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(MediumStr)
    ip: Mapped[str | None] = mapped_column(INET)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(40))


class PasswordOtp(UuidPkMixin, TimestampMixin, Base):
    """A six-digit code for password reset or first-time setup.

    Single use, attempt-capped, and superseded the moment a new one is requested for the
    same purpose — so a forwarded old email is worthless (PRD §7.3).
    """

    __tablename__ = "password_otps"
    __table_args__ = (
        CheckConstraint("purpose IN ('reset', 'setup')", name="password_otps_purpose"),
        CheckConstraint("attempts >= 0", name="password_otps_attempts"),
        # Verification looks up the one live code for a user and purpose.
        Index(
            "ix_password_otps_user_id_purpose_live",
            "user_id",
            "purpose",
            postgresql_where=text("used_at IS NULL AND superseded_at IS NULL"),
        ),
        Index("ix_password_otps_expires_at", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_ip: Mapped[str | None] = mapped_column(INET)
