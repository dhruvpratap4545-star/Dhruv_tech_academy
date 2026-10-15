"""Session and one-time-code collections (PRD §6, §7.2, §7.3).

Neither collection ever stores a usable secret. Refresh tokens are kept as a SHA-256 digest
and OTPs as an HMAC keyed by ``OTP_PEPPER``, so a database leak on its own yields nothing an
attacker can present back to the API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.core.db import TimestampedDocument

OTP_PURPOSES = ("reset", "setup")


class RefreshToken(TimestampedDocument):
    """One document per issued refresh token.

    Rotation means every refresh writes a new one and revokes the old, all sharing a
    ``family_id``. Presenting an already-revoked token is the signature of a stolen token,
    so the whole family is revoked at once (PRD §7.2).
    """

    user_id: uuid.UUID
    token_hash: str = Field(max_length=64)
    family_id: uuid.UUID
    # Mirrors the access token's `sid` claim, so revoking a session invalidates both.
    session_id: uuid.UUID
    user_agent: str | None = Field(default=None, max_length=255)
    ip: str | None = Field(default=None, max_length=45)
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = Field(default=None, max_length=40)

    class Settings:
        name = "refresh_tokens"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("token_hash", ASCENDING)], unique=True, name="uq_refresh_tokens_hash"),
            # Logout-all and reuse detection both sweep a user's live tokens.
            IndexModel(
                [("user_id", ASCENDING), ("revoked_at", ASCENDING)],
                name="ix_refresh_tokens_user_live",
            ),
            IndexModel([("family_id", ASCENDING)], name="ix_refresh_tokens_family"),
            IndexModel([("expires_at", ASCENDING)], name="ix_refresh_tokens_expires_at"),
        ]


class PasswordOtp(TimestampedDocument):
    """A six-digit code for password reset or first-time setup.

    Single use, attempt-capped, and superseded the moment a new one is requested for the
    same purpose — so a forwarded old email is worthless (PRD §7.3).
    """

    user_id: uuid.UUID
    purpose: Literal["reset", "setup"]
    otp_hash: str = Field(max_length=64)
    expires_at: datetime
    attempts: int = Field(default=0, ge=0)
    used_at: datetime | None = None
    superseded_at: datetime | None = None
    request_ip: str | None = Field(default=None, max_length=45)

    class Settings:
        name = "password_otps"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("user_id", ASCENDING), ("purpose", ASCENDING), ("created_at", DESCENDING)],
                name="ix_password_otps_user_purpose_created",
            ),
            IndexModel([("expires_at", ASCENDING)], name="ix_password_otps_expires_at"),
        ]
