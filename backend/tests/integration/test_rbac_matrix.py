"""The PRD §5.3 permission matrix and the §3.1 no-escalation rule, end to end.

Covers acceptance criteria 5, 6, 6a, 7 and 8 from PRD §13. Every test here answers one
question: can this role, in this scope, do this thing — and crucially, can it *not* do the
things it must not.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def world(institute, make_user):
    """Two institutes, two branches in the first, and a user for every role.

    ABC College ──┬── MCA branch   (branch admin A1, faculty)
                  └── BCA branch   (branch admin A2)
    XYZ College ───── other branch (institute admin B)
    """

    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")
    xyz, xyz_branch = await institute("XYZ College", "XYZ", with_branch="CSE")

    return {
        "abc": abc,
        "mca": mca,
        "xyz": xyz,
        "xyz_branch": xyz_branch,
        "super_admin": await make_user("super_admin"),
        "platform_admin": await make_user("platform_admin"),
        "abc_admin": await make_user("institute_admin", institute_id=abc.id),
        "abc_branch_admin": await make_user("branch_admin", institute_id=abc.id, branch_id=mca.id),
        "abc_faculty": await make_user("faculty", institute_id=abc.id, branch_id=mca.id),
        "abc_student": await make_user("student", institute_id=abc.id),
        "xyz_admin": await make_user("institute_admin", institute_id=xyz.id),
    }


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "testpassword9"}
    )
    assert response.status_code == 200, response.text
    return client


# ------------------------------------------------------------------ institute access


async def test_super_admin_can_create_an_institute(client: AsyncClient, world) -> None:
    await _as(client, world["super_admin"])
    response = await client.post(
        "/api/v1/institutes",
        json={"name": "New College", "code": "NEW", "type": "college"},
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("role", ["abc_admin", "abc_branch_admin", "abc_faculty", "abc_student"])
async def test_nobody_below_platform_can_create_an_institute(
    client: AsyncClient, world, role: str
) -> None:
    """PRD §5.3: institute:create is platform-only."""
    await _as(client, world[role])
    response = await client.post(
        "/api/v1/institutes", json={"name": "Sneaky", "code": "SNK", "type": "college"}
    )
    assert response.status_code == 403


async def test_an_institute_admin_sees_only_their_own_institute(client: AsyncClient, world) -> None:
    """PRD §13 criterion 5."""
    await _as(client, world["abc_admin"])
    response = await client.get("/api/v1/institutes")
    assert response.status_code == 200
    codes = {item["code"] for item in response.json()["items"]}
    assert codes == {"ABC"}


async def test_platform_admin_sees_every_institute(client: AsyncClient, world) -> None:
    await _as(client, world["platform_admin"])
    codes = {i["code"] for i in (await client.get("/api/v1/institutes")).json()["items"]}
    assert {"ABC", "XYZ"} <= codes


async def test_an_admin_cannot_read_another_institute(client: AsyncClient, world) -> None:
    """PRD §13 criterion 8: two institutes cannot see each other's data."""
    await _as(client, world["abc_admin"])
    response = await client.get(f"/api/v1/institutes/{world['xyz'].id}")
    assert response.status_code == 403


async def test_an_admin_cannot_edit_another_institute(client: AsyncClient, world) -> None:
    await _as(client, world["abc_admin"])
    response = await client.patch(
        f"/api/v1/institutes/{world['xyz'].id}", json={"name": "Hijacked"}
    )
    assert response.status_code == 403


async def test_the_direct_institute_cannot_be_archived(client: AsyncClient, world, db) -> None:
    """PRD §2: the built-in institute holding self-registered learners is permanent."""
    from sqlalchemy import select

    from app.modules.org.models import Institute
    from app.modules.rbac.catalog import DIRECT_INSTITUTE_CODE

    direct = await db.scalar(select(Institute).where(Institute.code == DIRECT_INSTITUTE_CODE))
    await _as(client, world["super_admin"])
    response = await client.post(f"/api/v1/institutes/{direct.id}/archive")
    assert response.status_code == 403


# --------------------------------------------------------------------- branch access


async def test_an_institute_admin_can_create_a_branch(client: AsyncClient, world) -> None:
    await _as(client, world["abc_admin"])
    response = await client.post(
        f"/api/v1/institutes/{world['abc'].id}/branches",
        json={"name": "BCA", "code": "BCA"},
    )
    assert response.status_code == 201, response.text


async def test_a_branch_admin_cannot_create_a_branch(client: AsyncClient, world) -> None:
    """PRD §5.3: branch:create is institute level and above."""
    await _as(client, world["abc_branch_admin"])
    response = await client.post(
        f"/api/v1/institutes/{world['abc'].id}/branches",
        json={"name": "Sneaky", "code": "SNK"},
    )
    assert response.status_code == 403


async def test_an_admin_cannot_create_a_branch_in_another_institute(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_admin"])
    response = await client.post(
        f"/api/v1/institutes/{world['xyz'].id}/branches",
        json={"name": "Invader", "code": "INV"},
    )
    assert response.status_code == 403


# ----------------------------------------------------------------------- user access


async def test_a_student_cannot_reach_any_admin_endpoint(client: AsyncClient, world) -> None:
    """PRD §13 criterion 7."""
    await _as(client, world["abc_student"])
    for method, path in [
        ("GET", "/api/v1/audit-logs"),
        ("POST", "/api/v1/users/invite"),
        ("GET", f"/api/v1/institutes/{world['abc'].id}/branches"),
    ]:
        response = await client.request(method, path, json={} if method == "POST" else None)
        assert response.status_code in (403, 422), (
            f"{method} {path} returned {response.status_code}"
        )


async def test_a_student_can_read_their_own_profile(client: AsyncClient, world) -> None:
    await _as(client, world["abc_student"])
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == world["abc_student"].email


async def test_an_institute_admin_lists_only_their_own_users(client: AsyncClient, world) -> None:
    """PRD §13 criterion 8, from the user-list side."""
    await _as(client, world["abc_admin"])
    emails = {u["email"] for u in (await client.get("/api/v1/users")).json()["items"]}
    assert world["xyz_admin"].email not in emails
    assert world["abc_faculty"].email in emails


async def test_an_admin_cannot_read_a_user_from_another_institute(
    client: AsyncClient, world
) -> None:
    """404 rather than 403: a 403 would confirm the account exists."""
    await _as(client, world["abc_admin"])
    response = await client.get(f"/api/v1/users/{world['xyz_admin'].id}")
    assert response.status_code == 404


# ---------------------------------------------------------------- no escalation rule


async def test_an_institute_admin_cannot_create_another_institute_admin(
    client: AsyncClient, world
) -> None:
    """PRD §13 criterion 6: nobody grants a role at or above their own level."""
    await _as(client, world["abc_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Rival Admin",
            "email": "rival@example.com",
            "role_key": "institute_admin",
            "institute_id": str(world["abc"].id),
        },
    )
    assert response.status_code == 403


async def test_an_institute_admin_cannot_create_a_platform_admin(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Escalated",
            "email": "escalated@example.com",
            "role_key": "platform_admin",
        },
    )
    assert response.status_code == 403


async def test_an_institute_admin_can_create_a_branch_admin(client: AsyncClient, world) -> None:
    await _as(client, world["abc_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "New Branch Admin",
            "email": "newba@example.com",
            "role_key": "branch_admin",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
        },
    )
    assert response.status_code == 201, response.text


async def test_a_branch_admin_cannot_create_a_branch_admin(client: AsyncClient, world) -> None:
    await _as(client, world["abc_branch_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Peer",
            "email": "peer@example.com",
            "role_key": "branch_admin",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
        },
    )
    assert response.status_code == 403


async def test_a_branch_admin_can_invite_faculty_in_their_own_branch(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_branch_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "New Teacher",
            "email": "teacher@example.com",
            "role_key": "faculty",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
        },
    )
    assert response.status_code == 201, response.text


async def test_a_branch_admin_cannot_invite_into_another_institute(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_branch_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Outsider",
            "email": "outsider@example.com",
            "role_key": "faculty",
            "institute_id": str(world["xyz"].id),
            "branch_id": str(world["xyz_branch"].id),
        },
    )
    assert response.status_code == 403


async def test_a_student_cannot_invite_anyone(client: AsyncClient, world) -> None:
    await _as(client, world["abc_student"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Friend",
            "email": "friend@example.com",
            "role_key": "student",
            "institute_id": str(world["abc"].id),
        },
    )
    assert response.status_code == 403


async def test_the_assignable_role_list_never_offers_a_peer_role(
    client: AsyncClient, world
) -> None:
    """The UI must not be able to offer a choice the backend would reject."""
    await _as(client, world["abc_admin"])
    response = await client.get("/api/v1/users/roles/catalogue")
    assert response.status_code == 200
    keys = {r["key"] for r in response.json()}
    assert "institute_admin" not in keys
    assert "platform_admin" not in keys
    assert "branch_admin" in keys


# -------------------------------------------------------------------- status changes


async def test_an_admin_can_suspend_a_user_in_their_scope(client: AsyncClient, world) -> None:
    await _as(client, world["abc_admin"])
    response = await client.patch(
        f"/api/v1/users/{world['abc_faculty'].id}/status", json={"status": "suspended"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"


async def test_an_admin_cannot_suspend_a_user_in_another_institute(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_admin"])
    response = await client.patch(
        f"/api/v1/users/{world['xyz_admin'].id}/status", json={"status": "suspended"}
    )
    assert response.status_code == 404


async def test_nobody_can_suspend_themselves(client: AsyncClient, world) -> None:
    """A self-suspension would lock an institute out of its own account."""
    await _as(client, world["abc_admin"])
    response = await client.patch(
        f"/api/v1/users/{world['abc_admin'].id}/status", json={"status": "suspended"}
    )
    assert response.status_code == 403


async def test_a_faculty_cannot_suspend_a_student(client: AsyncClient, world) -> None:
    await _as(client, world["abc_faculty"])
    response = await client.patch(
        f"/api/v1/users/{world['abc_student'].id}/status", json={"status": "suspended"}
    )
    assert response.status_code == 403


# -------------------------------------------------------------------------- audit log


async def test_an_institute_admin_sees_only_their_own_audit_rows(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_admin"])
    response = await client.get("/api/v1/audit-logs")
    assert response.status_code == 200
    institute_ids = {row["institute_id"] for row in response.json()["items"]}
    assert str(world["xyz"].id) not in institute_ids


async def test_a_faculty_cannot_read_the_audit_log(client: AsyncClient, world) -> None:
    await _as(client, world["abc_faculty"])
    assert (await client.get("/api/v1/audit-logs")).status_code == 403
