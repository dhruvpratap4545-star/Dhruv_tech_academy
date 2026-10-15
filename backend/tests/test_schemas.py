"""Input validation (PRD §7.1, §7.5, §11)."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.modules.auth import schemas as auth_schemas
from app.modules.org import schemas as org_schemas
from app.modules.users import schemas as user_schemas


def _register(**overrides):
    payload = {
        "full_name": "Asha Rao",
        "email": "asha@example.com",
        "password": "Kaveri#Delta88",
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
            full_name="Asha Rao", email="asha@example.com", password="Kaveri#Delta88"
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


def test_invitation_and_reset_emails_carry_a_link() -> None:
    """A six-digit code with nowhere to type it is not a usable instruction. The recipient
    of an invitation has never seen the product and does not know the address."""
    from app.modules.notifications import templates

    setup = templates.password_setup("learner@example.com", "Learner", "123456")
    reset = templates.password_reset("learner@example.com", "Learner", "654321")

    for message, path in ((setup, "/set-password"), (reset, "/forgot-password")):
        assert path in message.html, "the HTML body needs the link"
        assert path in message.text, "so does the plain text, for clients that strip HTML"
        # Pre-filled, so nobody retypes the address the mail was just sent to.
        assert "email=learner%40example.com" in message.text


def test_a_one_time_code_never_travels_in_a_url() -> None:
    """The code is what authorises the change. Put it in a URL and it is copied into
    browser history, proxy logs and every link-rewriting gateway in between."""
    import re

    from app.modules.notifications import templates

    for message, code in (
        (templates.password_setup("learner@example.com", "Learner", "123456"), "123456"),
        (templates.password_reset("learner@example.com", "Learner", "654321"), "654321"),
    ):
        for part in (message.html, message.text):
            for url in re.findall(r"https?://[^\s\"'<>]+", part):
                assert code not in url, f"the code leaked into a link: {url}"


# ------------------------------------------------------- password policy (PRD §7.1)


@pytest.mark.parametrize(
    ("value", "missing"),
    [
        ("Ab1!", "at least 8 characters"),
        ("12345678!", "one letter"),
        ("abcdefgh!", "one number"),
        ("abcdefgh1", "one special character"),
    ],
)
def test_each_password_rule_is_enforced(value: str, missing: str) -> None:
    from app.modules.auth.schemas import validate_password_strength

    with pytest.raises(ValueError, match=re.escape(missing)):
        validate_password_strength(value)


def test_a_password_breaking_several_rules_is_told_all_of_them() -> None:
    """Being told one problem, fixing it, and being told the next is the interaction that
    ends in somebody reusing an old password."""
    from app.modules.auth.schemas import password_rule_failures

    assert password_rule_failures("abc") == [
        "at least 8 characters",
        "one number",
        "one special character",
    ]


@pytest.mark.parametrize(
    "value",
    ["Correct-Horse9", "Tr0ub4dor&3", "my dog is 7 years", "ಕನ್ನಡ123!"],
)
def test_reasonable_passwords_are_accepted(value: str) -> None:
    """Including a space as the special character, and a non-Latin script — rejecting
    either would exclude real people for no security gain."""
    from app.modules.auth.schemas import validate_password_strength

    assert validate_password_strength(value) == value


@pytest.mark.parametrize("value", ["password123!", "Password123!", "admin123#", "welcome1!"])
def test_a_common_password_is_refused_even_with_a_symbol_bolted_on(value: str) -> None:
    """A character-class rule invites exactly one evasion. "password123!" is no stronger
    than "password123" against anyone running a wordlist with mangling rules."""
    from app.modules.auth.schemas import validate_password_strength

    with pytest.raises(ValueError, match="too common"):
        validate_password_strength(value)


def test_the_browser_and_the_server_agree_on_what_a_digit_is() -> None:
    r"""A checklist that ticks every box while the API refuses the password is worse than
    no checklist. "½" is \p{N} but not a decimal digit; both sides now use \p{Nd}."""
    from app.modules.auth.schemas import validate_password_strength

    with pytest.raises(ValueError, match="one number"):
        validate_password_strength("Abcdefg½!")

    assert validate_password_strength("Tamarind7#") == "Tamarind7#"


def test_the_same_password_verifies_however_it_was_typed() -> None:
    """Devanagari, Kannada and Tamil compose differently on different keyboards — iOS
    composes, several Linux input methods decompose. Argon2 sees bytes, so without
    normalisation an account set up on one device refuses the correct password on another.
    """
    import unicodedata

    from app.core.security import hash_password, verify_password

    composed = unicodedata.normalize("NFC", "Café123!")
    decomposed = unicodedata.normalize("NFD", "Café123!")
    assert composed.encode() != decomposed.encode(), "the test needs two byte sequences"

    assert verify_password(decomposed, hash_password(composed))
    assert verify_password(composed, hash_password(decomposed))


def test_a_wrong_password_is_still_wrong_after_normalisation() -> None:
    from app.core.security import hash_password, verify_password

    assert not verify_password("Different9!", hash_password("Café123!"))
