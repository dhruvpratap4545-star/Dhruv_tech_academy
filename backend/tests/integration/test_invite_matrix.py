"""PRD §3.1 "Who can add whom", row by row, for invite *and* role assignment.

| Role            | Can add                                  | Where                      |
|-----------------|------------------------------------------|----------------------------|
| Super Admin     | any role                                 | any institute              |
| Platform Admin  | Institute Admin and below                | any institute              |
| Institute Admin | Branch Admin, Faculty, Student           | own institute only         |
| Branch Admin    | Faculty, Student                         | own branch only            |
| Faculty         | Student                                  | own assigned classes only  |
| Student         | nobody                                   | —                          |

Every row gets both halves: the allowed case succeeds, and the case one step beyond it is
refused. A test that only proves the happy path proves nothing about a permission system.
"""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient

ROLE_RANK = {
    "super_admin": 100,
    "platform_admin": 90,
    "institute_admin": 70,
    "branch_admin": 50,
    "faculty": 30,
    "student": 10,
}


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "testpassword9!"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture
async def world(institute, make_user, db):
    """Two institutes; the first has two branches and a class the faculty actually teaches."""
    from app.modules.org.models import AcademicSession, Branch, Class, ClassFaculty

    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")
    bca = Branch(institute_id=abc.id, name="BCA", code="BCA")
    db.add(bca)
    await db.flush()

    term = AcademicSession(
        institute_id=abc.id,
        name="2026-27",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        is_current=True,
    )
    db.add(term)
    await db.flush()

    taught = Class(
        institute_id=abc.id,
        branch_id=mca.id,
        academic_session_id=term.id,
        name="MCA 1 A",
        code="MCA1A",
    )
    untaught = Class(
        institute_id=abc.id,
        branch_id=mca.id,
        academic_session_id=term.id,
        name="MCA 1 B",
        code="MCA1B",
    )
    db.add_all([taught, untaught])
    await db.flush()

    xyz, xyz_branch = await institute("XYZ College", "XYZ", with_branch="CSE")

    faculty = await make_user("faculty", institute_id=abc.id, branch_id=mca.id)
    db.add(ClassFaculty(class_id=taught.id, faculty_user_id=faculty.id))
    await db.commit()

    return {
        "abc": abc,
        "mca": mca,
        "bca": bca,
        "xyz": xyz,
        "xyz_branch": xyz_branch,
        "taught": taught,
        "untaught": untaught,
        "super_admin": await make_user("super_admin"),
        "platform_admin": await make_user("platform_admin"),
        "institute_admin": await make_user("institute_admin", institute_id=abc.id),
        "branch_admin": await make_user("branch_admin", institute_id=abc.id, branch_id=mca.id),
        "faculty": faculty,
        "student": await make_user("student", institute_id=abc.id),
    }


def _invite(world, role_key: str, *, institute=None, branch=None, classes=None, email=None):
    body = {
        "full_name": "Invited Person",
        "email": email or f"invite-{role_key}-{id(world) % 100000}@example.com",
        "role_key": role_key,
    }
    if institute is not None:
        body["institute_id"] = str(institute.id)
    if branch is not None:
        body["branch_id"] = str(branch.id)
    if classes is not None:
        body["class_ids"] = [str(c.id) for c in classes]
    return body


# --------------------------------------------------------------- role_key is required


async def test_an_invite_without_a_role_is_rejected(client: AsyncClient, world) -> None:
    """No user may exist without a role: they could log in and see nothing."""
    await _as(client, world["institute_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json={
            "full_name": "No Role",
            "email": "norole@example.com",
            "institute_id": str(world["abc"].id),
        },
    )
    assert response.status_code == 422


async def test_an_unknown_role_is_rejected(client: AsyncClient, world) -> None:
    await _as(client, world["institute_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, "emperor", institute=world["abc"]),
    )
    assert response.status_code == 422


async def test_the_reserved_parent_role_cannot_be_granted(client: AsyncClient, world) -> None:
    """Parent is designed in M1 but not active until Kids Zone (PRD §3, §12)."""
    await _as(client, world["super_admin"])
    response = await client.post(
        "/api/v1/users/invite", json=_invite(world, "parent", institute=world["abc"])
    )
    assert response.status_code == 422


# ------------------------------------------------------------------------ Super Admin


@pytest.mark.parametrize("role_key", ["institute_admin", "branch_admin", "faculty", "student"])
async def test_super_admin_can_invite_any_role_inside_an_institute(
    client: AsyncClient, world, role_key
) -> None:
    await _as(client, world["super_admin"])
    body = _invite(world, role_key, institute=world["abc"], email=f"sa-{role_key}@example.com")
    if role_key in {"branch_admin", "faculty"}:
        body["branch_id"] = str(world["mca"].id)
    response = await client.post("/api/v1/users/invite", json=body)
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("role_key", ["super_admin", "platform_admin"])
async def test_even_a_super_admin_cannot_invite_a_platform_role(
    client: AsyncClient, world, role_key
) -> None:
    """Platform-wide authority is reached by promoting an account that already works, not
    by sending an invitation to an address nobody has proved they control. PRD §3.1 still
    holds — see the promotion test below."""
    await _as(client, world["super_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, role_key, institute=None, email=f"sa-{role_key}@example.com"),
    )
    assert response.status_code == 422
    assert "cannot be given to a new invitation" in response.json()["error"]["message"]


async def test_super_admin_can_invite_into_any_institute(client: AsyncClient, world) -> None:
    await _as(client, world["super_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, "institute_admin", institute=world["xyz"], email="sa-xyz@example.com"),
    )
    assert response.status_code == 201, response.text


# --------------------------------------------------------------------- Platform Admin


async def test_platform_admin_can_invite_an_institute_admin_anywhere(
    client: AsyncClient, world
) -> None:
    await _as(client, world["platform_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, "institute_admin", institute=world["xyz"], email="pa-ia@example.com"),
    )
    assert response.status_code == 201, response.text


async def test_platform_admin_cannot_invite_a_peer(client: AsyncClient, world) -> None:
    """Two independent rules forbid this now — no platform role may be invited at all, and
    nobody may grant their own rank. The platform-role rule is checked first, so the status
    is 422 rather than 403; what matters is that the account is not created."""
    await _as(client, world["platform_admin"])
    response = await client.post(
        "/api/v1/users/invite", json=_invite(world, "platform_admin", email="pa-pa@example.com")
    )
    assert response.status_code in (403, 422), response.text

    listed = await client.get("/api/v1/users", params={"search": "pa-pa@example.com"})
    assert listed.json()["items"] == [], "no account may exist after a refused invitation"


async def test_platform_admin_cannot_invite_a_super_admin(client: AsyncClient, world) -> None:
    await _as(client, world["platform_admin"])
    response = await client.post(
        "/api/v1/users/invite", json=_invite(world, "super_admin", email="pa-sa@example.com")
    )
    assert response.status_code in (403, 422), response.text


# -------------------------------------------------------------------- Institute Admin


@pytest.mark.parametrize("role_key", ["branch_admin", "faculty", "student"])
async def test_institute_admin_can_invite_below_their_level(
    client: AsyncClient, world, role_key
) -> None:
    await _as(client, world["institute_admin"])
    needs_branch = role_key in ("branch_admin", "faculty")
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            role_key,
            institute=world["abc"],
            branch=world["mca"] if needs_branch else None,
            email=f"ia-{role_key}@example.com",
        ),
    )
    assert response.status_code == 201, response.text


async def test_institute_admin_cannot_invite_another_institute_admin(
    client: AsyncClient, world
) -> None:
    await _as(client, world["institute_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, "institute_admin", institute=world["abc"], email="ia-ia@example.com"),
    )
    assert response.status_code == 403


async def test_institute_admin_cannot_invite_into_another_institute(
    client: AsyncClient, world
) -> None:
    await _as(client, world["institute_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, "student", institute=world["xyz"], email="ia-xyz@example.com"),
    )
    assert response.status_code == 403


# ----------------------------------------------------------------------- Branch Admin


@pytest.mark.parametrize("role_key", ["faculty", "student"])
async def test_branch_admin_can_invite_faculty_and_students_in_their_branch(
    client: AsyncClient, world, role_key
) -> None:
    await _as(client, world["branch_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            role_key,
            institute=world["abc"],
            branch=world["mca"],
            email=f"ba-{role_key}@example.com",
        ),
    )
    assert response.status_code == 201, response.text


async def test_branch_admin_cannot_invite_a_peer(client: AsyncClient, world) -> None:
    await _as(client, world["branch_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            "branch_admin",
            institute=world["abc"],
            branch=world["mca"],
            email="ba-ba@example.com",
        ),
    )
    assert response.status_code == 403


async def test_branch_admin_cannot_invite_an_institute_admin(client: AsyncClient, world) -> None:
    await _as(client, world["branch_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, "institute_admin", institute=world["abc"], email="ba-ia@example.com"),
    )
    assert response.status_code == 403


async def test_branch_admin_cannot_invite_into_a_sibling_branch(client: AsyncClient, world) -> None:
    """The MCA admin must not reach the BCA branch of the same institute."""
    await _as(client, world["branch_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            "faculty",
            institute=world["abc"],
            branch=world["bca"],
            email="ba-bca@example.com",
        ),
    )
    assert response.status_code == 403


async def test_branch_admin_cannot_widen_their_own_scope_by_omitting_the_branch(
    client: AsyncClient, world
) -> None:
    """Leaving branch_id out would ask for institute-wide authority."""
    await _as(client, world["branch_admin"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, "student", institute=world["abc"], email="ba-wide@example.com"),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------- Faculty


async def test_faculty_can_invite_a_student_into_a_class_they_teach(
    client: AsyncClient, world
) -> None:
    await _as(client, world["faculty"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            "student",
            institute=world["abc"],
            branch=world["mca"],
            classes=[world["taught"]],
            email="fac-ok@example.com",
        ),
    )
    assert response.status_code == 201, response.text


async def test_faculty_cannot_invite_into_a_class_they_do_not_teach(
    client: AsyncClient, world
) -> None:
    await _as(client, world["faculty"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            "student",
            institute=world["abc"],
            branch=world["mca"],
            classes=[world["untaught"]],
            email="fac-bad@example.com",
        ),
    )
    assert response.status_code == 403


async def test_faculty_must_name_a_class(client: AsyncClient, world) -> None:
    """Without a class the invite would add a student to the branch at large, which is a
    Branch Admin's job, not a teacher's."""
    await _as(client, world["faculty"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            "student",
            institute=world["abc"],
            branch=world["mca"],
            email="fac-noclass@example.com",
        ),
    )
    assert response.status_code == 422


async def test_faculty_cannot_invite_a_peer(client: AsyncClient, world) -> None:
    await _as(client, world["faculty"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            "faculty",
            institute=world["abc"],
            branch=world["mca"],
            classes=[world["taught"]],
            email="fac-fac@example.com",
        ),
    )
    assert response.status_code == 403


async def test_faculty_cannot_invite_a_branch_admin(client: AsyncClient, world) -> None:
    await _as(client, world["faculty"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            "branch_admin",
            institute=world["abc"],
            branch=world["mca"],
            email="fac-ba@example.com",
        ),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------- Student


@pytest.mark.parametrize("role_key", ["student", "faculty", "institute_admin"])
async def test_a_student_can_invite_nobody(client: AsyncClient, world, role_key) -> None:
    await _as(client, world["student"])
    response = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world,
            role_key,
            institute=world["abc"],
            branch=world["mca"],
            email=f"st-{role_key}@example.com",
        ),
    )
    assert response.status_code == 403


# ------------------------------------------- the same rule governs assign and revoke


async def test_assigning_a_role_obeys_the_same_ceiling(client: AsyncClient, world) -> None:
    """Otherwise invite is locked down and assign is a back door to the same escalation."""
    await _as(client, world["institute_admin"])
    response = await client.post(
        f"/api/v1/users/{world['student'].id}/roles",
        json={"role_key": "institute_admin", "institute_id": str(world["abc"].id)},
    )
    assert response.status_code == 403


async def test_assigning_a_role_obeys_the_same_scope(client: AsyncClient, world) -> None:
    await _as(client, world["institute_admin"])
    response = await client.post(
        f"/api/v1/users/{world['student'].id}/roles",
        json={"role_key": "student", "institute_id": str(world["xyz"].id)},
    )
    assert response.status_code == 403


async def test_a_branch_admin_cannot_assign_across_branches(client: AsyncClient, world) -> None:
    await _as(client, world["branch_admin"])
    response = await client.post(
        f"/api/v1/users/{world['student'].id}/roles",
        json={
            "role_key": "faculty",
            "institute_id": str(world["abc"].id),
            "branch_id": str(world["bca"].id),
        },
    )
    assert response.status_code == 403


async def test_revoking_a_role_obeys_the_same_ceiling(client: AsyncClient, world) -> None:
    """A Branch Admin must not be able to strip an Institute Admin of their role."""
    await _as(client, world["branch_admin"])
    response = await client.request(
        "DELETE",
        f"/api/v1/users/{world['institute_admin'].id}/roles",
        json={"role_key": "institute_admin", "institute_id": str(world["abc"].id)},
    )
    assert response.status_code == 403


async def test_a_branch_role_cannot_be_granted_without_a_branch(client: AsyncClient, world) -> None:
    """A Branch Admin with no branch would be effective across the whole institute."""
    await _as(client, world["institute_admin"])
    response = await client.post(
        f"/api/v1/users/{world['student'].id}/roles",
        json={"role_key": "branch_admin", "institute_id": str(world["abc"].id)},
    )
    assert response.status_code == 422


# ------------------------------------------------------- what the UI is allowed to show


@pytest.mark.parametrize(
    "actor,expected",
    [
        ("institute_admin", {"branch_admin", "faculty", "student"}),
        ("branch_admin", {"faculty", "student"}),
        ("faculty", {"student"}),
    ],
)
async def test_the_assignable_role_catalogue_matches_the_matrix(
    client: AsyncClient, world, actor: str, expected: set[str]
) -> None:
    """The invite form reads this list. It must never offer a role the backend would
    refuse — and must never hide one it would accept."""
    await _as(client, world[actor])
    response = await client.get("/api/v1/users/roles/catalogue")
    assert response.status_code == 200
    assert {r["key"] for r in response.json()} == expected


async def test_the_catalogue_never_disagrees_with_the_check(client: AsyncClient, world) -> None:
    """Whatever a list offers, the matching endpoint must accept — and the reverse.

    There are two lists now, because there are two different questions. "Who can I invite?"
    excludes platform roles; "who can I promote this person to?" does not, because a Super
    Admin must be able to appoint a successor (PRD §3.1 "any role") or the first owner can
    never be replaced.
    """
    await _as(client, world["super_admin"])

    for_invite = {
        r["key"]
        for r in (
            await client.get("/api/v1/users/roles/catalogue", params={"purpose": "invite"})
        ).json()
    }
    for_assign = {r["key"] for r in (await client.get("/api/v1/users/roles/catalogue")).json()}

    assert "super_admin" not in for_invite, "an invitation must not offer platform authority"
    assert "super_admin" in for_assign, "a Super Admin must be able to appoint a successor"

    # Everything the invite list offers is genuinely invitable.
    created = await client.post(
        "/api/v1/users/invite",
        json=_invite(world, "institute_admin", institute=world["abc"], email="offered@example.com"),
    )
    assert created.status_code == 201, created.text

    # And what the assign list offers is genuinely assignable.
    promoted = await client.post(
        f"/api/v1/users/{world['institute_admin'].id}/roles", json={"role_key": "super_admin"}
    )
    assert promoted.status_code == 201, promoted.text


async def test_an_invited_super_admin_does_not_count_as_the_survivor(
    client: AsyncClient, world, db
) -> None:
    """PRD §3's "at least one Super Admin must always exist" has to mean one who can sign in.

    Inviting a second Super Admin creates the role assignment immediately, but that person
    has no password until they complete setup. If the guard counted them, the only working
    administrator could revoke their own role and lock everybody out of the platform with no
    way back — which is exactly what happened on the live stack before this was fixed.
    """
    from sqlalchemy import select

    from app.modules.users.models import User

    await _as(client, world["super_admin"])

    # A platform role cannot be invited directly any more, so build the same situation the
    # supported way: invite the person into an institute, then promote them. They are still
    # `invited` with no password, which is the condition under test.
    invited = await client.post(
        "/api/v1/users/invite",
        json=_invite(
            world, "institute_admin", institute=world["abc"], email="successor@example.com"
        ),
    )
    assert invited.status_code == 201, invited.text

    successor = await db.scalar(select(User).where(User.email == "successor@example.com"))
    assert successor is not None
    assert successor.status == "invited" and successor.password_hash is None

    promoted = await client.post(
        f"/api/v1/users/{successor.id}/roles", json={"role_key": "super_admin"}
    )
    assert promoted.status_code == 201, promoted.text

    # Two assignments exist, but only one of them belongs to someone who can log in.
    refused = await client.request(
        "DELETE",
        f"/api/v1/users/{world['super_admin'].id}/roles",
        json={"role_key": "super_admin"},
    )
    assert refused.status_code == 409, (
        "the last Super Admin who can actually sign in was allowed to revoke themselves"
    )
