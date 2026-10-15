"""Access and reset token handling (PRD §7.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.errors import Unauthorized
from app.modules.auth.tokens import (
    ALGORITHM,
    ISSUER,
    create_access_token,
    create_reset_token,
    decode_access_token,
    decode_reset_token,
)

USER = uuid.uuid4()
SESSION = uuid.uuid4()
OTP = uuid.uuid4()


def test_access_token_round_trips() -> None:
    claims = decode_access_token(create_access_token(USER, SESSION))
    assert claims.user_id == USER
    assert claims.session_id == SESSION


def test_access_token_carries_no_roles_or_permissions() -> None:
    """Authorization is resolved per request, so a revoked role takes effect at once."""
    payload = jwt.decode(
        create_access_token(USER, SESSION),
        settings.jwt_public_key,
        algorithms=[ALGORITHM],
        issuer=ISSUER,
    )
    assert set(payload) == {"sub", "sid", "iss", "iat", "exp"}


def test_access_token_names_the_signing_key() -> None:
    """`kid` is what allows a new key to be introduced without invalidating live tokens."""
    assert (
        jwt.get_unverified_header(create_access_token(USER, SESSION))["kid"] == settings.jwt_key_id
    )


def test_a_tampered_token_is_rejected() -> None:
    token = create_access_token(USER, SESSION)
    head, payload, signature = token.split(".")
    with pytest.raises(Unauthorized):
        decode_access_token(f"{head}.{payload}.{signature[:-4]}AAAA")


def test_garbage_is_rejected() -> None:
    with pytest.raises(Unauthorized):
        decode_access_token("not-a-token")


def test_an_expired_token_is_rejected() -> None:
    expired = jwt.encode(
        {
            "sub": str(USER),
            "sid": str(SESSION),
            "iss": ISSUER,
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
        },
        settings.jwt_private_key.get_secret_value(),
        algorithm=ALGORITHM,
    )
    with pytest.raises(Unauthorized):
        decode_access_token(expired)


def test_an_unsigned_token_is_rejected() -> None:
    """The classic `alg: none` downgrade."""
    forged = jwt.encode(
        {
            "sub": str(USER),
            "sid": str(SESSION),
            "iss": ISSUER,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(Unauthorized):
        decode_access_token(forged)


def test_a_token_from_another_issuer_is_rejected() -> None:
    other = jwt.encode(
        {
            "sub": str(USER),
            "sid": str(SESSION),
            "iss": "somebody-else",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        settings.jwt_private_key.get_secret_value(),
        algorithm=ALGORITHM,
    )
    with pytest.raises(Unauthorized):
        decode_access_token(other)


def test_reset_token_round_trips_and_names_its_otp() -> None:
    claims = decode_reset_token(create_reset_token(USER, OTP, 10))
    assert claims.user_id == USER
    assert claims.otp_id == OTP


def test_an_access_token_cannot_be_used_as_a_reset_token() -> None:
    """Type confusion: a live session must not be able to set a new password without
    knowing the current one."""
    with pytest.raises(Unauthorized):
        decode_reset_token(create_access_token(USER, SESSION))


def test_a_reset_token_cannot_be_used_as_an_access_token() -> None:
    with pytest.raises(Unauthorized):
        decode_access_token(create_reset_token(USER, OTP, 10))


def test_an_expired_reset_token_is_rejected() -> None:
    with pytest.raises(Unauthorized):
        decode_reset_token(create_reset_token(USER, OTP, -1))
