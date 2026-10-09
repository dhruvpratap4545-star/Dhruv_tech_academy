"""Custom roles and per-user permission grants, end to end (ADR-017).

Four things are worth proving here, and each gets both halves — the case that must work and
the case one step beyond it that must not:

1. **Deny beats everything.** That is the entire reason the feature exists; if a role can
   out-vote a block, the block is decoration.
2. **You cannot hand out what you do not hold.** Both routes to it — a custom role's
   permission list, and a direct grant — because closing one and leaving the other open
   closes nothing.
3. **You cannot edit your own access, or a peer's.** Every escalation story starts there.
4. **Lists narrow as well as detail endpoints.** A deny the per-row check honours but the
   list query ignores is a deny that leaks exactly the rows it was created to hide.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "testpassword9!"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture
async def world(institute, make_user, db):
    """One institute, two branches, and somebody at every level that matters."""
    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")

    from app.modules.org.models import Branch

    bca = Branch(institute_id=abc.id, name="BCA", code="BCA")
    db.add(bca)
    await db.commit()

    return {
        "abc": abc,
        "mca": mca,
        "bca": bca,
        "owner": await make_user("super_admin"),
        "principal": await make_user("institute_admin", institute_id=abc.id),
        "head": await make_user("branch_admin", institute_id=abc.id, branch_id=mca.id),
        "teacher": await make_user("faculty", institute_id=abc.id, branch_id=mca.id),
    }


# ----------------------------------------------------------------- deny beats everything


async def test_a_block_overrides_the_role_that_grants_it(client, world):
    """The headline rule. A Branch Admin holds `user:read`; a block must end that."""
    await _as(client, world["principal"])
    allowed = await client.get("/api/v1/users", params={"institute_id": str(world["abc"].id)})
    assert allowed.status_code == 200

    response = await client.post(
        f"/api/v1/users/{world['head'].id}/grants",
        json={
            "permission": "user:read",
            "effect": "deny",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
            "reason": "Under investigation for sharing student records",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["effect"] == "deny"

    await _as(client, world["head"])
    blocked = await client.get("/api/v1/users", params={"institute_id": str(world["abc"].id)})
    assert blocked.status_code == 403


async def test_a_block_on_one_branch_leaves_the_other_alone(client, world, make_user):
    """Blocks are scoped, not global. The sibling branch must be untouched."""
    other_head = await make_user(
        "branch_admin", institute_id=world["abc"].id, branch_id=world["bca"].id
    )
    await _as(client, world["principal"])
    response = await client.post(
        f"/api/v1/users/{world['head'].id}/grants",
        json={
            "permission": "user:read",
            "effect": "deny",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
            "reason": "Temporary block during handover",
        },
    )
    assert response.status_code == 201

    await _as(client, other_head)
    assert (
        await client.get("/api/v1/users", params={"institute_id": str(world["abc"].id)})
    ).status_code == 200


async def test_lifting_a_block_restores_access_immediately(client, world):
    """No waiting out the permission cache: revoking must take effect on the next request."""
    await _as(client, world["principal"])
    created = await client.post(
        f"/api/v1/users/{world['head'].id}/grants",
        json={
            "permission": "audit:read",
            "effect": "deny",
            "institute_id": str(world["abc"].id),
            "reason": "Blocked pending review",
        },
    )
    grant_id = created.json()["id"]

    await _as(client, world["head"])
    assert (await client.get("/api/v1/audit-logs")).status_code == 403

    await _as(client, world["principal"])
    removed = await client.delete(f"/api/v1/users/{world['head'].id}/grants/{grant_id}")
    assert removed.status_code == 204

    await _as(client, world["head"])
    assert (await client.get("/api/v1/audit-logs")).status_code == 200


async def test_an_expired_grant_does_not_apply(client, world, db):
    """Expiry is the difference between covering someone's leave and a permanent promotion."""
    from sqlalchemy import select

    from app.modules.rbac.context import context_cache
    from app.modules.rbac.models import UserPermissionGrant

    await _as(client, world["principal"])
    created = await client.post(
        f"/api/v1/users/{world['teacher'].id}/grants",
        json={
            "permission": "audit:read",
            "effect": "allow",
            "institute_id": str(world["abc"].id),
            "reason": "Covering for the branch head this week",
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
    )
    assert created.status_code == 201

    await _as(client, world["teacher"])
    assert (await client.get("/api/v1/audit-logs")).status_code == 200

    # Wind the clock past the expiry rather than waiting a week for it.
    grant = await db.scalar(
        select(UserPermissionGrant).where(UserPermissionGrant.id == uuid.UUID(created.json()["id"]))
    )
    grant.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    context_cache.invalidate(world["teacher"].id)

    await _as(client, world["teacher"])
    assert (await client.get("/api/v1/audit-logs")).status_code == 403


# ----------------------------------------------------- you cannot give away what you lack


async def test_a_grant_cannot_exceed_what_the_granter_holds(client, world):
    """An Institute Admin has no `platform_admin:manage`, so they cannot confer it."""
    await _as(client, world["principal"])
    response = await client.post(
        f"/api/v1/users/{world['head'].id}/grants",
        json={
            "permission": "platform_admin:manage",
            "effect": "allow",
            "institute_id": str(world["abc"].id),
            "reason": "Trying to escalate",
        },
    )
    assert response.status_code == 403


async def test_a_custom_role_cannot_exceed_what_its_creator_holds(client, world):
    """The same ceiling by the other route, which is the one people forget to close."""
    await _as(client, world["principal"])
    response = await client.post(
        "/api/v1/roles",
        json={
            "name": "Shadow Admin",
            "scope_level": "institute",
            "rank": 60,
            "institute_id": str(world["abc"].id),
            "permissions": ["user:read", "platform_admin:manage"],
        },
    )
    assert response.status_code == 403
    assert "platform_admin:manage" in response.json()["error"]["message"]


async def test_a_block_may_name_a_permission_the_granter_lacks(client, world):
    """Deliberately asymmetric: blocking only ever removes access, so it needs no ceiling."""
    await _as(client, world["principal"])
    response = await client.post(
        f"/api/v1/users/{world['head'].id}/grants",
        json={
            "permission": "platform_admin:manage",
            "effect": "deny",
            "institute_id": str(world["abc"].id),
            "reason": "Belt and braces",
        },
    )
    assert response.status_code == 201


# --------------------------------------------------------------------- self and peers


async def test_nobody_can_change_their_own_access(client, world):
    await _as(client, world["principal"])
    response = await client.post(
        f"/api/v1/users/{world['principal'].id}/grants",
        json={
            "permission": "user:read",
            "effect": "allow",
            "institute_id": str(world["abc"].id),
            "reason": "Self service",
        },
    )
    assert response.status_code == 403


async def test_a_peer_cannot_change_a_peer(client, world, make_user):
    peer = await make_user("institute_admin", institute_id=world["abc"].id)
    await _as(client, world["principal"])
    response = await client.post(
        f"/api/v1/users/{peer.id}/grants",
        json={
            "permission": "audit:read",
            "effect": "deny",
            "institute_id": str(world["abc"].id),
            "reason": "Peer attack",
        },
    )
    assert response.status_code == 403


async def test_a_branch_admin_cannot_grant_into_a_sibling_branch(client, world, make_user):
    victim = await make_user("faculty", institute_id=world["abc"].id, branch_id=world["bca"].id)
    await _as(client, world["head"])
    response = await client.post(
        f"/api/v1/users/{victim.id}/grants",
        json={
            "permission": "class:read",
            "effect": "allow",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["bca"].id),
            "reason": "Reaching across branches",
        },
    )
    # A Branch Admin holds no `permission:grant` at all, so this never gets as far as scope.
    assert response.status_code == 403


# ------------------------------------------------------------------------ custom roles


async def test_a_custom_role_can_be_created_assigned_and_used(client, world, make_user):
    await _as(client, world["principal"])
    created = await client.post(
        "/api/v1/roles",
        json={
            "name": "Lab Assistant",
            "description": "Can see classes and people, nothing else.",
            "scope_level": "branch",
            "rank": 20,
            "institute_id": str(world["abc"].id),
            "permissions": ["class:read", "user:read", "profile:read", "profile:update"],
        },
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["key"] == "abc.lab_assistant"
    assert role["is_system"] is False
    assert role["editable"] is True

    helper = await make_user("student", institute_id=world["abc"].id)
    assigned = await client.post(
        f"/api/v1/users/{helper.id}/roles",
        json={
            "role_key": "abc.lab_assistant",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
        },
    )
    assert assigned.status_code == 201, assigned.text

    await _as(client, helper)
    me = await client.get("/api/v1/me")
    assert "class:read" in me.json()["permissions"]
    assert "user:update_status" not in me.json()["permissions"]


async def test_a_custom_role_is_invisible_to_another_institute(client, world, institute, make_user):
    await _as(client, world["principal"])
    await client.post(
        "/api/v1/roles",
        json={
            "name": "Lab Assistant",
            "scope_level": "branch",
            "rank": 20,
            "institute_id": str(world["abc"].id),
            "permissions": ["class:read"],
        },
    )

    xyz, _ = await institute("XYZ College", "XYZ", with_branch="CSE")
    outsider = await make_user("institute_admin", institute_id=xyz.id)
    await _as(client, outsider)
    keys = [r["key"] for r in (await client.get("/api/v1/roles")).json()]
    assert "abc.lab_assistant" not in keys
    assert "institute_admin" in keys, "built-in roles stay visible to everyone"


async def test_a_role_in_use_cannot_be_archived(client, world, make_user):
    await _as(client, world["principal"])
    created = await client.post(
        "/api/v1/roles",
        json={
            "name": "Lab Assistant",
            "scope_level": "branch",
            "rank": 20,
            "institute_id": str(world["abc"].id),
            "permissions": ["class:read"],
        },
    )
    role_id = created.json()["id"]
    helper = await make_user("student", institute_id=world["abc"].id)
    await client.post(
        f"/api/v1/users/{helper.id}/roles",
        json={
            "role_key": "abc.lab_assistant",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
        },
    )

    response = await client.post(f"/api/v1/roles/{role_id}/archive")
    assert response.status_code == 409
    assert "1 person holds" in response.json()["error"]["message"]


async def test_removing_a_permission_from_a_role_takes_effect_at_once(client, world, make_user):
    """The cache must be dropped for every holder, not waited out — a permission is usually
    removed precisely because it is being misused."""
    await _as(client, world["principal"])
    created = await client.post(
        "/api/v1/roles",
        json={
            "name": "Lab Assistant",
            "scope_level": "branch",
            "rank": 20,
            "institute_id": str(world["abc"].id),
            "permissions": ["class:read", "audit:read"],
        },
    )
    role_id = created.json()["id"]
    helper = await make_user("student", institute_id=world["abc"].id)
    await client.post(
        f"/api/v1/users/{helper.id}/roles",
        json={
            "role_key": "abc.lab_assistant",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
        },
    )

    await _as(client, helper)
    assert (await client.get("/api/v1/audit-logs")).status_code == 200

    await _as(client, world["principal"])
    updated = await client.patch(f"/api/v1/roles/{role_id}", json={"permissions": ["class:read"]})
    assert updated.status_code == 200

    await _as(client, helper)
    assert (await client.get("/api/v1/audit-logs")).status_code == 403


async def test_built_in_roles_cannot_be_edited_by_anyone(client, world):
    await _as(client, world["owner"])
    roles = (await client.get("/api/v1/roles")).json()
    institute_admin = next(r for r in roles if r["key"] == "institute_admin")
    assert institute_admin["editable"] is False

    response = await client.patch(
        f"/api/v1/roles/{institute_admin['id']}", json={"name": "Renamed"}
    )
    assert response.status_code == 404


# ----------------------------------------------------------------------- the catalogue


async def test_the_permission_catalogue_is_grouped_and_complete(client, world):
    from app.modules.rbac.catalog import PERMISSIONS

    await _as(client, world["principal"])
    response = await client.get("/api/v1/permissions")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(PERMISSIONS)
    assert {p["group"] for p in body} >= {"Organisation", "People", "Access control"}


async def test_a_faculty_member_cannot_read_the_role_catalogue(client, world):
    """Faculty hold no `role:read`: understanding the platform's power structure is not
    part of teaching a class."""
    await _as(client, world["teacher"])
    assert (await client.get("/api/v1/roles")).status_code == 403
    assert (await client.get("/api/v1/permissions")).status_code == 403


async def test_my_access_describes_the_caller_without_needing_a_permission(client, world):
    await _as(client, world["teacher"])
    response = await client.get("/api/v1/me/access")
    assert response.status_code == 200
    body = response.json()

    assert [r["key"] for r in body["roles"]] == ["faculty"]
    assert body["granted_count"] < body["total_count"], "the boundary must be visible"
    granted = {p["key"] for p in body["permissions"] if p["granted"]}
    assert "class:read" in granted
    assert "institute:create" not in granted
    assert body["can_grant_roles"] == ["Student"]


async def test_my_access_marks_an_exception_as_an_exception(client, world):
    await _as(client, world["principal"])
    await client.post(
        f"/api/v1/users/{world['teacher'].id}/grants",
        json={
            "permission": "audit:read",
            "effect": "allow",
            "institute_id": str(world["abc"].id),
            "reason": "Covering for the branch head",
        },
    )

    await _as(client, world["teacher"])
    body = (await client.get("/api/v1/me/access")).json()
    audit_row = next(p for p in body["permissions"] if p["key"] == "audit:read")
    assert audit_row["granted"] is True
    assert audit_row["source"] == "direct", "an exception must not read as part of the role"
    assert len(body["direct_grants"]) == 1
    assert body["direct_grants"][0]["reason"] == "Covering for the branch head"


async def test_a_retired_role_keeps_its_name(client, world):
    """Reusing a retired role's key would make every past audit row ambiguous, so the name
    stays reserved — and the refusal has to say so, or it reads as a bug."""
    await _as(client, world["principal"])
    created = await client.post(
        "/api/v1/roles",
        json={
            "name": "Lab Assistant",
            "scope_level": "branch",
            "rank": 20,
            "institute_id": str(world["abc"].id),
            "permissions": ["class:read"],
        },
    )
    assert created.status_code == 201
    assert (await client.post(f"/api/v1/roles/{created.json()['id']}/archive")).status_code == 200

    again = await client.post(
        "/api/v1/roles",
        json={
            "name": "Lab Assistant",
            "scope_level": "branch",
            "rank": 20,
            "institute_id": str(world["abc"].id),
            "permissions": ["class:read"],
        },
    )
    assert again.status_code == 409
    assert "retired" in again.json()["error"]["message"].lower()


# --------------------------------------------------- platform roles are never invited


async def test_a_super_admin_cannot_be_created_by_invitation(client, world):
    """An invitation makes an account for an address nobody has proved they control. One
    typo in the email field would hand the whole platform to a stranger's mailbox, and the
    mistake stays invisible until it is used."""
    await _as(client, world["owner"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "New Owner",
            "email": "someone-elses-typo@example.com",
            "role_key": "super_admin",
        },
    )
    assert response.status_code == 422
    assert "cannot be given to a new invitation" in response.json()["error"]["message"]


async def test_a_platform_admin_cannot_be_created_by_invitation(client, world):
    await _as(client, world["owner"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "New Platform Admin",
            "email": "platform-typo@example.com",
            "role_key": "platform_admin",
        },
    )
    assert response.status_code == 422


async def test_an_existing_account_can_still_be_promoted_to_super_admin(client, world):
    """Succession must stay possible (PRD §3.1), or the first owner could never be
    replaced. Promotion acts on somebody who has already proved they can sign in."""
    await _as(client, world["owner"])
    response = await client.post(
        f"/api/v1/users/{world['principal'].id}/roles",
        json={"role_key": "super_admin"},
    )
    assert response.status_code == 201, response.text


async def test_the_invite_catalogue_hides_platform_roles(client, world):
    """The form must not offer a choice the service goes on to refuse."""
    await _as(client, world["owner"])

    for_assign = await client.get("/api/v1/users/roles/catalogue")
    for_invite = await client.get("/api/v1/users/roles/catalogue", params={"purpose": "invite"})
    assert for_assign.status_code == 200 and for_invite.status_code == 200

    assert "super_admin" in {r["key"] for r in for_assign.json()}
    invite_keys = {r["key"] for r in for_invite.json()}
    assert "super_admin" not in invite_keys
    assert "platform_admin" not in invite_keys
    assert "institute_admin" in invite_keys, "ordinary roles must still be invitable"


# ------------------------------------- per-institute adjustments to a built-in role


async def _customise(client, role_key, institute, permissions):
    roles = (await client.get("/api/v1/roles")).json()
    role = next(r for r in roles if r["key"] == role_key)
    return await client.put(
        f"/api/v1/roles/{role['id']}/institutes/{institute.id}/permissions",
        json={"permissions": permissions},
    )


async def test_an_institute_can_widen_a_built_in_role_for_itself(client, world, make_user):
    """The headline: ABC decides their Faculty may read the audit log. Faculty elsewhere
    are untouched, and the built-in definition is unchanged."""
    teacher = world["teacher"]
    await _as(client, teacher)
    assert (await client.get("/api/v1/audit-logs")).status_code == 403

    await _as(client, world["principal"])
    roles = (await client.get("/api/v1/roles")).json()
    faculty = next(r for r in roles if r["key"] == "faculty")
    assert faculty["customisable"] is True, "an institute admin may adjust Faculty"
    assert faculty["editable"] is False, "but not redefine the built-in itself"

    response = await _customise(
        client, "faculty", world["abc"], [*faculty["permissions"], "audit:read"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["customised_here"] is True
    assert "audit:read" in response.json()["permissions"]

    await _as(client, teacher)
    assert (await client.get("/api/v1/audit-logs")).status_code == 200


async def test_one_institute_s_change_does_not_reach_another(client, world, institute, make_user):
    """The property that makes this safe to offer at all."""
    xyz, xyz_branch = await institute("XYZ College", "XYZ", with_branch="CSE")
    their_teacher = await make_user("faculty", institute_id=xyz.id, branch_id=xyz_branch.id)

    await _as(client, world["principal"])
    roles = (await client.get("/api/v1/roles")).json()
    faculty = next(r for r in roles if r["key"] == "faculty")
    assert (
        await _customise(client, "faculty", world["abc"], [*faculty["permissions"], "audit:read"])
    ).status_code == 200

    await _as(client, their_teacher)
    assert (await client.get("/api/v1/audit-logs")).status_code == 403, (
        "ABC's decision leaked into XYZ"
    )


async def test_an_institute_can_narrow_a_built_in_role_for_itself(client, world):
    """Removal works as well as addition — Faculty here may no longer read people."""
    await _as(client, world["teacher"])
    assert (await client.get("/api/v1/users")).status_code == 200

    await _as(client, world["principal"])
    roles = (await client.get("/api/v1/roles")).json()
    faculty = next(r for r in roles if r["key"] == "faculty")
    kept = [p for p in faculty["permissions"] if p != "user:read"]
    assert (await _customise(client, "faculty", world["abc"], kept)).status_code == 200

    await _as(client, world["teacher"])
    assert (await client.get("/api/v1/users")).status_code == 403


async def test_restoring_the_definition_clears_the_customisation(client, world):
    await _as(client, world["principal"])
    roles = (await client.get("/api/v1/roles")).json()
    faculty = next(r for r in roles if r["key"] == "faculty")
    original = list(faculty["permissions"])

    await _customise(client, "faculty", world["abc"], [*original, "audit:read"])
    restored = await _customise(client, "faculty", world["abc"], original)
    assert restored.status_code == 200
    assert restored.json()["customised_here"] is False, "no rows should be left behind"


async def test_nobody_can_customise_a_role_at_or_above_their_own_level(client, world):
    """Otherwise an Institute Admin redefines Institute Admin and takes the institute."""
    await _as(client, world["principal"])
    roles = (await client.get("/api/v1/roles")).json()
    mine = next(r for r in roles if r["key"] == "institute_admin")
    assert mine["customisable"] is False

    response = await _customise(
        client, "institute_admin", world["abc"], [*mine["permissions"], "platform_admin:manage"]
    )
    assert response.status_code == 403


async def test_customising_cannot_add_a_permission_the_caller_lacks(client, world):
    """The subset rule, by this route too — closing one door and leaving the other open
    closes nothing."""
    await _as(client, world["principal"])
    roles = (await client.get("/api/v1/roles")).json()
    faculty = next(r for r in roles if r["key"] == "faculty")

    response = await _customise(
        client, "faculty", world["abc"], [*faculty["permissions"], "platform_admin:manage"]
    )
    assert response.status_code == 403


async def test_a_platform_role_cannot_be_customised_for_one_institute(client, world):
    """Super Admin belongs to no institute, so no institute's view of it could differ."""
    await _as(client, world["owner"])
    roles = (await client.get("/api/v1/roles")).json()
    super_admin = next(r for r in roles if r["key"] == "super_admin")
    assert super_admin["customisable"] is False

    response = await _customise(client, "super_admin", world["abc"], ["user:read"])
    assert response.status_code == 422


async def test_a_branch_admin_cannot_customise_roles(client, world):
    """`role:manage` is institute-level; a branch is not the right blast radius for a
    change that lands on everyone holding the role across the institute."""
    await _as(client, world["head"])
    roles = (await client.get("/api/v1/roles")).json()
    faculty = next(r for r in roles if r["key"] == "faculty")
    assert faculty["customisable"] is False

    response = await _customise(client, "faculty", world["abc"], ["class:read"])
    assert response.status_code == 403


async def test_an_outsider_cannot_customise_another_institute(client, world, institute, make_user):
    xyz, _branch = await institute("XYZ College", "XYZ", with_branch="CSE")
    outsider = await make_user("institute_admin", institute_id=xyz.id)

    await _as(client, outsider)
    response = await _customise(client, "faculty", world["abc"], ["class:read"])
    assert response.status_code == 403


async def test_the_change_takes_effect_without_waiting_out_the_cache(client, world):
    """A permission removed from a role is usually removed because it is being misused."""
    await _as(client, world["teacher"])
    assert (await client.get("/api/v1/users")).status_code == 200

    await _as(client, world["principal"])
    roles = (await client.get("/api/v1/roles")).json()
    faculty = next(r for r in roles if r["key"] == "faculty")
    await _customise(
        client, "faculty", world["abc"], [p for p in faculty["permissions"] if p != "user:read"]
    )

    # No re-login, no cache expiry: the next request must already see it.
    await _as(client, world["teacher"])
    assert (await client.get("/api/v1/users")).status_code == 403


# ----------------------------------------------------- the matrix, as the client asked


async def test_a_system_role_is_read_only_for_everyone(client, world):
    """Including a Super Admin. A built-in role is what its name means on every
    installation of this product; a version of "Institute Admin" that varies per customer
    cannot be documented, supported, or reasoned about in a security review."""
    await _as(client, world["owner"])
    roles = (await client.get("/api/v1/roles")).json()

    for row in roles:
        if row["is_system"]:
            assert row["editable"] is False, f"{row['key']} reported itself editable"

    faculty = next(r for r in roles if r["key"] == "faculty")
    refused = await client.patch(
        f"/api/v1/roles/{faculty['id']}",
        json={"permissions": [*faculty["permissions"], "audit:read"]},
    )
    assert refused.status_code == 404


async def test_a_custom_role_grants_exactly_what_it_was_given(client, world, make_user):
    """The whole point of a custom role: the holder gets that set and nothing else."""
    await _as(client, world["principal"])
    created = await client.post(
        "/api/v1/roles",
        json={
            "name": "Exam Clerk",
            "scope_level": "branch",
            "rank": 15,
            "institute_id": str(world["abc"].id),
            "permissions": ["class:read", "profile:read", "profile:update"],
        },
    )
    assert created.status_code == 201, created.text

    clerk = await make_user("student", institute_id=world["abc"].id)
    assigned = await client.post(
        f"/api/v1/users/{clerk.id}/roles",
        json={
            "role_key": created.json()["key"],
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
        },
    )
    assert assigned.status_code == 201, assigned.text

    await _as(client, clerk)
    held = set((await client.get("/api/v1/me")).json()["permissions"])

    # The student role they already had contributes its own permissions, so the test is
    # that nothing *beyond* the two sets appeared — not that the sets are equal.
    assert {"class:read", "profile:read", "profile:update"} <= held
    assert "user:update_status" not in held
    assert "role:manage" not in held
    assert "audit:read" not in held


async def test_toggling_a_permission_onto_a_custom_role_reaches_its_holders(
    client, world, make_user
):
    """What the matrix does when a cell is clicked, and the cache invalidation behind it."""
    await _as(client, world["principal"])
    created = await client.post(
        "/api/v1/roles",
        json={
            "name": "Exam Clerk",
            "scope_level": "branch",
            "rank": 15,
            "institute_id": str(world["abc"].id),
            "permissions": ["class:read"],
        },
    )
    role = created.json()

    clerk = await make_user("student", institute_id=world["abc"].id)
    await client.post(
        f"/api/v1/users/{clerk.id}/roles",
        json={
            "role_key": role["key"],
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
        },
    )

    await _as(client, clerk)
    assert "audit:read" not in (await client.get("/api/v1/me")).json()["permissions"]

    await _as(client, world["principal"])
    updated = await client.patch(
        f"/api/v1/roles/{role['id']}", json={"permissions": ["class:read", "audit:read"]}
    )
    assert updated.status_code == 200, updated.text

    # No re-login and no cache expiry: the holder sees it on their next request.
    await _as(client, clerk)
    assert "audit:read" in (await client.get("/api/v1/me")).json()["permissions"]


async def test_a_custom_role_cannot_be_created_at_or_above_your_own_rank(client, world):
    await _as(client, world["principal"])
    mine = 70  # Institute Admin
    for rank in (mine, mine + 1):
        response = await client.post(
            "/api/v1/roles",
            json={
                "name": f"Overreach {rank}",
                "scope_level": "institute",
                "rank": rank,
                "institute_id": str(world["abc"].id),
                "permissions": ["user:read"],
            },
        )
        assert response.status_code == 403, f"rank {rank} should be refused"


# ------------------------------------ the holes the review found, each with its repro


async def test_a_narrower_deny_still_blocks_the_status_endpoints(client, world, make_user):
    """The deny layer has to reach every endpoint, not only the list ones.

    The subtle case is a deny *narrower* than the grant: an institute-wide `user:update_status`
    with a block on one branch. `holds()` stays true, so the permission dependency lets the
    request through, and anything that does not re-check at the target scope silently acts.
    """
    victim = await make_user("faculty", institute_id=world["abc"].id, branch_id=world["mca"].id)

    await _as(client, world["owner"])
    blocked = await client.post(
        f"/api/v1/users/{world['principal'].id}/grants",
        json={
            "permission": "user:update_status",
            "effect": "deny",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["mca"].id),
            "reason": "Blocked from acting in MCA",
        },
    )
    assert blocked.status_code == 201, blocked.text

    await _as(client, world["principal"])
    single = await client.patch(f"/api/v1/users/{victim.id}/status", json={"status": "suspended"})
    assert single.status_code in (403, 404), "a block on the branch must stop the single endpoint"

    bulk = await client.post(
        "/api/v1/users/bulk-status",
        json={"user_ids": [str(victim.id)], "status": "suspended"},
    )
    assert bulk.json()["succeeded"] == 0, "the same block must stop the bulk endpoint"
    assert bulk.json()["skipped"] == 1


async def test_another_institutes_role_view_is_not_readable(client, world, institute, make_user):
    """`role:read` is held somewhere, not everywhere. Asking for another institute's view
    would disclose which permissions they have deliberately added or removed."""
    xyz, _branch = await institute("XYZ College", "XYZ", with_branch="CSE")

    await _as(client, world["principal"])
    response = await client.get("/api/v1/roles", params={"institute_id": str(xyz.id)})
    assert response.status_code == 404

    # Their own institute still works, and so does omitting the parameter entirely.
    assert (
        await client.get("/api/v1/roles", params={"institute_id": str(world["abc"].id)})
    ).status_code == 200
    assert (await client.get("/api/v1/roles")).status_code == 200


async def test_platform_staff_may_still_look_at_any_institute(client, world, institute):
    xyz, _branch = await institute("XYZ College", "XYZ", with_branch="CSE")
    await _as(client, world["owner"])
    assert (
        await client.get("/api/v1/roles", params={"institute_id": str(xyz.id)})
    ).status_code == 200


async def test_an_invited_account_cannot_be_promoted_to_a_platform_role(client, world):
    """Refusing platform roles on `invite` is decorative if the same account can be invited
    as a Student and promoted a second later — the address is still unproven, and whoever
    reads that mailbox completes the setup and owns the platform."""
    await _as(client, world["owner"])
    invited = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "Typo Victim",
            "email": "typo@nobody-owns-this.example",
            "role_key": "student",
            "institute_id": str(world["abc"].id),
        },
    )
    assert invited.status_code == 201
    victim = invited.json()["user"]
    assert victim["status"] == "invited"

    promoted = await client.post(
        f"/api/v1/users/{victim['id']}/roles", json={"role_key": "super_admin"}
    )
    assert promoted.status_code == 422
    assert "already active" in promoted.json()["error"]["message"]


async def test_an_active_account_can_still_be_promoted(client, world):
    """The restriction is about proving the address, not about blocking succession."""
    await _as(client, world["owner"])
    promoted = await client.post(
        f"/api/v1/users/{world['principal'].id}/roles", json={"role_key": "super_admin"}
    )
    assert promoted.status_code == 201, promoted.text


async def test_only_a_super_admin_may_appoint_platform_admins(client, world, make_user):
    """`platform_admin:manage` gates something now. It was in the catalogue, granted to
    Super Admin and shown in the matrix — and checked nowhere; what actually stopped a
    Platform Admin minting another was the rank ceiling, a different rule that happens to
    have the same effect. A permission nobody enforces is worse than one that does not
    exist."""
    platform_admin = await make_user("platform_admin")
    target = world["principal"]

    await _as(client, platform_admin)
    refused = await client.post(
        f"/api/v1/users/{target.id}/roles", json={"role_key": "platform_admin"}
    )
    assert refused.status_code == 403

    await _as(client, world["owner"])
    allowed = await client.post(
        f"/api/v1/users/{target.id}/roles", json={"role_key": "platform_admin"}
    )
    assert allowed.status_code == 201, allowed.text
