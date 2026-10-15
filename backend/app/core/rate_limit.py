"""Network-level rate limiting (PRD §7.4).

This is the *outer* layer only — it throttles by IP and stops crude flooding. The limits
that actually protect an account (5 failed logins, 3 OTPs per hour, 5 attempts per code)
live in the database, in ``auth.service``, because an attacker rotating IP addresses walks
straight through an IP limiter.

Storage is in-process memory, which is correct for one instance and wrong for two: each
instance would enforce its own allowance. Moving to Redis is the documented prerequisite for
scaling out (PRD §10.2), and only this file changes when that happens.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def rate_limit_key(request: Request) -> str:
    """Prefer the authenticated user, fall back to the IP.

    Keying a logged-in caller by user id means one office behind a single NAT address does
    not exhaust a shared allowance, while anonymous endpoints still get IP protection.
    """
    user_id = getattr(request.state, "rate_limit_user_id", None)
    return f"user:{user_id}" if user_id else f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[settings.rate_limit_default] if settings.rate_limits_enabled else [],
    enabled=settings.rate_limits_enabled,
    headers_enabled=True,
    strategy="fixed-window",
)
