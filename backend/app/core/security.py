"""Password hashing, OTP/token secrets and cookie handling (PRD §7).

Rules that must not be relaxed:
- passwords are Argon2id, never stored or logged in clear text;
- OTPs and refresh tokens are stored only as hashes;
- secret comparisons use ``hmac.compare_digest``;
- auth cookies are httpOnly + SameSite=Lax, and Secure outside local development.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata

from fastapi import Response
from pwdlib import PasswordHash

from app.core.config import settings

password_hasher = PasswordHash.recommended()

ACCESS_COOKIE = "dhruv_access"
REFRESH_COOKIE = "dhruv_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "XMLHttpRequest"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Timing defence: unknown emails are still compared against a real Argon2 hash so that
# "email does not exist" and "wrong password" take the same time (PRD §7.4).
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def normalise_password(plain: str) -> str:
    """Unicode-normalise before hashing or verifying, on both paths.

    The same password typed in Devanagari, Kannada or Tamil can arrive as different bytes
    from different keyboards — iOS composes (NFC), several Linux input methods decompose
    (NFD). Argon2 sees bytes, so without this the account is set up from one device and
    refuses the *correct* password typed on another, with no error anyone could diagnose.

    NFKC rather than NFC so visually identical compatibility forms (full-width Latin from
    a CJK keyboard, for one) also settle to the same bytes. Applied symmetrically: any
    change here must apply to hashing and verification together, or every existing
    password stops matching.
    """
    return unicodedata.normalize("NFKC", plain)


def hash_password(plain: str) -> str:
    return password_hasher.hash(normalise_password(plain))


def verify_password(plain: str, hashed: str | None) -> bool:
    """Constant-ish time check that also runs for unknown users.

    When ``hashed`` is None (user does not exist, or was invited and never set a password)
    the comparison still runs against a real Argon2 hash, so "no such account" and "wrong
    password" take the same time and cannot be told apart (PRD §7.4).
    """
    try:
        matched = password_hasher.verify(normalise_password(plain), hashed or DUMMY_PASSWORD_HASH)
    except Exception:
        # A malformed or truncated stored hash must read as "wrong password", not a 500.
        return False
    return matched and hashed is not None


def generate_otp(digits: int = 6) -> str:
    """Cryptographically random numeric OTP (PRD §7.3)."""
    upper = 10**digits
    return str(secrets.randbelow(upper)).zfill(digits)


def hash_otp(otp: str) -> str:
    """HMAC-SHA256 with OTP_PEPPER so a database leak alone cannot reveal codes."""
    pepper = settings.otp_pepper.get_secret_value().encode()
    return hmac.new(pepper, otp.encode(), hashlib.sha256).hexdigest()


def verify_otp(otp: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(otp), stored_hash)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_cookie(response: Response, name: str, value: str, max_age: int, path: str) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        path=path,
        domain=settings.cookie_domain,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def set_access_cookie(response: Response, token: str) -> None:
    _set_cookie(response, ACCESS_COOKIE, token, settings.access_token_ttl_minutes * 60, "/")


def set_refresh_cookie(response: Response, token: str, *, remembered: bool = False) -> None:
    days = (
        settings.refresh_token_ttl_days_remembered
        if remembered
        else settings.refresh_token_ttl_days
    )
    _set_cookie(response, REFRESH_COOKIE, token, days * 86400, REFRESH_COOKIE_PATH)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/", domain=settings.cookie_domain)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, domain=settings.cookie_domain)
