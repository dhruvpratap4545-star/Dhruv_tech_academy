"""The organisation level, end to end.

One administrator running four colleges is the whole reason this level exists. These tests
are written around the two ways that can go wrong: reaching too far, and not far enough.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _as(client: AsyncClient, user) -> AsyncClient:
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text
    return client


async def _codes(client: AsyncClient) -> set[str]:
    listed = await client.get("/api/v1/institutes", params={"limit": 50})
    assert listed.status_code == 200, listed.text
    return {row["code"] for row in listed.json()["items"]}


# ------------------------------------------------------------------ reach, and its limits


async def test_an_organisation_admin_sees_every_institute_in_their_organisation(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1", "JSPM2", "JSPM3"))
    admin = await make_user("org_admin", organisation_id=jspm.id)

    await _as(client, admin)
    assert await _codes(client) == {"JSPM1", "JSPM2", "JSPM3"}


async def test_an_organisation_admin_cannot_see_another_organisation(
    client: AsyncClient, organisation, make_user
) -> None:
    """The isolation that makes the level safe to hand out."""
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1", "JSPM2"))
    mit, theirs = await organisation("MIT", "MIT", institutes=("MIT1",))
    admin = await make_user("org_admin", organisation_id=jspm.id)

    await _as(client, admin)
    assert "MIT1" not in await _codes(client)

    # And the detail endpoints agree with the list, rather than confirming it exists.
    assert (await client.get(f"/api/v1/institutes/{theirs[0].id}")).status_code == 404
    assert (await client.get(f"/api/v1/organisations/{mit.id}")).status_code == 404


async def test_a_standalone_institute_belongs_to_nobody(
    client: AsyncClient, organisation, make_user, institute
) -> None:
    """An institute with no organisation must not fall into one by accident.

    The case the scope arithmetic is most likely to get wrong: a standalone institute and
    an organisation-scoped grant both leave a column null.
    """
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    alone, _ = await institute("Lone Coaching", "LONE1")
    admin = await make_user("org_admin", organisation_id=jspm.id)

    await _as(client, admin)
    assert await _codes(client) == {"JSPM1"}
    assert (await client.get(f"/api/v1/institutes/{alone.id}")).status_code == 404


async def test_an_organisation_admin_sees_the_people_in_their_colleges(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, colleges = await organisation("JSPM", "JSPM", institutes=("JSPM1", "JSPM2"))
    _, mit_colleges = await organisation("MIT", "MIT", institutes=("MIT1",))

    mine_a = await make_user("student", institute_id=colleges[0].id, email="a@jspm.example")
    mine_b = await make_user("student", institute_id=colleges[1].id, email="b@jspm.example")
    theirs = await make_user("student", institute_id=mit_colleges[0].id, email="c@mit.example")

    admin = await make_user("org_admin", organisation_id=jspm.id)
    await _as(client, admin)

    listed = await client.get("/api/v1/users", params={"limit": 100})
    assert listed.status_code == 200, listed.text
    emails = {row["email"] for row in listed.json()["items"]}

    assert mine_a.email in emails
    assert mine_b.email in emails, "a second college in the same organisation is still theirs"
    assert theirs.email not in emails

    # The dashboard counts the same people the list shows.
    overview = await client.get("/api/v1/me/overview")
    assert overview.status_code == 200, overview.text
    assert overview.json()["users_total"] == listed.json()["total"]


async def test_a_deny_on_one_college_narrows_the_organisation_grant(
    client: AsyncClient, organisation, make_user
) -> None:
    """A denial written at institute level has to reach a grant written at organisation
    level. That only works because every scope carries its organisation."""
    jspm, colleges = await organisation("JSPM", "JSPM", institutes=("JSPM1", "JSPM2"))
    admin = await make_user("org_admin", organisation_id=jspm.id)
    owner = await make_user("super_admin")

    await _as(client, admin)
    assert await _codes(client) == {"JSPM1", "JSPM2"}

    await _as(client, owner)
    blocked = await client.post(
        f"/api/v1/users/{admin.id}/grants",
        json={
            "permission": "institute:read",
            "effect": "deny",
            "institute_id": str(colleges[0].id),
            "reason": "Under review",
        },
    )
    assert blocked.status_code == 201, blocked.text

    await _as(client, admin)
    # The wide grant is dropped entirely rather than narrowed — the documented safe
    # direction, and the same behaviour a branch-level deny already produces.
    assert "JSPM1" not in await _codes(client)


# -------------------------------------------------------------------- granting the role


async def test_the_role_must_be_given_across_a_whole_organisation(
    client: AsyncClient, organisation, make_user
) -> None:
    """Not above it and not below it.

    Above would hand the holder every organisation. Below would make "Organisation Admin"
    the name of somebody who administers one college, which is what Institute Admin is for.
    """
    jspm, colleges = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    owner = await make_user("super_admin")
    target = await make_user("student", institute_id=colleges[0].id)

    await _as(client, owner)

    pinned = await client.post(
        f"/api/v1/users/{target.id}/roles",
        json={"role_key": "org_admin", "institute_id": str(colleges[0].id)},
    )
    assert pinned.status_code == 422, pinned.text
    assert "whole organisation" in pinned.json()["error"]["message"]

    platformwide = await client.post(
        f"/api/v1/users/{target.id}/roles", json={"role_key": "org_admin"}
    )
    assert platformwide.status_code == 422, platformwide.text

    correct = await client.post(
        f"/api/v1/users/{target.id}/roles",
        json={"role_key": "org_admin", "organisation_id": str(jspm.id)},
    )
    assert correct.status_code == 201, correct.text


async def test_an_organisation_admin_cannot_appoint_a_peer(
    client: AsyncClient, organisation, make_user
) -> None:
    """The rank rule applies at the new level like every other."""
    jspm, colleges = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    admin = await make_user("org_admin", organisation_id=jspm.id)
    colleague = await make_user("institute_admin", institute_id=colleges[0].id)

    await _as(client, admin)
    refused = await client.post(
        f"/api/v1/users/{colleague.id}/roles",
        json={"role_key": "org_admin", "organisation_id": str(jspm.id)},
    )
    assert refused.status_code == 403, refused.text
    assert "at or above your own level" in refused.json()["error"]["message"]


# ----------------------------------------------------------------- the organisation itself


async def test_only_platform_staff_create_an_organisation(
    client: AsyncClient, organisation, make_user
) -> None:
    """Creating a *new* organisation decides who else exists on the platform."""
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    admin = await make_user("org_admin", organisation_id=jspm.id)

    await _as(client, admin)
    refused = await client.post(
        "/api/v1/organisations", json={"name": "Another Group", "code": "ANOTHER"}
    )
    assert refused.status_code == 403, refused.text

    await _as(client, await make_user("super_admin"))
    allowed = await client.post(
        "/api/v1/organisations", json={"name": "Another Group", "code": "ANOTHER"}
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["institute_count"] == 0


async def test_an_organisation_with_institutes_cannot_be_archived(
    client: AsyncClient, organisation, make_user
) -> None:
    """Archiving it would leave the colleges pointing at something retired, and nobody
    would find out until somebody could not sign in."""
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1", "JSPM2"))
    await _as(client, await make_user("super_admin"))

    refused = await client.post(f"/api/v1/organisations/{jspm.id}/archive")
    assert refused.status_code == 409, refused.text
    assert "2 institutes belong" in refused.json()["error"]["message"]


async def test_an_empty_organisation_can_be_archived(
    client: AsyncClient, organisation, make_user
) -> None:
    empty, _ = await organisation("Dormant", "DORMANT")
    await _as(client, await make_user("super_admin"))

    archived = await client.post(f"/api/v1/organisations/{empty.id}/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"


async def test_an_organisation_admin_may_edit_their_own_and_no_other(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    mit, _ = await organisation("MIT", "MIT", institutes=("MIT1",))
    admin = await make_user("org_admin", organisation_id=jspm.id)

    await _as(client, admin)
    mine = await client.patch(
        f"/api/v1/organisations/{jspm.id}", json={"name": "JSPM Group of Institutes"}
    )
    assert mine.status_code == 200, mine.text
    assert mine.json()["name"] == "JSPM Group of Institutes"

    theirs = await client.patch(f"/api/v1/organisations/{mit.id}", json={"name": "Taken Over"})
    assert theirs.status_code == 404, theirs.text


async def test_the_list_shows_only_organisations_you_belong_to(
    client: AsyncClient, organisation, make_user
) -> None:
    jspm, _ = await organisation("JSPM", "JSPM", institutes=("JSPM1",))
    await organisation("MIT", "MIT", institutes=("MIT1",))
    admin = await make_user("org_admin", organisation_id=jspm.id)

    await _as(client, admin)
    listed = await client.get("/api/v1/organisations", params={"limit": 50})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert {row["code"] for row in body["items"]} == {"JSPM"}
    assert body["items"][0]["institute_count"] == 1

    # Platform staff see both.
    await _as(client, await make_user("super_admin"))
    everything = await client.get("/api/v1/organisations", params={"limit": 50})
    assert {row["code"] for row in everything.json()["items"]} >= {"JSPM", "MIT"}
