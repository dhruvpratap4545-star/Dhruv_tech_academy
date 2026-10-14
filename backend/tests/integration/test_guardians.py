"""Parent login, and the link that confines it.

The Parent role carries ``user:read`` across the institute their child attends. On its own
that means "may read every child in the school", which is the opposite of what the word
parent means. The guardian row is what narrows it, and these tests are mostly about that
narrowing holding in every place a person can be read.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

PASSWORD = "Jacaranda!Tide4"


async def _as(client: AsyncClient, user) -> AsyncClient:
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def family(institute, make_user):
    """A college with two unrelated learners, and the administrator who runs it."""

    async def _make():
        college, branch = await institute("Vidya College", "VIDYA1", with_branch="Science")
        return {
            "college": college,
            "branch": branch,
            "principal": await make_user("institute_admin", institute_id=college.id),
            "mine": await make_user("student", institute_id=college.id, email="riya@vidya.example"),
            "theirs": await make_user(
                "student", institute_id=college.id, email="arun@vidya.example"
            ),
        }

    return _make


# --------------------------------------------------------------------------- linking


async def test_attaching_a_new_guardian_invites_them(client: AsyncClient, family) -> None:
    world = await family()
    await _as(client, world["principal"])

    linked = await client.post(
        f"/api/v1/users/{world['mine'].id}/guardians",
        json={
            "email": "meera@parent.example",
            "full_name": "Meera Sharma",
            "relationship": "Mother",
            "is_primary": True,
        },
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["email"] == "meera@parent.example"
    assert linked.json()["status"] == "invited"

    listed = await client.get(f"/api/v1/users/{world['mine'].id}/guardians")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert len(body) == 1
    assert body[0]["relationship"] == "Mother"
    assert body[0]["is_primary"] is True
    # Not verified until the adult completes setup at their own address. Until then the
    # consent the row records is asserted by the school, not demonstrated by the parent.
    assert body[0]["verified_at"] is None


async def test_a_parent_with_two_children_keeps_one_account(client: AsyncClient, family) -> None:
    """The reason the adult is named by email rather than chosen from a list."""
    world = await family()
    await _as(client, world["principal"])

    first = await client.post(
        f"/api/v1/users/{world['mine'].id}/guardians",
        json={"email": "meera@parent.example", "full_name": "Meera Sharma"},
    )
    second = await client.post(
        f"/api/v1/users/{world['theirs'].id}/guardians",
        json={"email": "meera@parent.example"},
    )
    assert first.status_code == 201 and second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"], "one person is one account"


async def test_the_same_guardian_cannot_be_attached_twice(client: AsyncClient, family) -> None:
    world = await family()
    await _as(client, world["principal"])

    payload = {"email": "meera@parent.example", "full_name": "Meera Sharma"}
    assert (
        await client.post(f"/api/v1/users/{world['mine'].id}/guardians", json=payload)
    ).status_code == 201

    again = await client.post(f"/api/v1/users/{world['mine'].id}/guardians", json=payload)
    assert again.status_code == 409, again.text
    assert "already recorded" in again.json()["error"]["message"]


async def test_a_learner_cannot_be_their_own_guardian(client: AsyncClient, family) -> None:
    """Refused in the application and again by a check constraint, because a self-link
    would let a student read themselves as a parent and collect a second set of
    permissions."""
    world = await family()
    await _as(client, world["principal"])

    refused = await client.post(
        f"/api/v1/users/{world['mine'].id}/guardians", json={"email": world["mine"].email}
    )
    assert refused.status_code == 422, refused.text
    assert "own guardian" in refused.json()["error"]["message"]


async def test_removing_a_link_leaves_the_account_alone(client: AsyncClient, family) -> None:
    world = await family()
    await _as(client, world["principal"])

    created = await client.post(
        f"/api/v1/users/{world['mine'].id}/guardians",
        json={"email": "meera@parent.example", "full_name": "Meera Sharma"},
    )
    parent_id = created.json()["id"]

    removed = await client.request(
        "DELETE", f"/api/v1/users/{world['mine'].id}/guardians/{parent_id}"
    )
    assert removed.status_code == 204, removed.text
    assert (await client.get(f"/api/v1/users/{world['mine'].id}/guardians")).json() == []

    # The person still exists — they may be responsible for other learners.
    assert (await client.get(f"/api/v1/users/{parent_id}")).status_code == 200


# ----------------------------------------------------------- what a parent can then see


async def _parent_of(client: AsyncClient, world, email: str = "meera@parent.example"):
    """Attach a guardian to the first learner and return their user id."""
    await _as(client, world["principal"])
    created = await client.post(
        f"/api/v1/users/{world['mine'].id}/guardians",
        json={"email": email, "full_name": "Meera Sharma", "relationship": "Mother"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_a_parent_sees_their_own_child_and_no_other(client: AsyncClient, family, db) -> None:
    """The narrowing, in the list."""
    from app.core.security import hash_password
    from app.modules.users.models import User

    world = await family()
    parent_id = await _parent_of(client, world)

    parent = await db.get(User, __import__("uuid").UUID(parent_id))
    parent.password_hash = hash_password(PASSWORD)
    parent.status = "active"
    await db.commit()

    await _as(client, parent)
    listed = await client.get("/api/v1/users", params={"limit": 100})
    assert listed.status_code == 200, listed.text
    emails = {row["email"] for row in listed.json()["items"]}

    assert world["mine"].email in emails
    assert world["theirs"].email not in emails, "another family's child must not appear"
    # Their own row is theirs to see.
    assert parent.email in emails


async def test_a_parent_cannot_open_another_familys_child_by_id(
    client: AsyncClient, family, db
) -> None:
    """The same narrowing, in the detail endpoint.

    This is the one that matters most. Scope alone would allow it — the role carries
    `user:read` across the whole institute — so the list and the detail endpoint would
    disagree, and the disagreement would be a parent reading somebody else's child.
    """
    import uuid as uuid_module

    from app.core.security import hash_password
    from app.modules.users.models import User

    world = await family()
    parent_id = await _parent_of(client, world)

    parent = await db.get(User, uuid_module.UUID(parent_id))
    parent.password_hash = hash_password(PASSWORD)
    parent.status = "active"
    await db.commit()

    await _as(client, parent)
    assert (await client.get(f"/api/v1/users/{world['mine'].id}")).status_code == 200
    assert (await client.get(f"/api/v1/users/{world['theirs'].id}")).status_code == 404


async def test_a_parent_sees_their_children_on_their_own_screen(
    client: AsyncClient, family, db
) -> None:
    import uuid as uuid_module

    from app.core.security import hash_password
    from app.modules.users.models import User

    world = await family()
    parent_id = await _parent_of(client, world)

    parent = await db.get(User, uuid_module.UUID(parent_id))
    parent.password_hash = hash_password(PASSWORD)
    parent.status = "active"
    await db.commit()

    await _as(client, parent)
    children = await client.get("/api/v1/me/children")
    assert children.status_code == 200, children.text
    body = children.json()
    assert len(body) == 1
    assert body[0]["full_name"] == world["mine"].full_name
    assert body[0]["relationship"] == "Mother"


async def test_everybody_else_has_no_children(client: AsyncClient, family) -> None:
    """The endpoint needs no permission because it is about the caller. It has to be
    empty, not forbidden, for somebody who is not a parent."""
    world = await family()
    await _as(client, world["principal"])
    response = await client.get("/api/v1/me/children")
    assert response.status_code == 200
    assert response.json() == []


async def test_the_dashboard_counts_what_the_parent_can_see(
    client: AsyncClient, family, db
) -> None:
    import uuid as uuid_module

    from app.core.security import hash_password
    from app.modules.users.models import User

    world = await family()
    parent_id = await _parent_of(client, world)

    parent = await db.get(User, uuid_module.UUID(parent_id))
    parent.password_hash = hash_password(PASSWORD)
    parent.status = "active"
    await db.commit()

    await _as(client, parent)
    listed = await client.get("/api/v1/users", params={"limit": 100})
    overview = await client.get("/api/v1/me/overview")
    assert overview.status_code == 200, overview.text
    assert overview.json()["users_total"] == listed.json()["total"]


async def test_completing_setup_records_the_consent_as_verified(
    client: AsyncClient, family, db
) -> None:
    """The DPDP point. "The school says this is the parent" becomes "the parent answered
    at their own address" only when they complete setup."""
    import uuid as uuid_module

    from sqlalchemy import select

    from app.modules.users.models import Guardian

    world = await family()
    parent_id = await _parent_of(client, world)

    link = await db.scalar(
        select(Guardian).where(Guardian.parent_user_id == uuid_module.UUID(parent_id))
    )
    assert link.verified_at is None

    # Only the hash of a code is stored, so the plaintext the invitation emailed cannot be
    # read back. Issue a fresh one through the same service the invitation used — what is
    # under test is what *completing* setup does, not how the code travelled.
    from app.modules.auth import service as auth_service
    from app.modules.auth.service import PURPOSE_SETUP, RequestMeta
    from app.modules.users.models import User

    parent = await db.get(User, uuid_module.UUID(parent_id))
    _, code = await auth_service.issue_otp(
        db, user=parent, purpose=PURPOSE_SETUP, meta=RequestMeta(ip=None, user_agent=None)
    )
    await db.commit()

    done = await client.post(
        "/api/v1/auth/password/setup",
        json={"email": parent.email, "code": code, "new_password": "Kestrel#Bay74"},
    )
    assert done.status_code == 200, done.text

    await db.refresh(link)
    assert link.verified_at is not None
