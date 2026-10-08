"""Access-token minting and verification (PRD §7.2).

ES256 rather than HS256: the private key signs, the public key verifies. Only this service
holds the private key today, but when a second service needs to validate a token it can be
given the public key alone — a shared HMAC secret could not be handed out that way.

The ``kid`` header names which key signed a token, so a new key can be introduced while
tokens signed by the old one still verify (PRD §7.2 "key rotation").

Claims are deliberately thin: subject, session, issued-at, expiry. **No roles or permissions
travel in the token.** Authorization is resolved per request against the database, so a
suspension or a revoked role takes effect immediately instead of lingering until the token
expires (PRD §7.2 "instant effect").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError

from app.core.config import settings
from app.core.errors import Unauthorized

ALGORITHM = "ES256"
ISSUER = "dhruv-online-academy"


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """``slots=True`` keeps these small — one is built on every authenticated request."""

    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(
        payload,
        settings.jwt_private_key.get_secret_value(),
        algorithm=ALGORITHM,
        headers={"kid": settings.jwt_key_id},
    )


def decode_access_token(token: str) -> AccessClaims:
    """Verify signature, issuer and expiry. Any failure is one generic 401.

    Distinguishing "expired" from "malformed" would tell an attacker which half of a forged
    token to fix, so the caller gets the same answer either way.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["sub", "sid", "exp", "iat", "iss"]},
        )
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise Unauthorized("Your session has ended. Please log in again.") from exc


# --------------------------------------------------------------------- reset tokens

RESET_TOKEN_TYPE = "pwreset"  # noqa: S105 - a token *type* discriminator, not a secret


@dataclass(frozen=True, slots=True)
class ResetClaims:
    user_id: uuid.UUID
    otp_id: uuid.UUID


def create_reset_token(user_id: uuid.UUID, otp_id: uuid.UUID, ttl_minutes: int) -> str:
    """Short-lived proof that an OTP was verified (PRD §8 "verify-otp -> 10-min reset token").

    It carries the OTP row's id rather than standing alone. Single use is therefore enforced
    by that row, not by the token: a JWT cannot be revoked, but the OTP it points at can be
    marked used — so replaying this token a second time finds a spent code and fails.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "otp": str(otp_id),
        "typ": RESET_TOKEN_TYPE,
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(
        payload,
        settings.jwt_private_key.get_secret_value(),
        algorithm=ALGORITHM,
        headers={"kid": settings.jwt_key_id},
    )


def decode_reset_token(token: str) -> ResetClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["sub", "otp", "typ", "exp", "iss"]},
        )
        # An access token must never be accepted here, and vice versa.
        if payload.get("typ") != RESET_TOKEN_TYPE:
            raise InvalidTokenError("wrong token type")
        return ResetClaims(user_id=uuid.UUID(payload["sub"]), otp_id=uuid.UUID(payload["otp"]))
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise Unauthorized("This reset link has expired. Please start again.") from exc
