"""Input validation (PRD §7.1, §7.5, §11)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.auth import schemas as auth_schemas
from app.modules.org import schemas as org_schemas
from app.modules.users import schemas as user_schemas


def _register(**overrides):
    payload = {
        "full_name": "Asha Rao",
        "email": "asha@example.com",
        "password": "goodpassword9",
        "accept_terms": True,
    }
    payload.update(overrides)
    return auth_schemas.RegisterRequest(**payload)


def test_a_valid_signup_is_accepted() -> None:
    assert _register().email == "asha@example.com"


def test_consent_is_mandatory() -> None:
    """DPDP §11: sign-up without consent must be impossible, not merely discouraged."""
    with pytest.raises(ValidationError):
        _register(accept_terms=False)


def test_consent_cannot_be_omitted() -> None:
    with pytest.raises(ValidationError):
        auth_schemas.RegisterRequest(
            full_name="Asha Rao", email="asha@example.com", password="goodpassword9"
        )


@pytest.mark.parametrize("bad", ["short1", "a" * 129 + "1"])
def test_password_length_bounds_are_enforced(bad: str) -> None:
    with pytest.raises(ValidationError):
        _register(password=bad)


@pytest.mark.parametrize("bad", ["alllettersonly", "123456789012"])
def test_password_needs_a_letter_and_a_number(bad: str) -> None:
    with pytest.raises(ValidationError):
        _register(password=bad)


@pytest.mark.parametrize("bad", ["password123", "Password123", "admin123", "welcome1"])
def test_common_passwords_are_refused(bad: str) -> None:
    with pytest.raises(ValidationError):
        _register(password=bad)


def test_a_malformed_email_is_refused() -> None:
    with pytest.raises(ValidationError):
        _register(email="not-an-email")


def test_unknown_fields_are_refused() -> None:
    """extra="forbid" turns a typo'd field into an error instead of a silent no-op."""
    with pytest.raises(ValidationError):
        _register(is_admin=True)


def test_whitespace_is_stripped() -> None:
    assert _register(full_name="  Asha Rao  ").full_name == "Asha Rao"


def test_login_does_not_apply_the_password_policy() -> None:
    """Existing passwords predate any policy change; login must still accept them."""
    assert auth_schemas.LoginRequest(email="a@b.com", password="old").password == "old"


# ------------------------------------------------------------------------------ codes


@pytest.mark.parametrize(
    "raw,expected", [("mca", "MCA"), (" bca ", "BCA"), ("1st year", "1ST-YEAR")]
)
def test_codes_are_normalised(raw: str, expected: str) -> None:
    """`mca`, `MCA` and `Mca` must not become three different branches."""
    assert org_schemas.normalise_code(raw) == expected


@pytest.mark.parametrize("bad", ["a", "-abc", "has.dot", "has/slash", "x" * 41])
def test_bad_codes_are_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="Code must be"):
        org_schemas.normalise_code(bad)


def test_session_end_date_cannot_precede_the_start() -> None:
    with pytest.raises(ValidationError):
        org_schemas.AcademicSessionCreate(
            name="2026-27", start_date="2027-06-30", end_date="2026-07-01"
        )


# ------------------------------------------------------------------------------ users


def test_invite_requires_a_role() -> None:
    """A user with no role can log in and see nothing, which reads as a broken account."""
    with pytest.raises(ValidationError):
        user_schemas.InviteUserRequest(full_name="Ravi Kumar", email="ravi@example.com")


def test_status_updates_are_limited_to_active_and_suspended() -> None:
    assert user_schemas.UpdateStatusRequest(status="suspended").status == "suspended"
    with pytest.raises(ValidationError):
        user_schemas.UpdateStatusRequest(status="deleted")


def test_theme_is_restricted_to_the_three_supported_values() -> None:
    assert user_schemas.UpdatePreferencesRequest(theme="dark").theme == "dark"
    with pytest.raises(ValidationError):
        user_schemas.UpdatePreferencesRequest(theme="neon")


def test_user_output_never_exposes_credential_fields() -> None:
    """A regression here would leak password hashes and lockout state to every caller."""
    fields = set(user_schemas.UserOut.model_fields)
    assert not fields & {"password_hash", "failed_login_count", "locked_until"}
