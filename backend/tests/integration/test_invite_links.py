"""Shareable setup links on invitations.

While email is not configured — and whenever it does not arrive — the inviter can share
the one-time setup link by hand. The code travels in the URL *fragment*, which browsers
never send to a server, so it cannot land in an access log.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from httpx import AsyncClient

from app.modules.audit.models import AuditLog
from app.modules.notifications import email as email_module
from app.modules.notifications.email import ConsoleEmailProvider


async def _login(client: AsyncClient, user) -> None:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text


def _code(link: str) -> str:
    parts = urlsplit(link)
    assert parts.path == "/set-password"
    assert parse_qs(parts.query)["email"] == ["ravi@example.com"]
    assert "code" not in parse_qs(parts.query), "the code must never be a query parameter"
    return parse_qs(parts.fragment)["code"][0]


async def _invite(client: AsyncClient, inst, branch):
    return await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Ravi Kumar",
            "email": "ravi@example.com",
            "role_key": "faculty",
            "institute_id": str(inst.id),
            "branch_id": str(branch.id),
        },
    )


async def test_the_setup_link_completes_setup(client: AsyncClient, db, make_user, institute):
    inst, branch = await institute("ABC College", "ABC", with_branch="MCA")
    await _login(client, await make_user("institute_admin", institute_id=inst.id))

    invited = await _invite(client, inst, branch)

    assert invited.status_code == 201, invited.text
    body = invited.json()
    assert body["invitation_sent"] is True  # the test provider counts as delivering
    code = _code(body["setup_link"])

    client.cookies.clear()
    setup = await client.post(
        "/api/v1/auth/password/setup",
        json={"email": "ravi@example.com", "code": code, "new_password": "Bramble#Lantern2"},
    )
    assert setup.status_code == 200, setup.text
    # The link is a credential: it never reaches the permanent audit table.
    for row in await db.find(AuditLog, {}):
        assert code not in str(row.extra or {})


async def test_without_email_the_inviter_is_told_to_share_the_link(
    client: AsyncClient, make_user, institute
):
    inst, branch = await institute("ABC College", "ABC", with_branch="MCA")
    await _login(client, await make_user("institute_admin", institute_id=inst.id))
    email_module.set_provider(ConsoleEmailProvider())

    invited = await _invite(client, inst, branch)

    assert invited.json()["invitation_sent"] is False
    assert invited.json()["setup_link"]


async def test_resending_retires_the_old_link(client: AsyncClient, make_user, institute):
    from datetime import timedelta

    from app.core.db import utcnow
    from app.modules.auth.models import PasswordOtp

    inst, branch = await institute("ABC College", "ABC", with_branch="MCA")
    await _login(client, await make_user("institute_admin", institute_id=inst.id))
    first = _code((await _invite(client, inst, branch)).json()["setup_link"])
    user_id = (await client.get("/api/v1/users?search=ravi")).json()["items"][0]["id"]
    # A resend inside the one-minute cooldown is refused; age the first code past it.
    await PasswordOtp.get_pymongo_collection().update_many(
        {}, {"$set": {"created_at": utcnow() - timedelta(minutes=2)}}
    )

    resent = await client.post(f"/api/v1/users/{user_id}/resend-invite")
    second = _code(resent.json()["setup_link"])

    client.cookies.clear()
    old = await client.post(
        "/api/v1/auth/password/setup",
        json={"email": "ravi@example.com", "code": first, "new_password": "Bramble#Lantern2"},
    )
    new = await client.post(
        "/api/v1/auth/password/setup",
        json={"email": "ravi@example.com", "code": second, "new_password": "Bramble#Lantern2"},
    )
    assert first != second
    assert old.status_code != 200
    assert new.status_code == 200, new.text


async def test_creating_an_institute_returns_the_admins_link(client: AsyncClient, make_user):
    await _login(client, await make_user("super_admin"))

    created = await client.post(
        "/api/v1/institutes/with-admin",
        json={
            "institute": {"name": "Sunrise School", "code": "SUN", "type": "school"},
            "admin_full_name": "Meera Iyer",
            "admin_email": "meera@example.com",
        },
    )

    assert created.status_code == 201, created.text
    link = created.json()["setup_link"]
    assert "/set-password?email=meera%40example.com#code=" in link


async def test_the_user_list_never_exposes_a_link(client: AsyncClient, make_user, institute):
    """Only the response to the person who invited carries it."""
    inst, branch = await institute("ABC College", "ABC", with_branch="MCA")
    await _login(client, await make_user("institute_admin", institute_id=inst.id))
    await _invite(client, inst, branch)

    listing = await client.get("/api/v1/users")

    assert "set-password" not in listing.text
    assert "#code=" not in listing.text
