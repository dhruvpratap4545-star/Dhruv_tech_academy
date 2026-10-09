"""Request and response bodies for the auth endpoints (PRD §8).

Every input model forbids unknown fields. A typo'd field name then fails loudly instead of
being silently ignored — which is how "I set remember_me and it did nothing" bugs happen.
"""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import settings

# PRD §7.1: at least 8 characters, with a letter, a number and a special character.
#
# A character-class checklist is a weaker rule than length alone — it mostly teaches people
# to end a password with "1!" — but it is the rule the client asked for, it is the one most
# users already expect, and it is checkable live as somebody types, which is worth more in
# practice than a strength score nobody can act on. The common-password list below is what
# actually catches the worst choices.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


# The three character classes, defined in Unicode terms rather than ASCII.
#
# This platform is Indian. `[A-Za-z]` would tell somebody whose password is in Kannada,
# Devanagari or Tamil that it contains no letter, and `[^A-Za-z0-9]` would then count
# every one of those letters as a "special character" — so "ಕನ್ನಡ123" would pass a rule it
# should not and fail one it should. Python's `str` methods already know the whole of
# Unicode; a hand-written character class does not.
# Defined by Unicode *category*, so the browser and the server agree character for
# character. `str.isalpha()` and `str.isdigit()` look equivalent to `\p{L}` and `\p{N}`
# and are not: `isdigit()` rejects "½" while `\p{N}` accepts it, so a password could tick
# all four boxes in the live checklist and be refused by the API — which is the one thing
# a checklist must never do.
def _is_letter(ch: str) -> bool:
    return unicodedata.category(ch).startswith("L")


def _is_digit(ch: str) -> bool:
    # Nd only — decimal digits. Matches `\p{Nd}` in the browser exactly.
    return unicodedata.category(ch) == "Nd"


def _has_letter(value: str) -> bool:
    return any(_is_letter(ch) for ch in value)


def _has_digit(value: str) -> bool:
    return any(_is_digit(ch) for ch in value)


def _has_special(value: str) -> bool:
    """Anything that is neither a letter nor a decimal digit, spaces included. Enumerating
    an allowed-symbols set is how a password manager's output gets rejected for a character
    nobody thought of."""
    return any(not _is_letter(ch) and not _is_digit(ch) for ch in value)


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


def password_rule_failures(value: str) -> list[str]:
    """Which of the four rules this password breaks, in the order they are displayed.

    Returned as a list rather than raised one at a time so the message can name every
    problem at once. Being told "needs a number", fixing it, and then being told "needs a
    symbol" is the interaction that makes people give up and reuse an old password.
    """
    failures: list[str] = []
    if len(value) < MIN_PASSWORD_LENGTH:
        failures.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if not _has_letter(value):
        failures.append("one letter")
    if not _has_digit(value):
        failures.append("one number")
    if not _has_special(value):
        failures.append("one special character")
    return failures


def validate_password_strength(value: str) -> str:
    failures = password_rule_failures(value)
    if failures:
        raise ValueError("Password needs " + ", ".join(failures) + ".")
    # Compare with the decoration stripped. A character-class rule invites exactly one
    # evasion — take a breached password and bolt a symbol on the end — and "password123!"
    # is no stronger than "password123" against anyone running a list with mangling rules.
    stripped = "".join(ch for ch in value if _is_letter(ch) or _is_digit(ch)).lower()
    if value.lower() in _COMMON_PASSWORDS or stripped in _COMMON_PASSWORDS:
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
        "with at least one letter, one number and one special character."
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
