"""Shared test fixtures.

Two tiers of test live here:

* **Unit tests** exercise pure logic — scopes, the permission context, cursors, hashing,
  tokens, schema validation. They need nothing but Python and run everywhere.
* **Integration tests** (``tests/integration/``) drive the real API against a real
  PostgreSQL. They are skipped when no database is reachable, *except* in CI where a
  missing database is a failure rather than a reason to quietly pass.

Keys are generated per session. A committed test key would eventually be copy-pasted into
an environment that matters.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient


def _generate_es256_keypair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


# Settings are read at import time, so the environment must be prepared before any
# application module is imported.
_PRIVATE_KEY, _PUBLIC_KEY = _generate_es256_keypair()
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_PRIVATE_KEY", _PRIVATE_KEY)
os.environ.setdefault("JWT_PUBLIC_KEY", _PUBLIC_KEY)
os.environ.setdefault("OTP_PEPPER", "test-pepper-not-used-anywhere-real")
# Rate limiting stays ON in tests, with limits raised far above anything a test hits.
# Disabling it entirely would skip the slowapi decorator path, where a missing `response`
# parameter only fails at request time — exactly the bug this setup is here to catch.
os.environ.setdefault("RATE_LIMITS_ENABLED", "true")
for _limit in (
    "RATE_LIMIT_LOGIN",
    "RATE_LIMIT_FORGOT_PASSWORD",
    "RATE_LIMIT_VERIFY_OTP",
    "RATE_LIMIT_REGISTER",
    "RATE_LIMIT_DEFAULT",
):
    os.environ.setdefault(_limit, "100000/minute")

from app.core.security import CSRF_HEADER, CSRF_HEADER_VALUE  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def jwt_keys() -> tuple[str, str]:
    return _PRIVATE_KEY, _PUBLIC_KEY


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Anonymous client against the app with no database wired in.

    Suitable only for routes that never touch the database: health, error shape, CSRF.
    """
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={CSRF_HEADER: CSRF_HEADER_VALUE},
    ) as ac:
        yield ac
