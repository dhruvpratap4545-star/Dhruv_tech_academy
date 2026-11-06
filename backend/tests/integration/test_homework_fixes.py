"""Regression tests for Homework Board review findings: a parent's detail view, resubmission
keeping earlier files, checking work sent back for redo, and clearing marks."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.db import Db
from app.modules.org.models import ClassEnrollment
from app.modules.users.models import Guardian
from tests.integration.test_homework_board import _as, _assign, _submit, world  # noqa: F401


async def _checked(client: AsyncClient, world, **check) -> tuple[dict, dict]:  # noqa: F811
    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    sub = (await _submit(client, hw["id"], text="Answers")).json()
    await _as(client, world["faculty_a"])
    response = await client.post(
        f"/api/v1/homework/{hw['id']}/submissions/{sub['id']}/check", json=check
    )
    assert response.status_code == 200, response.text
    return hw, sub


async def test_a_parent_opening_homework_sees_their_childs_submission(
    client: AsyncClient,
    world,  # noqa: F811
) -> None:
    hw, _ = await _checked(client, world, marks=8, remark="Good work")

    await _as(client, world["parent_a"])
    plain = await client.get(f"/api/v1/homework/{hw['id']}")
    chosen = await client.get(
        f"/api/v1/homework/{hw['id']}", params={"student_id": str(world["student_a"].id)}
    )

    for response in (plain, chosen):
        assert response.status_code == 200, response.text
        assert response.json()["student_status"] == "checked"
        assert response.json()["submission"]["marks"] == 8
        assert response.json()["submission"]["remark"] == "Good work"


async def test_a_parent_cannot_pick_a_child_they_are_not_linked_to(
    client: AsyncClient,
    db: Db,
    world,  # noqa: F811
) -> None:
    hw = await _assign(client, world)
    # parent_b is linked to student_b only; put student_b in 10-A too so the homework is
    # readable, then ask for student_a's submission.
    db.add(ClassEnrollment(class_id=world["class_a"].id, student_user_id=world["student_b"].id))
    await db.commit()

    await _as(client, world["parent_b"])
    other = await client.get(
        f"/api/v1/homework/{hw['id']}", params={"student_id": str(world["student_a"].id)}
    )
    own = await client.get(
        f"/api/v1/homework/{hw['id']}", params={"student_id": str(world["student_b"].id)}
    )

    assert other.status_code == 404
    assert own.status_code == 200


async def test_a_linked_child_outside_the_class_is_refused(
    client: AsyncClient,
    db: Db,
    world,  # noqa: F811
) -> None:
    hw = await _assign(client, world)
    db.add(Guardian(parent_user_id=world["parent_a"].id, student_user_id=world["student_b"].id))
    await db.commit()

    await _as(client, world["parent_a"])
    response = await client.get(
        f"/api/v1/homework/{hw['id']}", params={"student_id": str(world["student_b"].id)}
    )

    assert response.status_code == 404


async def test_a_text_only_resubmission_keeps_the_earlier_photos(
    client: AsyncClient,
    world,  # noqa: F811
) -> None:
    hw = await _assign(client, world)
    await _as(client, world["student_a"])
    first = (await _submit(client, hw["id"], text="draft", photos=2)).json()

    text_only = await _submit(client, hw["id"], text="better answer")
    new_files = await _submit(client, hw["id"], text="final", photos=1)

    assert text_only.status_code == 200, text_only.text
    assert [f["id"] for f in text_only.json()["files"]] == [f["id"] for f in first["files"]]
    assert text_only.json()["text"] == "better answer"
    assert len(new_files.json()["files"]) == 1


async def test_work_sent_back_for_redo_cannot_be_checked_until_resubmitted(
    client: AsyncClient,
    world,  # noqa: F811
) -> None:
    hw, sub = await _checked(client, world, redo=True, remark="Show working")
    url = f"/api/v1/homework/{hw['id']}/submissions/{sub['id']}/check"

    refused = await client.post(url, json={"marks": 5})

    await _as(client, world["student_a"])
    await _submit(client, hw["id"], text="with working")
    await _as(client, world["faculty_a"])
    allowed = await client.post(url, json={"marks": 5})

    assert refused.status_code == 409
    assert allowed.status_code == 200


async def test_clearing_marks_removes_them_but_omitting_them_keeps_them(
    client: AsyncClient,
    world,  # noqa: F811
) -> None:
    hw, sub = await _checked(client, world, marks=8, grade="A", remark="Good")
    url = f"/api/v1/homework/{hw['id']}/submissions/{sub['id']}/check"

    kept = (await client.post(url, json={"remark": "Very good"})).json()
    cleared = (await client.post(url, json={"marks": None, "grade": None, "remark": "x"})).json()

    assert kept["marks"] == 8 and kept["grade"] == "A"
    assert cleared["marks"] is None and cleared["grade"] is None
