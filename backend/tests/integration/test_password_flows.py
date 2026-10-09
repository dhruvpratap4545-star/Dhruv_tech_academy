"""Forgot password, invitation setup and change password (PRD §4.2, §4.4, §7.3).

Covers acceptance criteria 3 and 4 from PRD §13.
"""

from __future__ import annotations

import re

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import PasswordOtp, RefreshToken
from app.modules.notifications.email import MemoryEmailProvider
from app.modules.users.models import User

SIGNUP = {
    "full_name": "Asha Rao",
    "email": "asha@example.com",
    "password": "goodpassword9!",
    "accept_terms": True,
}


def code_from(outbox: MemoryEmailProvider, address: str) -> str:
    message = outbox.last_to(address)
    assert message is not None, f"no email was sent to {address}"
    found = re.search(r"\b(\d{6})\b", message.text)
    assert found, f"no six-digit code in: {message.text}"
    return found.group(1)


async def _register(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/register", json=SIGNUP)).status_code == 201
    await client.post("/api/v1/auth/logout")


# ------------------------------------------------------------------- forgot password


async def test_forgot_password_sends_a_code(
    client: AsyncClient, outbox: MemoryEmailProvider
) -> None:
    await _register(client)
    response = await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    assert response.status_code == 200
    assert code_from(outbox, "asha@example.com")


async def test_an_unknown_email_gets_the_same_answer_and_no_email(
    client: AsyncClient, outbox: MemoryEmailProvider
) -> None:
    """PRD §7.3: identical response, so this is not an account-existence oracle."""
    await _register(client)
    known = await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    outbox.clear()
    unknown = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert outbox.outbox == []


async def test_the_full_reset_journey(
    client: AsyncClient, outbox: MemoryEmailProvider, db: AsyncSession
) -> None:
    await _register(client)
    await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    code = code_from(outbox, "asha@example.com")

    verified = await client.post(
        "/api/v1/auth/password/verify-otp", json={"email": "asha@example.com", "code": code}
    )
    assert verified.status_code == 200
    token = verified.json()["reset_token"]

    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"reset_token": token, "new_password": "brandnewpass8!"},
    )
    assert reset.status_code == 200

    # The new password works and the old one does not.
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "asha@example.com", "password": "brandnewpass8!"},
        )
    ).status_code == 200
    await client.post("/api/v1/auth/logout")
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "asha@example.com", "password": "goodpassword9!"},
        )
    ).status_code == 401


async def test_a_reset_logs_every_device_out_and_warns_the_user(
    client: AsyncClient, outbox: MemoryEmailProvider, db: AsyncSession
) -> None:
    """PRD §13 criterion 3: other devices are logged out and a security email is sent."""
    await _register(client)
    await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    code = code_from(outbox, "asha@example.com")
    token = (
        await client.post(
            "/api/v1/auth/password/verify-otp", json={"email": "asha@example.com", "code": code}
        )
    ).json()["reset_token"]
    await client.post(
        "/api/v1/auth/password/reset",
        json={"reset_token": token, "new_password": "brandnewpass8!"},
    )

    live = (
        (await db.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    assert live == []

    notice = outbox.last_to("asha@example.com")
    assert notice is not None and "changed" in notice.subject.lower()


async def test_a_wrong_code_is_rejected(client: AsyncClient, outbox: MemoryEmailProvider) -> None:
    await _register(client)
    await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    response = await client.post(
        "/api/v1/auth/password/verify-otp", json={"email": "asha@example.com", "code": "000000"}
    )
    assert response.status_code == 422


async def test_a_code_cannot_be_used_twice(
    client: AsyncClient, outbox: MemoryEmailProvider
) -> None:
    """PRD §7.3 single use. The reset token is bound to the OTP row, so replay fails."""
    await _register(client)
    await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    code = code_from(outbox, "asha@example.com")
    token = (
        await client.post(
            "/api/v1/auth/password/verify-otp", json={"email": "asha@example.com", "code": code}
        )
    ).json()["reset_token"]

    first = await client.post(
        "/api/v1/auth/password/reset", json={"reset_token": token, "new_password": "firstpass11!"}
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/auth/password/reset", json={"reset_token": token, "new_password": "secondpass22!"}
    )
    assert second.status_code == 401


async def test_a_sixth_attempt_is_blocked(client: AsyncClient, outbox: MemoryEmailProvider) -> None:
    """PRD §13 criterion 3: max five attempts per code."""
    await _register(client)
    await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    code = code_from(outbox, "asha@example.com")

    for _ in range(5):
        await client.post(
            "/api/v1/auth/password/verify-otp",
            json={"email": "asha@example.com", "code": "000000"},
        )

    blocked = await client.post(
        "/api/v1/auth/password/verify-otp", json={"email": "asha@example.com", "code": code}
    )
    assert blocked.status_code == 429, "the correct code must be refused once attempts run out"


async def test_an_expired_code_is_rejected(
    client: AsyncClient, outbox: MemoryEmailProvider, db: AsyncSession
) -> None:
    from datetime import UTC, datetime, timedelta

    await _register(client)
    await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    code = code_from(outbox, "asha@example.com")

    otp = await db.scalar(select(PasswordOtp).where(PasswordOtp.purpose == "reset"))
    assert otp is not None
    otp.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    response = await client.post(
        "/api/v1/auth/password/verify-otp", json={"email": "asha@example.com", "code": code}
    )
    assert response.status_code == 422


async def test_requesting_a_second_code_too_soon_is_refused(
    client: AsyncClient, outbox: MemoryEmailProvider
) -> None:
    """PRD §7.3: a 60-second resend cooldown, enforced per account in the database."""
    await _register(client)
    await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    second = await client.post("/api/v1/auth/password/forgot", json={"email": "asha@example.com"})
    assert second.status_code == 429


# ------------------------------------------------------------------ change password


async def test_changing_a_password_requires_the_current_one(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    response = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "wrongpassword9", "new_password": "brandnewpass8!"},
    )
    assert response.status_code == 422


async def test_the_new_password_must_differ(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    response = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "goodpassword9!", "new_password": "goodpassword9!"},
    )
    assert response.status_code == 422


async def test_changing_a_password_works_and_ends_sessions(
    client: AsyncClient, db: AsyncSession
) -> None:
    await client.post("/api/v1/auth/register", json=SIGNUP)
    response = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "goodpassword9!", "new_password": "brandnewpass8!"},
    )
    assert response.status_code == 200
    assert (await client.get("/api/v1/me")).status_code == 401

    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "asha@example.com", "password": "brandnewpass8!"},
        )
    ).status_code == 200


async def test_an_anonymous_caller_cannot_change_a_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "goodpassword9!", "new_password": "brandnewpass8!"},
    )
    assert response.status_code == 401


# ------------------------------------------------------------------ invitation setup


async def test_an_invited_user_sets_a_password_and_becomes_active(
    client: AsyncClient, outbox: MemoryEmailProvider, db: AsyncSession, make_user, institute
) -> None:
    """PRD §13 criterion 4: invited to active via the setup code."""
    inst, branch = await institute("ABC College", "ABC", with_branch="MCA")
    admin = await make_user("institute_admin", institute_id=inst.id)

    await client.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": "testpassword9!"}
    )
    invited = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Ravi Kumar",
            "email": "ravi@example.com",
            "role_key": "faculty",
            "institute_id": str(inst.id),
            "branch_id": str(branch.id),
        },
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["user"]["status"] == "invited"

    code = code_from(outbox, "ravi@example.com")
    await client.post("/api/v1/auth/logout")

    setup = await client.post(
        "/api/v1/auth/password/setup",
        json={"email": "ravi@example.com", "code": code, "new_password": "ravispassword7!"},
    )
    assert setup.status_code == 200

    user = await db.scalar(select(User).where(User.email == "ravi@example.com"))
    assert user is not None and user.status == "active"

    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "ravi@example.com", "password": "ravispassword7!"},
        )
    ).status_code == 200


async def test_an_invited_user_cannot_log_in_before_setting_a_password(
    client: AsyncClient, make_user
) -> None:
    invited = await make_user("student", status="invited")
    response = await client.post(
        "/api/v1/auth/login", json={"email": invited.email, "password": "anything123"}
    )
    assert response.status_code in (401, 403)


# ------------------------------------------------- bootstrapping the first Super Admin


async def test_the_seeded_super_admin_can_get_into_their_account(
    client: AsyncClient, outbox: MemoryEmailProvider, db: AsyncSession, seeded
) -> None:
    """The very first administrator has to be able to log in, or nothing can be set up.

    The seed creates them `invited` with no password — deliberately, because a generated
    password would end up in a deploy log. There is no one above them to send an invitation,
    so forgot-password is their only way in, and it has to leave them able to log in.
    """
    from sqlalchemy import select

    from app.modules.rbac.catalog import SUPER_ADMIN
    from app.modules.rbac.models import Role, UserRoleAssignment

    role = await db.scalar(select(Role).where(Role.key == SUPER_ADMIN))
    assert role is not None
    owner = User(email="owner@example.com", full_name="Super Admin", status="invited")
    db.add(owner)
    await db.flush()
    db.add(UserRoleAssignment(user_id=owner.id, role_id=role.id))
    await db.commit()

    # Cannot log in yet: no password.
    blocked = await client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "anything123"}
    )
    assert blocked.status_code in (401, 403)

    # Forgot password is the way in.
    await client.post("/api/v1/auth/password/forgot", json={"email": "owner@example.com"})
    code = code_from(outbox, "owner@example.com")
    token = (
        await client.post(
            "/api/v1/auth/password/verify-otp",
            json={"email": "owner@example.com", "code": code},
        )
    ).json()["reset_token"]
    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"reset_token": token, "new_password": "ownerpassword9!"},
    )
    assert reset.status_code == 200

    # And now they can actually get in — this is the step that used to dead-end.
    login = await client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "ownerpassword9!"}
    )
    assert login.status_code == 200, login.text

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert "institute:create" in me.json()["permissions"]


async def test_a_completed_reset_activates_an_invited_account(
    client: AsyncClient, outbox: MemoryEmailProvider, db: AsyncSession, make_user
) -> None:
    """`invited` means "no password yet", so it must not survive setting one."""
    from sqlalchemy import select

    invited = await make_user("student", status="invited", email="newbie@example.com")
    assert invited.status == "invited"

    await client.post("/api/v1/auth/password/forgot", json={"email": "newbie@example.com"})
    code = code_from(outbox, "newbie@example.com")
    token = (
        await client.post(
            "/api/v1/auth/password/verify-otp",
            json={"email": "newbie@example.com", "code": code},
        )
    ).json()["reset_token"]
    await client.post(
        "/api/v1/auth/password/reset",
        json={"reset_token": token, "new_password": "newbiepass11!"},
    )

    refreshed = await db.scalar(select(User).where(User.email == "newbie@example.com"))
    assert refreshed is not None
    assert refreshed.status == "active"
