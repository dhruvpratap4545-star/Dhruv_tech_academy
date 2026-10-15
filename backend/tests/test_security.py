"""Password, OTP and token-secret handling (PRD §7.1, §7.3)."""

from __future__ import annotations

import re

import pytest

from app.core.security import (
    DUMMY_PASSWORD_HASH,
    generate_otp,
    generate_refresh_token,
    hash_otp,
    hash_password,
    hash_refresh_token,
    verify_otp,
    verify_password,
)


def test_hashing_a_password_never_reveals_it() -> None:
    hashed = hash_password("correct horse 9")
    assert "correct horse 9" not in hashed
    assert hashed.startswith("$argon2")


def test_the_same_password_hashes_differently_each_time() -> None:
    """Per-hash salt: identical passwords must not produce identical hashes, or a leak
    would reveal which accounts share one."""
    assert hash_password("same password 1") != hash_password("same password 1")


def test_a_correct_password_verifies() -> None:
    assert verify_password("correct horse 9", hash_password("correct horse 9"))


def test_a_wrong_password_does_not_verify() -> None:
    assert not verify_password("wrong password 1", hash_password("correct horse 9"))


def test_a_missing_hash_never_verifies() -> None:
    """An invited user has no password yet. Any attempt must fail, including an empty one."""
    assert not verify_password("anything 1", None)
    assert not verify_password("", None)


def test_a_corrupt_stored_hash_fails_closed() -> None:
    """A truncated hash must read as "wrong password", never as a 500 or a pass."""
    assert not verify_password("anything 1", "not-a-real-argon2-hash")


def test_the_dummy_hash_is_a_real_argon2_hash() -> None:
    """It exists to equalise timing for unknown emails, so it has to cost the same."""
    assert DUMMY_PASSWORD_HASH.startswith("$argon2")


# -------------------------------------------------------------------------------- OTP


def test_otp_is_the_configured_length_and_numeric() -> None:
    for _ in range(50):
        assert re.fullmatch(r"\d{6}", generate_otp(6))


def test_otp_generation_is_not_obviously_predictable() -> None:
    assert len({generate_otp(6) for _ in range(200)}) > 150


def test_otp_hash_hides_the_code_and_verifies() -> None:
    code = "123456"
    hashed = hash_otp(code)
    assert code not in hashed
    assert len(hashed) == 64  # SHA-256 hex
    assert verify_otp(code, hashed)


def test_a_wrong_otp_does_not_verify() -> None:
    assert not verify_otp("999999", hash_otp("123456"))


def test_otp_hashing_is_deterministic_for_lookup() -> None:
    """Unlike passwords, OTPs are HMACs so a stored digest can be compared directly."""
    assert hash_otp("123456") == hash_otp("123456")


@pytest.mark.parametrize("code", ["000000", "999999", "012345"])
def test_leading_zero_codes_survive_the_round_trip(code: str) -> None:
    """A code treated as an integer anywhere would silently drop its leading zeros."""
    assert verify_otp(code, hash_otp(code))


# ---------------------------------------------------------------------- refresh tokens


def test_refresh_tokens_are_long_and_unique() -> None:
    tokens = {generate_refresh_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(t) >= 32 for t in tokens)


def test_refresh_token_is_stored_only_as_a_digest() -> None:
    token = generate_refresh_token()
    digest = hash_refresh_token(token)
    assert token not in digest
    assert len(digest) == 64
    assert hash_refresh_token(token) == digest


# ------------------------------------------------------------------- PEM normalisation


def test_a_pem_with_escaped_newlines_is_restored() -> None:
    """Secret stores hand environment variables back as a single line, so a pasted key
    usually arrives with its line breaks escaped. Without this the key is malformed and
    the failure only shows up on the first login."""
    from app.core.config import _normalise_pem

    real = "-----BEGIN PRIVATE KEY-----\nMIGHAgEAMBMGByqGSM49\n-----END PRIVATE KEY-----"
    escaped = real.replace("\n", "\\n")

    assert escaped.count("\n") == 0, "the escaped form must be a single line"
    assert _normalise_pem(escaped) == real


def test_a_pem_with_real_newlines_passes_through() -> None:
    from app.core.config import _normalise_pem

    real = "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQ\n-----END PUBLIC KEY-----"
    assert _normalise_pem(real) == real


def test_surrounding_whitespace_is_trimmed() -> None:
    """A trailing newline from a copy-paste must not break PEM framing."""
    from app.core.config import _normalise_pem

    assert _normalise_pem("  -----BEGIN X-----\nabc\n-----END X-----  \n").startswith("-----")


def test_an_empty_key_normalises_to_empty() -> None:
    from app.core.config import _normalise_pem

    assert _normalise_pem(None) == ""
    assert _normalise_pem("") == ""


def test_a_pem_whose_newlines_became_spaces_still_loads(jwt_keys: tuple[str, str]) -> None:
    """A paste into a single-line field turns line breaks into spaces; the base64 is then
    unreadable ("Invalid padding") and the app refuses to start."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    from app.core.config import _normalise_pem

    private_pem, _ = jwt_keys
    mangled = private_pem.strip().replace("\n", " ")

    assert load_pem_private_key(_normalise_pem(mangled).encode(), password=None)


def test_quotes_around_a_pasted_pem_are_dropped(jwt_keys: tuple[str, str]) -> None:
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    from app.core.config import _normalise_pem

    _, public_pem = jwt_keys
    assert load_pem_public_key(_normalise_pem(f'"{public_pem.strip()}"').encode())


# ------------------------------------------------------------------- startup key check


def test_a_corrupt_key_names_the_variable_and_the_fault(jwt_keys: tuple[str, str]) -> None:
    import pytest
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    from app.main import _check_pem

    _, public_pem = jwt_keys
    truncated = public_pem.replace("-----END PUBLIC KEY-----", "").strip()[:-3]
    with pytest.raises(RuntimeError) as raised:
        _check_pem("JWT_PUBLIC_KEY", truncated, "PUBLIC KEY", load_pem_public_key)

    message = str(raised.value)
    assert "JWT_PUBLIC_KEY" in message
    assert "no '-----END PUBLIC KEY-----' line" in message
    assert truncated.splitlines()[1] not in message, "the key itself must never be logged"


def test_keys_swapped_between_variables_is_reported(jwt_keys: tuple[str, str]) -> None:
    import pytest
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    from app.main import _check_pem

    _, public_pem = jwt_keys
    with pytest.raises(RuntimeError, match="expected a 'PRIVATE KEY'"):
        _check_pem(
            "JWT_PRIVATE_KEY",
            public_pem,
            "PRIVATE KEY",
            lambda data: load_pem_private_key(data, password=None),
        )


def test_a_valid_key_passes_the_startup_check(jwt_keys: tuple[str, str]) -> None:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    from app.main import _check_pem

    private_pem, _ = jwt_keys
    _check_pem(
        "JWT_PRIVATE_KEY",
        private_pem,
        "PRIVATE KEY",
        lambda data: load_pem_private_key(data, password=None),
    )
