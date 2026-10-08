"""End-to-end authentication (PRD §4.1, §4.3, §7.2, §7.4).

Covers acceptance criteria 1, 2 and 9 from PRD §13.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ACCESS_COOKIE, REFRESH_COOKIE
from app.modules.audit.models import AuditLog
from app.modules.auth.models import RefreshToken
from app.modules.users.models import User

SIGNUP = {
    "full_name": "Asha Rao",
    "email": "asha@example.com",
    "password": "goodpassword9",
    "accept_terms": True,
}


async def test_a_direct_learner_can_sign_up_and_is_logged_in(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/register", json=SIGNUP)
    assert response.status_code == 201, response.text
    assert ACCESS_COOKIE in response.cookies
    assert REFRESH_COOKIE in response.cookies


async def test_tokens_never_appear_in_the_response_body(client: AsyncClient) -> None:
    """PRD §7.2: cookies only, so XSS cannot read them."""
    response = await client.post("/api/v1/auth/register", json=SIGNUP)
    body = response.text.lower()
    assert "token" not in body


async def test_signup_records_consent(client: AsyncClient, db: AsyncSession) -> None:
    """DPDP §11: the consent and its version must be on the record."""
    await client.post("/api/v1/auth/register", json=SIGNUP)
    user = await db.scalar(select(User).where(User.email == "asha@example.com"))
    assert user is not None
    assert user.consent_accepted_at is not None
    assert user.consent_version


async def test_a_duplicate_signup_does_not_confirm_the_email_exists(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    second = await client.post("/api/v1/auth/register", json=SIGNUP)
    assert second.status_code == 409
    assert "already" not in second.json()["error"]["message"].lower()


async def test_signup_then_login_then_me(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    await client.post("/api/v1/auth/logout")

    login = await client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": "goodpassword9"}
    )
    assert login.status_code == 200

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == "asha@example.com"
    assert "student" in {r["role_key"] for r in me.json()["roles"]}


async def test_login_is_case_insensitive_on_email(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    response = await client.post(
        "/api/v1/auth/login", json={"email": "ASHA@Example.com", "password": "goodpassword9"}
    )
    assert response.status_code == 200


async def test_a_wrong_password_and_an_unknown_email_look_identical(client: AsyncClient) -> None:
    """PRD §13 criterion 2: the message must never reveal whether the email exists."""
    await client.post("/api/v1/auth/register", json=SIGNUP)

    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": "wrongpassword9"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrongpassword9"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_five_failures_lock_the_account_for_fifteen_minutes(
    client: AsyncClient, db: AsyncSession
) -> None:
    """PRD §13 criterion 2."""
    await client.post("/api/v1/auth/register", json=SIGNUP)

    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/login", json={"email": "asha@example.com", "password": "wrongpassword9"}
        )
        assert response.status_code == 401

    # The sixth attempt is refused even with the correct password.
    locked = await client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": "goodpassword9"}
    )
    assert locked.status_code == 429

    user = await db.scalar(select(User).where(User.email == "asha@example.com"))
    assert user is not None and user.locked_until is not None


async def test_the_lockout_is_recorded_in_the_audit_log(
    client: AsyncClient, db: AsyncSession
) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login", json={"email": "asha@example.com", "password": "wrongpassword9"}
        )

    actions = set((await db.execute(select(AuditLog.action))).scalars())
    assert "login_failure" in actions
    assert "account_locked" in actions


async def test_a_successful_login_resets_the_failure_counter(
    client: AsyncClient, db: AsyncSession
) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    for _ in range(3):
        await client.post(
            "/api/v1/auth/login", json={"email": "asha@example.com", "password": "wrongpassword9"}
        )
    await client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": "goodpassword9"}
    )

    user = await db.scalar(select(User).where(User.email == "asha@example.com"))
    assert user is not None and user.failed_login_count == 0


async def test_me_requires_a_session(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/me")).status_code == 401


# ------------------------------------------------------------------ refresh rotation


async def test_refresh_issues_a_new_token_and_keeps_the_session(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    original = client.cookies[REFRESH_COOKIE]

    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert client.cookies[REFRESH_COOKIE] != original
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_replaying_a_rotated_token_kills_the_whole_family(
    client: AsyncClient, db: AsyncSession
) -> None:
    """PRD §7.2 reuse detection: a replayed token means the cookie leaked."""
    await client.post("/api/v1/auth/register", json=SIGNUP)
    stolen = client.cookies[REFRESH_COOKIE]

    await client.post("/api/v1/auth/refresh")  # rotates; `stolen` is now revoked
    assert client.cookies[REFRESH_COOKIE] != stolen

    # Replace the jar entirely: setting a same-named cookie can otherwise leave the fresh
    # one in place and the "replay" would silently use a valid token.
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, stolen)
    replay = await client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401

    live = (
        (await db.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    assert live == [], "reuse detection must revoke every token in the family"

    actions = set((await db.execute(select(AuditLog.action))).scalars())
    assert "token_reuse_detected" in actions


async def test_refresh_without_a_cookie_is_rejected(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


# -------------------------------------------------------------------------- logout


async def test_logout_clears_the_session(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_logout_is_idempotent(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    await client.post("/api/v1/auth/logout")
    assert (await client.post("/api/v1/auth/logout")).status_code == 200


async def test_logout_all_revokes_every_session(client: AsyncClient, db: AsyncSession) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    response = await client.post("/api/v1/auth/logout-all")
    assert response.status_code == 200

    live = (
        (await db.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    assert live == []


# ------------------------------------------------------------------------ suspension


async def test_a_suspended_user_is_blocked_on_the_next_request(
    client: AsyncClient, db: AsyncSession
) -> None:
    """PRD §13 criterion 9. Status is checked per request, not trusted from the token."""
    await client.post("/api/v1/auth/register", json=SIGNUP)
    assert (await client.get("/api/v1/me")).status_code == 200

    user = await db.scalar(select(User).where(User.email == "asha@example.com"))
    assert user is not None
    user.status = "suspended"
    await db.commit()

    assert (await client.get("/api/v1/me")).status_code == 403


async def test_a_suspended_user_cannot_log_in(client: AsyncClient, db: AsyncSession) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    user = await db.scalar(select(User).where(User.email == "asha@example.com"))
    assert user is not None
    user.status = "suspended"
    await db.commit()

    response = await client.post(
        "/api/v1/auth/login", json={"email": "asha@example.com", "password": "goodpassword9"}
    )
    assert response.status_code == 403


async def test_a_suspended_user_cannot_refresh(client: AsyncClient, db: AsyncSession) -> None:
    """Otherwise a suspension could be outlived by refreshing the session."""
    await client.post("/api/v1/auth/register", json=SIGNUP)
    user = await db.scalar(select(User).where(User.email == "asha@example.com"))
    assert user is not None
    user.status = "suspended"
    await db.commit()

    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
