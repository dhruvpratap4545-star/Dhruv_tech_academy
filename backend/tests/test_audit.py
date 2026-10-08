"""The audit writer must never persist a secret (PRD §7.5)."""

from __future__ import annotations

from app.modules.audit.service import _scrub


def test_ordinary_metadata_passes_through() -> None:
    assert _scrub({"role_key": "faculty", "count": 3}) == {"role_key": "faculty", "count": 3}


def test_empty_metadata_becomes_null() -> None:
    assert _scrub(None) is None
    assert _scrub({}) is None


def test_secrets_are_stripped() -> None:
    cleaned = _scrub({"password": "hunter2", "otp": "123456", "role_key": "student"})
    assert cleaned == {"role_key": "student"}


def test_stripping_is_case_insensitive() -> None:
    assert _scrub({"Password": "x", "OTP": "1"}) is None


def test_every_known_secret_key_is_covered() -> None:
    secrets = {
        "password": "x",
        "new_password": "x",
        "current_password": "x",
        "otp": "1",
        "code": "1",
        "token": "t",
        "access_token": "t",
        "refresh_token": "t",
        "password_hash": "h",
        "otp_hash": "h",
        "authorization": "Bearer x",
        "cookie": "a=b",
    }
    assert _scrub(secrets) is None
