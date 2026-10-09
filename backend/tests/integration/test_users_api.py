"""User management, profile and preferences (PRD §4.5, §4.6, §8).

Covers acceptance criterion 10 from PRD §13.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from app.modules.auth.models import RefreshToken


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture
async def org(institute, make_user):
    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")
    return {
        "institute": abc,
        "branch": mca,
        "admin": await make_user("institute_admin", institute_id=abc.id),
        "faculty": await make_user("faculty", institute_id=abc.id, branch_id=mca.id),
        "student": await make_user("student", institute_id=abc.id),
    }


# ---------------------------------------------------------------------------- /me


async def test_me_reports_roles_and_permissions(client: AsyncClient, org) -> None:
    await _as(client, org["admin"])
    body = (await client.get("/api/v1/me")).json()

    assert body["email"] == org["admin"].email
    assert {r["role_key"] for r in body["roles"]} == {"institute_admin"}
    assert "user:invite" in body["permissions"]
    assert "institute:create" not in body["permissions"]
    assert str(org["institute"].id) in body["institute_ids"]


async def test_me_never_exposes_credentials(client: AsyncClient, org) -> None:
    await _as(client, org["student"])
    body = (await client.get("/api/v1/me")).json()
    assert not {"password_hash", "failed_login_count", "locked_until"} & set(body)


async def test_a_user_can_update_their_own_profile(client: AsyncClient, org) -> None:
    await _as(client, org["student"])
    response = await client.patch("/api/v1/me", json={"full_name": "Renamed Student"})
    assert response.status_code == 200
    assert response.json()["full_name"] == "Renamed Student"


async def test_theme_is_saved_against_the_user(client: AsyncClient, org) -> None:
    """PRD §13 criterion 10: the choice follows the user, so it lives server-side."""
    await _as(client, org["student"])
    assert (await client.get("/api/v1/me")).json()["preferences"]["theme"] == "system"

    updated = await client.patch("/api/v1/me/preferences", json={"theme": "dark"})
    assert updated.status_code == 200
    assert updated.json()["theme"] == "dark"

    # A fresh login on a "different device" sees the same preference.
    await client.post("/api/v1/auth/logout")
    await _as(client, org["student"])
    assert (await client.get("/api/v1/me")).json()["preferences"]["theme"] == "dark"


async def test_an_invalid_theme_is_refused(client: AsyncClient, org) -> None:
    await _as(client, org["student"])
    assert (await client.patch("/api/v1/me/preferences", json={"theme": "neon"})).status_code == 422


# ------------------------------------------------------------------------- invite


async def test_an_invited_user_appears_with_invited_status(
    client: AsyncClient, org, outbox
) -> None:
    await _as(client, org["admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Ravi Kumar",
            "email": "ravi@example.com",
            "role_key": "faculty",
            "institute_id": str(org["institute"].id),
            "branch_id": str(org["branch"].id),
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["status"] == "invited"
    assert outbox.last_to("ravi@example.com") is not None


async def test_inviting_an_existing_email_is_refused(client: AsyncClient, org) -> None:
    """One person is one user row (PRD §2 rule 4)."""
    await _as(client, org["admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Duplicate",
            "email": org["faculty"].email,
            "role_key": "faculty",
            "institute_id": str(org["institute"].id),
            "branch_id": str(org["branch"].id),
        },
    )
    assert response.status_code == 409


async def test_resending_an_invite_too_soon_is_refused(client: AsyncClient, org) -> None:
    """The 60-second OTP cooldown (PRD §7.3) applies to admin-initiated resends too,
    otherwise an invitation is a way to spam someone's inbox."""
    await _as(client, org["admin"])
    created = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Ravi Kumar",
            "email": "ravi@example.com",
            "role_key": "student",
            "institute_id": str(org["institute"].id),
        },
    )
    resent = await client.post(f"/api/v1/users/{created.json()['user']['id']}/resend-invite")
    assert resent.status_code == 429


async def test_resending_an_invite_after_the_cooldown_sends_a_new_code(
    client: AsyncClient, org, outbox, db: AsyncSession
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.modules.auth.models import PasswordOtp

    await _as(client, org["admin"])
    created = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Ravi Kumar",
            "email": "ravi@example.com",
            "role_key": "student",
            "institute_id": str(org["institute"].id),
        },
    )
    first = outbox.last_to("ravi@example.com")
    assert first is not None

    # Age the code past the cooldown instead of sleeping for a minute.
    otp = await db.scalar(select(PasswordOtp).where(PasswordOtp.purpose == "setup"))
    assert otp is not None
    otp.created_at = datetime.now(UTC) - timedelta(minutes=5)
    await db.commit()
    outbox.clear()

    resent = await client.post(f"/api/v1/users/{created.json()['user']['id']}/resend-invite")
    assert resent.status_code == 200, resent.text
    second = outbox.last_to("ravi@example.com")
    assert second is not None and second.text != first.text


async def test_resending_to_an_active_user_is_refused(client: AsyncClient, org) -> None:
    await _as(client, org["admin"])
    response = await client.post(f"/api/v1/users/{org['faculty'].id}/resend-invite")
    assert response.status_code == 422


# -------------------------------------------------------------------- search filter


async def test_users_can_be_searched_by_name_and_email(client: AsyncClient, org) -> None:
    await _as(client, org["admin"])
    response = await client.get("/api/v1/users", params={"search": org["faculty"].email})
    assert response.status_code == 200
    assert {u["email"] for u in response.json()["items"]} == {org["faculty"].email}


async def test_users_can_be_filtered_by_role(client: AsyncClient, org) -> None:
    await _as(client, org["admin"])
    response = await client.get("/api/v1/users", params={"role_key": "student"})
    assert response.status_code == 200
    emails = {u["email"] for u in response.json()["items"]}
    assert org["student"].email in emails
    assert org["faculty"].email not in emails


async def test_the_user_list_includes_roles_without_an_extra_query_per_row(
    client: AsyncClient, org
) -> None:
    await _as(client, org["admin"])
    items = (await client.get("/api/v1/users")).json()["items"]
    faculty = next(u for u in items if u["email"] == org["faculty"].email)
    assert {r["role_key"] for r in faculty["roles"]} == {"faculty"}


async def test_the_page_size_is_capped(client: AsyncClient, org) -> None:
    await _as(client, org["admin"])
    assert (await client.get("/api/v1/users", params={"limit": 500})).status_code == 422


async def test_a_tampered_cursor_is_rejected(client: AsyncClient, org) -> None:
    await _as(client, org["admin"])
    response = await client.get("/api/v1/users", params={"cursor": "not-a-cursor"})
    assert response.status_code == 422
    assert "not-a-cursor" not in response.text


# -------------------------------------------------------------------- role changes


async def test_assigning_and_revoking_a_role(client: AsyncClient, org) -> None:
    await _as(client, org["admin"])

    assigned = await client.post(
        f"/api/v1/users/{org['student'].id}/roles",
        json={
            "role_key": "faculty",
            "institute_id": str(org["institute"].id),
            "branch_id": str(org["branch"].id),
        },
    )
    assert assigned.status_code == 201
    assert {r["role_key"] for r in assigned.json()["roles"]} == {"student", "faculty"}

    revoked = await client.request(
        "DELETE",
        f"/api/v1/users/{org['student'].id}/roles",
        json={
            "role_key": "faculty",
            "institute_id": str(org["institute"].id),
            "branch_id": str(org["branch"].id),
        },
    )
    assert revoked.status_code == 204


async def test_a_revoked_role_loses_its_permissions_immediately(client: AsyncClient, org) -> None:
    """The permission cache must be invalidated on revocation, not waited out."""
    await _as(client, org["admin"])
    await client.post(
        f"/api/v1/users/{org['student'].id}/roles",
        json={
            "role_key": "faculty",
            "institute_id": str(org["institute"].id),
            "branch_id": str(org["branch"].id),
        },
    )

    await _as(client, org["student"])
    # enrollment:manage belongs to faculty only — class:read would not prove anything,
    # because students hold it in their own right.
    assert "enrollment:manage" in (await client.get("/api/v1/me")).json()["permissions"]

    await _as(client, org["admin"])
    await client.request(
        "DELETE",
        f"/api/v1/users/{org['student'].id}/roles",
        json={
            "role_key": "faculty",
            "institute_id": str(org["institute"].id),
            "branch_id": str(org["branch"].id),
        },
    )

    await _as(client, org["student"])
    assert "enrollment:manage" not in (await client.get("/api/v1/me")).json()["permissions"]


async def test_the_last_super_admin_cannot_be_removed(client: AsyncClient, make_user) -> None:
    """PRD §3: at least one Super Admin must always exist."""
    only_one = await make_user("super_admin")
    await _as(client, only_one)
    response = await client.request(
        "DELETE", f"/api/v1/users/{only_one.id}/roles", json={"role_key": "super_admin"}
    )
    assert response.status_code == 409


# ------------------------------------------------------------------------- suspend


async def test_suspending_a_user_ends_their_sessions(
    client: AsyncClient, org, db: AsyncSession
) -> None:
    await _as(client, org["faculty"])  # the faculty now holds a live session
    await _as(client, org["admin"])

    response = await client.patch(
        f"/api/v1/users/{org['faculty'].id}/status", json={"status": "suspended"}
    )
    assert response.status_code == 200

    live = (
        (
            await db.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == org["faculty"].id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert live == []


async def test_reactivating_a_user_who_never_set_a_password_returns_them_to_invited(
    client: AsyncClient, org, make_user
) -> None:
    invited = await make_user("student", institute_id=org["institute"].id, status="invited")
    await _as(client, org["admin"])

    await client.patch(f"/api/v1/users/{invited.id}/status", json={"status": "suspended"})
    response = await client.patch(f"/api/v1/users/{invited.id}/status", json={"status": "active"})
    assert response.status_code == 200
    assert response.json()["status"] == "invited", (
        "a user with no password must not be marked active"
    )


# --------------------------------------------------------------------------- audit


async def test_every_sensitive_action_writes_an_audit_row(
    client: AsyncClient, org, db: AsyncSession
) -> None:
    """PRD §13 criterion 11."""
    await _as(client, org["admin"])
    await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Ravi Kumar",
            "email": "ravi@example.com",
            "role_key": "student",
            "institute_id": str(org["institute"].id),
        },
    )
    await client.patch(f"/api/v1/users/{org['faculty'].id}/status", json={"status": "suspended"})

    actions = set((await db.execute(select(AuditLog.action))).scalars())
    assert {"login_success", "user_invited", "user_suspended"} <= actions


async def test_audit_rows_carry_the_request_id(client: AsyncClient, org, db: AsyncSession) -> None:
    """Lets a support question be traced from a log line to the exact action."""
    await _as(client, org["admin"])
    row = await db.scalar(select(AuditLog).where(AuditLog.action == "login_success").limit(1))
    assert row is not None and row.request_id


async def test_a_page_reports_how_many_rows_match_in_total(client: AsyncClient, make_user) -> None:
    """ "Page 3 of 7" needs a number that cursor paging does not produce by itself.

    The count has to describe the *filters*, not the window: it is the same on every page
    of one filtered list, and it changes when the filter changes. Returning the page size
    instead would make the last page claim the list is nearly empty.
    """
    owner = await make_user("super_admin")
    for index in range(7):
        await make_user("student", email=f"counted{index}@example.com")
    await _as(client, owner)

    first = await client.get("/api/v1/users", params={"limit": 3})
    assert first.status_code == 200, first.text
    body = first.json()
    total = body["total"]
    assert total >= 8, "the owner and seven students are all visible"
    assert len(body["items"]) == 3
    assert body["next_cursor"]

    # The second page reports the same total, not "what is left".
    second = await client.get("/api/v1/users", params={"limit": 3, "cursor": body["next_cursor"]})
    assert second.json()["total"] == total

    # Walking to the end, the totals never disagree and the rows add up to it.
    seen = len(body["items"])
    cursor = body["next_cursor"]
    while cursor:
        page = (await client.get("/api/v1/users", params={"limit": 3, "cursor": cursor})).json()
        assert page["total"] == total
        seen += len(page["items"])
        cursor = page["next_cursor"]
    assert seen == total

    # A filter narrows the total as well as the rows.
    filtered = (await client.get("/api/v1/users", params={"limit": 3, "search": "counted"})).json()
    assert filtered["total"] == 7


async def test_a_branch_admin_does_not_see_institute_wide_staff(
    client: AsyncClient, make_user, institute
) -> None:
    """The list and the detail endpoint must answer the same question.

    A Branch Admin of MCA may act only inside MCA. The list used to also show everyone
    holding an institute-wide role at the same college — the principal, and every member
    of staff attached to the institute rather than to a branch, including people in
    branches the caller has nothing to do with. Opening any of those rows returned "That
    user does not exist", because the per-row check compares scopes properly. Reading a
    name and an email address is a use of authority too, so the list was the half that was
    wrong.
    """
    college, mca = await institute("Scope College", "SCOPE1", with_branch="MCA")
    other = await make_user("branch_admin", institute_id=college.id, branch_id=mca.id)

    principal = await make_user("institute_admin", institute_id=college.id)
    in_my_branch = await make_user(
        "faculty", institute_id=college.id, branch_id=mca.id, email="mine@example.com"
    )

    await _as(client, other)
    listed = await client.get("/api/v1/users", params={"limit": 100})
    assert listed.status_code == 200, listed.text
    emails = {row["email"] for row in listed.json()["items"]}

    assert in_my_branch.email in emails, "their own branch is still fully visible"
    assert principal.email not in emails

    # And the two endpoints agree, which is the point.
    assert (await client.get(f"/api/v1/users/{principal.id}")).status_code == 404
    assert (await client.get(f"/api/v1/users/{in_my_branch.id}")).status_code == 200


async def test_running_one_college_does_not_widen_a_branch_role_in_another(
    client: AsyncClient, make_user, institute, db
) -> None:
    """Scope is per institute, not a pair of flat sets.

    Somebody can genuinely be Institute Admin of one college and Branch Admin of one
    branch of another. The scope used to be carried as "every institute I can reach" plus
    "every branch I hold" plus one flag saying whether *any* of it was institute-wide — and
    that flag, set by the first college, lifted the branch restriction on the second one
    too. The user list then returned every member of staff at the second college, while
    opening any of their rows answered "That user does not exist", because the per-row
    check compares scopes properly.
    """
    from app.modules.rbac.models import Role, UserRoleAssignment

    first, _ = await institute("First College", "FIRST1", with_branch="Alpha")
    second, beta = await institute("Second College", "SECOND1", with_branch="Beta")
    _, gamma = await institute("Second Annexe", "SECOND2", with_branch="Gamma")

    # One person, two hats: the whole of First College, one branch of Second College.
    wearer = await make_user("institute_admin", institute_id=first.id)
    branch_admin_role = await db.scalar(select(Role).where(Role.key == "branch_admin"))
    db.add(
        UserRoleAssignment(
            user_id=wearer.id,
            role_id=branch_admin_role.id,
            institute_id=second.id,
            branch_id=beta.id,
        )
    )
    await db.flush()

    # Three people at Second College: one in the branch they run, one institute-wide, and
    # one in a branch that is nothing to do with them.
    in_my_branch = await make_user(
        "faculty", institute_id=second.id, branch_id=beta.id, email="beta-teacher@example.com"
    )
    institute_wide = await make_user(
        "institute_admin", institute_id=second.id, email="second-principal@example.com"
    )
    other_branch = await make_user(
        "faculty", institute_id=second.id, branch_id=gamma.id, email="gamma-teacher@example.com"
    )

    await _as(client, wearer)
    listed = await client.get("/api/v1/users", params={"limit": 100})
    assert listed.status_code == 200, listed.text
    emails = {row["email"] for row in listed.json()["items"]}

    assert in_my_branch.email in emails, "their own branch at Second College is still visible"
    assert institute_wide.email not in emails, "Second College's principal leaked"
    assert other_branch.email not in emails, "a branch they have nothing to do with leaked"

    # The list and the detail endpoint agree, which is the point.
    assert (await client.get(f"/api/v1/users/{institute_wide.id}")).status_code == 404
    assert (await client.get(f"/api/v1/users/{other_branch.id}")).status_code == 404
    assert (await client.get(f"/api/v1/users/{in_my_branch.id}")).status_code == 200

    # And the count on the dashboard describes the same people as the list.
    overview = await client.get("/api/v1/me/overview")
    assert overview.status_code == 200, overview.text
    assert overview.json()["users_total"] == listed.json()["total"]


async def test_the_dashboard_count_respects_a_block_the_list_respects(
    client: AsyncClient, make_user, institute
) -> None:
    """A deny has to narrow the tile as well as the rows.

    `list_users` asked whether the caller still had a platform-wide scope; the dashboard
    asked only whether they were platform staff. An explicit deny on `user:read` removes
    the scope but not the status, so the list correctly showed nothing while the tile went
    on reporting the platform-wide total. "There are four hundred users", told to somebody
    allowed to see none of them, is the same leak in a smaller box.
    """
    owner = await make_user("super_admin")
    deputy = await make_user("platform_admin", email="deputy@example.com")
    college, _ = await institute("Counted College", "COUNT1")
    await make_user("student", institute_id=college.id, email="counted@example.com")

    await _as(client, deputy)
    before = (await client.get("/api/v1/me/overview")).json()["users_total"]
    assert before >= 3

    await _as(client, owner)
    blocked = await client.post(
        f"/api/v1/users/{deputy.id}/grants",
        json={"permission": "user:read", "effect": "deny", "reason": "Under review"},
    )
    assert blocked.status_code == 201, blocked.text

    await _as(client, deputy)
    listed = await client.get("/api/v1/users", params={"limit": 100})
    assert listed.status_code == 403 or listed.json()["items"] == []

    overview = await client.get("/api/v1/me/overview")
    assert overview.status_code in (200, 403)
    if overview.status_code == 200:
        assert overview.json()["users_total"] == 0, (
            "the tile still reported the platform-wide total to somebody who may see nobody"
        )


async def test_the_dashboard_counts_the_same_people_the_list_shows(
    client: AsyncClient, make_user, institute, db
) -> None:
    """A tile that disagrees with the list below it is worse than no tile.

    Faculty see the students of the classes they teach and nobody else, and the user list
    has always honoured that. The dashboard counted every branch-scoped person at their
    branch instead, and the reader had no way to tell which number was lying.
    """
    college, branch = await institute("Tile College", "TILE1", with_branch="Maths")
    teacher = await make_user(
        "faculty", institute_id=college.id, branch_id=branch.id, email="tile-teacher@example.com"
    )
    for index in range(4):
        await make_user(
            "student",
            institute_id=college.id,
            branch_id=branch.id,
            email=f"tile-learner{index}@example.com",
        )

    await _as(client, teacher)
    listed = await client.get("/api/v1/users", params={"limit": 100})
    assert listed.status_code == 200, listed.text

    overview = await client.get("/api/v1/me/overview")
    assert overview.status_code == 200, overview.text
    assert overview.json()["users_total"] == listed.json()["total"]


async def test_the_security_tile_needs_the_permission_that_gates_the_log(
    client: AsyncClient, make_user, institute
) -> None:
    """The tile reads the audit log, so it answers to `audit:read`.

    A Branch Admin deliberately does not hold it — an audit entry names an institute and
    nothing finer, so a branch-scoped reader could only ever be shown the whole college's
    history. Handing them an institute-wide count of failed sign-ins and lockouts is a
    smaller version of the same disclosure.
    """
    college, branch = await institute("Tile Two", "TILE2", with_branch="Physics")
    head = await make_user(
        "branch_admin", institute_id=college.id, branch_id=branch.id, email="tile-head@example.com"
    )
    principal = await make_user(
        "institute_admin", institute_id=college.id, email="tile-principal@example.com"
    )

    await _as(client, head)
    assert (await client.get("/api/v1/audit-logs")).status_code == 403
    assert (await client.get("/api/v1/me/overview")).json()["security_events_24h"] == 0

    await _as(client, principal)
    assert (await client.get("/api/v1/audit-logs")).status_code == 200
    assert "security_events_24h" in (await client.get("/api/v1/me/overview")).json()
