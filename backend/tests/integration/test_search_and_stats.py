"""Global search and the dashboard's sign-in chart.

Search is the classic place tenant isolation fails, because it is naturally written as
"query everything, then filter". So the tests that matter here are the negative ones: what
a search must *not* return.
"""

from __future__ import annotations

from datetime import date

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
    from app.modules.org.models import AcademicSession, Branch, Class

    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")
    bca = Branch(institute_id=abc.id, name="BCA Wing", code="BCA")
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
    db.add(
        Class(
            institute_id=abc.id,
            branch_id=mca.id,
            academic_session_id=term.id,
            name="Physics Lab",
            code="PHY1",
        )
    )

    xyz, cse = await institute("XYZ Academy", "XYZ", with_branch="CSE Wing")
    db.add(
        Class(
            institute_id=xyz.id,
            branch_id=cse.id,
            academic_session_id=(
                db.add(
                    other_term := AcademicSession(
                        institute_id=xyz.id,
                        name="2026-27",
                        start_date=date(2026, 7, 1),
                        end_date=date(2027, 6, 30),
                        is_current=True,
                    )
                )
                or (await db.flush())
                or other_term.id
            ),
            name="Physics Lab",
            code="PHY2",
        )
    )
    await db.commit()

    return {
        "abc": abc,
        "xyz": xyz,
        "owner": await make_user("super_admin"),
        "principal": await make_user(
            "institute_admin", institute_id=abc.id, email="principal@abc.example"
        ),
        "outsider": await make_user(
            "institute_admin", institute_id=xyz.id, email="head@xyz.example"
        ),
        "student": await make_user("student", institute_id=abc.id, email="learner@abc.example"),
    }


def _titles(body, kind):
    group = next((g for g in body["groups"] if g["kind"] == kind), None)
    return [i["title"] for i in group["items"]] if group else None


async def test_search_finds_people_institutes_branches_and_classes(client, world):
    await _as(client, world["owner"])
    body = (await client.get("/api/v1/search", params={"q": "Physics"})).json()
    assert "Physics Lab" in _titles(body, "class")

    body = (await client.get("/api/v1/search", params={"q": "ABC"})).json()
    assert "ABC College" in _titles(body, "institute")


async def test_search_never_crosses_an_institute_boundary(client, world):
    """The one that matters. Both institutes have a class called "Physics Lab"."""
    await _as(client, world["principal"])
    body = (await client.get("/api/v1/search", params={"q": "Physics"})).json()
    classes = _titles(body, "class") or []
    assert len(classes) == 1, "only this institute's class may be returned"

    body = (await client.get("/api/v1/search", params={"q": "XYZ"})).json()
    assert not (_titles(body, "institute") or []), "another institute must not be findable"

    body = (await client.get("/api/v1/search", params={"q": "CSE"})).json()
    assert not (_titles(body, "branch") or []), "another institute's branch must not surface"


async def test_search_omits_groups_the_caller_cannot_read(client, world):
    """Absent, not empty: an empty group still tells you the category exists to be empty."""
    await _as(client, world["student"])
    body = (await client.get("/api/v1/search", params={"q": "ABC"})).json()
    kinds = {g["kind"] for g in body["groups"]}
    assert "branch" not in kinds, "a student holds no branch:read"


async def test_a_single_character_search_returns_nothing(client, world):
    await _as(client, world["owner"])
    body = (await client.get("/api/v1/search", params={"q": "a"})).json()
    assert body["groups"] == []


async def test_search_requires_a_signed_in_caller(client):
    client.cookies.clear()
    assert (await client.get("/api/v1/search", params={"q": "anything"})).status_code == 401


async def test_a_block_removes_a_group_from_search(client, world):
    """Search must honour an explicit deny, like every other read path."""
    await _as(client, world["owner"])
    granted = await client.post(
        f"/api/v1/users/{world['principal'].id}/grants",
        json={
            "permission": "class:read",
            "effect": "deny",
            "institute_id": str(world["abc"].id),
            "reason": "Blocked during audit",
        },
    )
    assert granted.status_code == 201

    await _as(client, world["principal"])
    body = (await client.get("/api/v1/search", params={"q": "Physics"})).json()
    assert not (_titles(body, "class") or [])


# ------------------------------------------------------------------------ sign-in stats


async def test_stats_return_every_day_in_the_window(client, world):
    await _as(client, world["owner"])
    response = await client.get("/api/v1/audit-logs/stats", params={"days": 14})
    assert response.status_code == 200
    body = response.json()
    assert len(body["days"]) == 14, "quiet days must still appear, or the chart lies"
    assert body["total_successful"] >= 1, "our own sign-in should be counted"
    assert body["days"][-1]["successful"] >= 1, "and it belongs to today"


async def test_stats_count_failures_and_locks(client, world):
    await _as(client, world["owner"])
    before = (await client.get("/api/v1/audit-logs/stats")).json()["total_failed"]

    client.cookies.clear()
    await client.post(
        "/api/v1/auth/login",
        json={"email": world["student"].email, "password": "definitelywrong9"},
    )

    await _as(client, world["owner"])
    after = (await client.get("/api/v1/audit-logs/stats")).json()["total_failed"]
    assert after == before + 1


async def test_stats_are_scoped_to_the_callers_institutes(client, world):
    """Each institute counts its own activity, and the platform counts everyone's.

    Sign in as three different people in two institutes, then check the arithmetic: each
    admin must see strictly fewer events than the platform owner, and the owner must see
    at least the sum of both.
    """
    await _as(client, world["principal"])  # ABC
    await _as(client, world["outsider"])  # XYZ
    xyz = (await client.get("/api/v1/audit-logs/stats")).json()["total_successful"]

    await _as(client, world["principal"])
    abc = (await client.get("/api/v1/audit-logs/stats")).json()["total_successful"]

    await _as(client, world["owner"])
    platform = (await client.get("/api/v1/audit-logs/stats")).json()["total_successful"]

    assert xyz >= 1 and abc >= 1, "each admin must see their own institute's sign-ins"
    assert platform >= abc + xyz, "platform staff see every institute's events"
    assert abc < platform and xyz < platform, "an institute must not see the whole platform"


async def test_a_student_cannot_read_the_stats(client, world):
    await _as(client, world["student"])
    assert (await client.get("/api/v1/audit-logs/stats")).status_code == 403


async def test_the_window_is_capped(client, world):
    await _as(client, world["owner"])
    assert (await client.get("/api/v1/audit-logs/stats", params={"days": 400})).status_code == 422


async def test_a_sign_in_is_recorded_against_the_institute(client, world):
    """Without this an institute admin's chart and audit log are permanently empty, while
    the platform-wide view looks perfectly healthy."""
    await _as(client, world["principal"])
    stats = (await client.get("/api/v1/audit-logs/stats")).json()
    assert stats["total_successful"] >= 1, "the principal's own sign-in must be in their scope"

    logs = (await client.get("/api/v1/audit-logs", params={"action": "login_success"})).json()
    assert logs["items"], "the sign-in must appear in the institute's audit log"


async def test_a_failed_sign_in_is_recorded_against_the_institute(client, world):
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/login",
        json={"email": world["student"].email, "password": "definitelywrong9"},
    )
    await _as(client, world["principal"])
    stats = (await client.get("/api/v1/audit-logs/stats")).json()
    assert stats["total_failed"] >= 1


async def test_an_unknown_email_stays_institute_less(client, world):
    """There is no institute to attribute it to, and guessing one would pin a stranger's
    failed attempt on a customer."""
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/login", json={"email": "nobody@nowhere.example", "password": "whatever99"}
    )
    await _as(client, world["principal"])
    before = (await client.get("/api/v1/audit-logs/stats")).json()["total_failed"]

    await _as(client, world["owner"])
    after = (await client.get("/api/v1/audit-logs/stats")).json()["total_failed"]
    assert after > before, "platform staff must still see it"
