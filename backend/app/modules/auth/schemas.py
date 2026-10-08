"""Request and response bodies for the auth endpoints (PRD §8).

Every input model forbids unknown fields. A typo'd field name then fails loudly instead of
being silently ignored — which is how "I set remember_me and it did nothing" bugs happen.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import settings

# Deliberately permissive on characters and strict on composition (PRD §7.1). Length does
# more for strength than a character-class checklist, which mostly teaches people to end
# passwords with "1!".
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# Passwords seen constantly in breach corpora. A full breach-list check belongs in a later
# milestone; this catches the worst offenders at zero cost.
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty123",
        "abc12345",
        "iloveyou",
        "admin123",
        "welcome1",
        "letmein1",
        "dhruv123",
        "academy123",
    }
)

Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]
OtpCode = Annotated[str, Field(min_length=4, max_length=10)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def validate_password_strength(value: str) -> str:
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Password must contain at least one letter and one number.")
    if value.lower() in _COMMON_PASSWORDS:
        raise ValueError("That password is too common. Please choose a different one.")
    return value


class RegisterRequest(StrictModel):
    """Direct Learner sign-up (PRD §4.1). Consent is mandatory and recorded."""

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: Password
    accept_terms: Literal[True] = Field(
        description="Must be true. Confirms the privacy policy, terms and 18+ declaration."
    )

    _check_password = field_validator("password")(validate_password_strength)


class LoginRequest(StrictModel):
    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    remember_me: bool = False


class ForgotPasswordRequest(StrictModel):
    email: EmailStr


class VerifyOtpRequest(StrictModel):
    email: EmailStr
    code: OtpCode


class ResetPasswordRequest(StrictModel):
    """``reset_token`` comes from verify-otp and is short-lived (PRD §8)."""

    reset_token: str = Field(max_length=512)
    new_password: Password

    _check_password = field_validator("new_password")(validate_password_strength)


class SetupPasswordRequest(StrictModel):
    """Invited user's first password: OTP and password in one step (PRD §4.2)."""

    email: EmailStr
    code: OtpCode
    new_password: Password

    _check_password = field_validator("new_password")(validate_password_strength)


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    new_password: Password

    _check_password = field_validator("new_password")(validate_password_strength)


class MessageResponse(BaseModel):
    message: str


class VerifyOtpResponse(BaseModel):
    reset_token: str
    expires_in_seconds: int


class LoginResponse(BaseModel):
    """Tokens are set as httpOnly cookies and never appear in the body (PRD §7.2)."""

    user_id: str
    full_name: str
    requires_institute_choice: bool = Field(
        default=False,
        description="True when the user holds roles in more than one institute.",
    )


GENERIC_OTP_SENT = "If this email is registered, a code has been sent. Please check your inbox."
GENERIC_LOGIN_FAILED = "Email or password is incorrect."


def password_policy_text() -> str:
    return (
        f"{MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters, "
        "with at least one letter and one number."
    )


__all__ = [
    "GENERIC_LOGIN_FAILED",
    "GENERIC_OTP_SENT",
    "ChangePasswordRequest",
    "ForgotPasswordRequest",
    "LoginRequest",
    "LoginResponse",
    "MessageResponse",
    "RegisterRequest",
    "ResetPasswordRequest",
    "SetupPasswordRequest",
    "VerifyOtpRequest",
    "VerifyOtpResponse",
    "password_policy_text",
    "settings",
]
