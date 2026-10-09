"""Bulk suspend and re-activate (PRD §8).

The danger in a bulk endpoint is always the same: it becomes a way to do in a list what you
may not do one at a time. So every test here asks whether the per-user rules survived being
applied in a loop — your permission, your scope, their rank below yours, never yourself —
and whether a refusal for one person quietly becomes a success for them.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture
async def world(institute, make_user, db):
    abc, mca = await institute("ABC College", "ABC", with_branch="MCA")
    xyz, _cse = await institute("XYZ College", "XYZ", with_branch="CSE")
    return {
        "abc": abc,
        "mca": mca,
        "xyz": xyz,
        "owner": await make_user("super_admin"),
        "principal": await make_user("institute_admin", institute_id=abc.id),
        "peer": await make_user("institute_admin", institute_id=abc.id),
        "head": await make_user("branch_admin", institute_id=abc.id, branch_id=mca.id),
        "teacher": await make_user("faculty", institute_id=abc.id, branch_id=mca.id),
        "student_a": await make_user("student", institute_id=abc.id),
        "student_b": await make_user("student", institute_id=abc.id),
        "outsider": await make_user("student", institute_id=xyz.id),
    }


async def _bulk(client, ids, status="suspended"):
    return await client.post(
        "/api/v1/users/bulk-status",
        json={"user_ids": [str(i) for i in ids], "status": status},
    )


def _by_id(body, user) -> dict:
    return next(r for r in body["results"] if r["user_id"] == str(user.id))


async def test_several_people_are_suspended_in_one_request(client, world):
    await _as(client, world["principal"])
    response = await _bulk(client, [world["student_a"].id, world["student_b"].id])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] == 2 and body["skipped"] == 0
    assert all(r["outcome"] == "succeeded" for r in body["results"])

    listed = await client.get("/api/v1/users", params={"status": "suspended", "limit": 100})
    suspended = {u["id"] for u in listed.json()["items"]}
    assert str(world["student_a"].id) in suspended
    assert str(world["student_b"].id) in suspended


async def test_a_suspended_person_cannot_sign_in_afterwards(client, world):
    """The point of the action, not just the row's status column."""
    await _as(client, world["principal"])
    assert (await _bulk(client, [world["student_a"].id])).status_code == 200

    client.cookies.clear()
    denied = await client.post(
        "/api/v1/auth/login",
        json={"email": world["student_a"].email, "password": "Jacaranda!Tide4"},
    )
    assert denied.status_code == 403


async def test_you_are_skipped_from_your_own_batch(client, world):
    """Including yourself must not work, however it is wrapped. An institute locking
    itself out of its own administrator account has no way back."""
    await _as(client, world["principal"])
    response = await _bulk(client, [world["principal"].id, world["student_a"].id])

    body = response.json()
    assert body["succeeded"] == 1 and body["skipped"] == 1
    mine = _by_id(body, world["principal"])
    assert mine["outcome"] == "skipped"
    assert "your own" in mine["reason"].lower()

    me = await client.get("/api/v1/me")
    assert me.status_code == 200, "the actor must still be signed in and active"


async def test_somebody_above_the_caller_is_skipped_and_the_rest_still_apply(client, world):
    """One refusal must not fail the batch — the administrator would have no idea which
    person caused it, and would unpick the selection by hand.

    The person refused here is the platform owner, who outranks the caller. A *peer* is no
    longer refused: see the test below.
    """
    await _as(client, world["principal"])
    response = await _bulk(
        client, [world["owner"].id, world["student_a"].id, world["student_b"].id]
    )

    body = response.json()
    assert body["succeeded"] == 2 and body["skipped"] == 1
    assert _by_id(body, world["owner"])["outcome"] == "skipped"


async def test_a_peer_can_be_suspended(client, world):
    """Suspending is restraint, not escalation, so equal rank is allowed.

    It used to be refused, on the same rule that governs *granting* a role. That looked
    tidy and was wrong in the case that matters most: if an administrator's password is
    stolen, the people who have to shut that account down are the ones at their own level,
    and the strict rule refused every one of them. At the top of the hierarchy there is
    nobody above to fall back on, so the account simply could not be contained.

    The caller gains nothing by it — a peer already has every power they do — and
    `_guard_last_super_admin` still stops the platform being left with nobody in charge.
    """
    await _as(client, world["principal"])
    response = await _bulk(client, [world["peer"].id])

    body = response.json()
    assert body["succeeded"] == 1 and body["skipped"] == 0, body
    assert _by_id(body, world["peer"])["outcome"] == "succeeded"


async def test_somebody_in_another_institute_is_skipped(client, world):
    await _as(client, world["principal"])
    response = await _bulk(client, [world["outsider"].id, world["student_a"].id])

    body = response.json()
    assert body["succeeded"] == 1 and body["skipped"] == 1
    assert _by_id(body, world["outsider"])["outcome"] == "skipped"


async def test_a_branch_admin_cannot_reach_outside_their_branch(client, world, make_user):
    """The scope rule has to survive the loop too."""
    other_branch_student = world["student_a"]
    await _as(client, world["head"])
    response = await _bulk(client, [other_branch_student.id, world["teacher"].id])

    body = response.json()
    # The faculty member is in their branch and below them, so that one lands; the
    # institute-wide student is not theirs to touch.
    assert _by_id(body, world["teacher"])["outcome"] == "succeeded"
    assert body["skipped"] >= 1


async def test_a_faculty_member_cannot_suspend_at_all(client, world):
    """`user:update_status` is not theirs, so the request never reaches the loop."""
    await _as(client, world["teacher"])
    response = await _bulk(client, [world["student_a"].id])
    assert response.status_code == 403


async def test_an_unknown_id_is_skipped_not_fatal(client, world):
    await _as(client, world["principal"])
    response = await _bulk(client, [uuid.uuid4(), world["student_a"].id])

    body = response.json()
    assert response.status_code == 200
    assert body["succeeded"] == 1 and body["skipped"] == 1


async def test_re_activation_works_the_same_way(client, world):
    await _as(client, world["principal"])
    await _bulk(client, [world["student_a"].id, world["student_b"].id])

    response = await _bulk(client, [world["student_a"].id, world["student_b"].id], status="active")
    assert response.json()["succeeded"] == 2

    listed = await client.get("/api/v1/users", params={"status": "active", "limit": 100})
    active = {u["id"] for u in listed.json()["items"]}
    assert str(world["student_a"].id) in active


async def test_every_change_writes_its_own_audit_row(client, world):
    """A bulk action is still a sequence of individual decisions about individual people,
    and the record has to read that way or it is useless in an investigation."""
    await _as(client, world["principal"])
    await _bulk(client, [world["student_a"].id, world["student_b"].id])

    logs = await client.get("/api/v1/audit-logs", params={"action": "user_suspended", "limit": 100})
    targets = {row["target_id"] for row in logs.json()["items"]}
    assert str(world["student_a"].id) in targets
    assert str(world["student_b"].id) in targets


async def test_a_skipped_person_leaves_no_audit_row(client, world):
    """Nothing happened to them, so nothing may be recorded as having happened."""
    await _as(client, world["principal"])
    await _bulk(client, [world["owner"].id, world["student_a"].id])

    logs = await client.get("/api/v1/audit-logs", params={"action": "user_suspended", "limit": 100})
    targets = {row["target_id"] for row in logs.json()["items"]}
    assert str(world["owner"].id) not in targets
    assert str(world["student_a"].id) in targets, "the rest of the batch still applied"


async def test_the_batch_is_capped(client, world):
    await _as(client, world["principal"])
    response = await _bulk(client, [uuid.uuid4() for _ in range(101)])
    assert response.status_code == 422


async def test_the_same_person_cannot_be_listed_twice(client, world):
    """Applied twice and counted twice makes the summary wrong in a way nobody would
    think to question."""
    await _as(client, world["principal"])
    response = await _bulk(client, [world["student_a"].id, world["student_a"].id])
    assert response.status_code == 422


async def test_an_empty_batch_is_refused(client, world):
    await _as(client, world["principal"])
    response = await client.post(
        "/api/v1/users/bulk-status", json={"user_ids": [], "status": "suspended"}
    )
    assert response.status_code == 422
