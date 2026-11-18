"""Content Library end to end (Phase 3, Module B).

Covers client acceptance items 4 (the syllabus trees are searchable down to topic level)
and 5 (a PDF and a video link are uploaded and linked to a topic, and are then visible only
to students of the linked class). Material is published the moment it is added — there is
no review step — and the syllabus has four fixed levels: Track › Level › Subject › Topic.
"""

from __future__ import annotations

import io
import uuid
from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from openpyxl import Workbook

from app.core import storage
from app.core.db import Db
from app.modules.audit.models import AuditLog
from app.modules.files.models import StoredFile
from app.modules.library.flatten import flatten_to_four_levels
from app.modules.library.models import (
    ClassSyllabus,
    ContentItem,
    ContentItemVersion,
    SyllabusNode,
)
from app.modules.library.rules import slugify
from app.modules.library.seed import seed_syllabus
from app.modules.library.tree import TreeWriter
from app.modules.org.models import AcademicSession, Class, ClassEnrollment, ClassFaculty
from app.modules.rbac.models import InstituteModule
from app.modules.users.models import Guardian

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
VIDEO = "https://youtu.be/dQw4w9WgXcQ?si=abc"


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text
    return client


async def _tree(db: Db) -> dict[str, SyllabusNode]:
    writer = TreeWriter(db, None)
    await writer.load("cbse")
    cbse = writer.ensure(None, track="cbse", kind="track", name="CBSE", code="cbse")
    c10 = writer.ensure(cbse, track="cbse", kind="level", name="Class 10")
    # Four fixed levels. `elec` is the subject the Ohm's Law topic sits in — the level whose
    # list shows every topic's material underneath it.
    elec = writer.ensure(c10, track="cbse", kind="subject", name="Science")
    ohm = writer.ensure(elec, track="cbse", kind="topic", name="Ohm's Law")
    c9 = writer.ensure(cbse, track="cbse", kind="level", name="Class 9")
    sci9 = writer.ensure(c9, track="cbse", kind="subject", name="Science")
    motion = writer.ensure(sci9, track="cbse", kind="topic", name="Motion")
    await db.commit()
    return {"cbse": cbse, "c10": c10, "elec": elec, "ohm": ohm, "c9": c9, "motion": motion}


@pytest_asyncio.fixture
async def world(db: Db, institute, make_user):
    abc, mca = await institute("ABC School", "ABC", with_branch="MAIN")
    xyz, _ = await institute("XYZ School", "XYZ")
    nolib, _ = await institute("No Library School", "NOLIB")
    for row in (abc, xyz):
        db.add(InstituteModule(institute_id=row.id, module_key="library", enabled=True))
    session = AcademicSession(
        institute_id=abc.id, name="2026-27", start_date=date(2026, 4, 1), end_date=date(2027, 3, 31)
    )
    db.add(session)
    ten_a = Class(
        institute_id=abc.id,
        branch_id=mca.id,
        academic_session_id=session.id,
        name="Class 10",
        section="A",
        code="10A",
    )
    ten_b = Class(
        institute_id=abc.id,
        branch_id=mca.id,
        academic_session_id=session.id,
        name="Class 10",
        section="B",
        code="10B",
    )
    db.add_all([ten_a, ten_b])
    await db.commit()

    users = {
        "platform": await make_user("platform_admin"),
        "abc_admin": await make_user("institute_admin", institute_id=abc.id),
        "faculty": await make_user("faculty", institute_id=abc.id, branch_id=mca.id),
        "student_a": await make_user("student", institute_id=abc.id),
        "student_b": await make_user("student", institute_id=abc.id),
        "parent": await make_user("parent", institute_id=abc.id),
        "xyz_admin": await make_user("institute_admin", institute_id=xyz.id),
        "xyz_student": await make_user("student", institute_id=xyz.id),
        "nolib_admin": await make_user("institute_admin", institute_id=nolib.id),
    }
    db.add(ClassFaculty(class_id=ten_a.id, faculty_user_id=users["faculty"].id, subject="Science"))
    db.add(ClassEnrollment(class_id=ten_a.id, student_user_id=users["student_a"].id))
    db.add(ClassEnrollment(class_id=ten_b.id, student_user_id=users["student_b"].id))
    db.add(Guardian(parent_user_id=users["parent"].id, student_user_id=users["student_a"].id))
    await db.commit()
    return {
        "abc": abc,
        "xyz": xyz,
        "nolib": nolib,
        "ten_a": ten_a,
        "ten_b": ten_b,
        **users,
        **await _tree(db),
    }


async def _link(client: AsyncClient, world, klass, *nodes) -> None:
    await _as(client, world["abc_admin"])
    response = await client.put(
        f"/api/v1/library/classes/{klass.id}/syllabus",
        json={"node_ids": [str(n.id) for n in nodes]},
    )
    assert response.status_code == 200, response.text


async def _published_pair(client: AsyncClient, world) -> tuple[str, str, str]:
    """Faculty add a PDF and a video on Ohm's Law; both are published at once."""
    await _as(client, world["faculty"])
    pdf = await client.post(
        "/api/v1/library/items/upload",
        files={"file": ("ohm notes.pdf", PDF, "application/pdf")},
        data={
            "title": "Ohm's Law notes",
            "node_ids": [str(world["ohm"].id)],
            "institute_id": str(world["abc"].id),
            "medium": "both",
        },
    )
    assert pdf.status_code == 201, pdf.text
    video = await client.post(
        "/api/v1/library/items",
        json={
            "institute_id": str(world["abc"].id),
            "title": "Ohm's Law explained",
            "kind": "video_link",
            "url": VIDEO,
            "node_ids": [str(world["ohm"].id)],
        },
    )
    assert video.status_code == 201, video.text
    assert pdf.json()["status"] == video.json()["status"] == "published"
    return pdf.json()["id"], video.json()["id"], pdf.json()["file_id"]


# ------------------------------------------------------------------- acceptance item 5


async def test_material_is_published_on_upload_and_visible_only_to_the_linked_class(
    client: AsyncClient, db: Db, world
) -> None:
    pdf_id, video_id, file_id = await _published_pair(client, world)
    await _link(client, world, world["ten_a"], world["c10"])
    await _link(client, world, world["ten_b"], world["c9"])
    url = f"/api/v1/library/items?node_id={world['c10'].id}"

    await _as(client, world["student_a"])
    mine = (await client.get(url)).json()
    download = await client.get(f"/api/v1/files/{file_id}")

    assert {i["id"] for i in mine["items"]} == {pdf_id, video_id}
    video = next(i for i in mine["items"] if i["id"] == video_id)
    assert (video["video_provider"], video["video_id"]) == ("youtube", "dQw4w9WgXcQ")
    assert download.status_code == 200 and download.content == PDF

    await _as(client, world["parent"])
    assert {i["id"] for i in (await client.get(url)).json()["items"]} == {pdf_id, video_id}

    for outsider in ("student_b", "xyz_student"):
        await _as(client, world[outsider])
        listed = await client.get(f"/api/v1/library/items?node_id={world['c10'].id}")
        assert listed.status_code in (200, 404)
        if listed.status_code == 200:
            assert listed.json()["items"] == []
        assert (await client.get(f"/api/v1/library/items/{pdf_id}")).status_code == 404
        assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 404

    assert await db.count(AuditLog, {"action": "library_item_created"}) == 2


async def test_material_is_visible_at_once_to_its_class_only(
    client: AsyncClient, db: Db, world
) -> None:
    await _link(client, world, world["ten_a"], world["c10"])
    await _as(client, world["faculty"])
    note = await client.post(
        "/api/v1/library/items",
        json={
            "institute_id": str(world["abc"].id),
            "title": "Quick note",
            "kind": "text",
            "body": "<script>alert(1)</script> V = IR",
            "node_ids": [str(world["ohm"].id)],
        },
    )
    item_id = note.json()["id"]
    assert note.json()["status"] == "published"
    assert note.json()["body"] == "<script>alert(1)</script> V = IR"  # stored as plain text

    await _as(client, world["student_a"])
    assert (await client.get(f"/api/v1/library/items/{item_id}")).status_code == 200
    for outsider in ("student_b", "xyz_admin"):
        await _as(client, world[outsider])
        assert (await client.get(f"/api/v1/library/items/{item_id}")).status_code == 404

    # A draft left over from the old review flow is still staff-only.
    db.update_many(ContentItem, {"_id": uuid.UUID(item_id)}, {"status": "draft"})
    await db.commit()
    await _as(client, world["abc_admin"])
    assert (await client.get(f"/api/v1/library/items/{item_id}")).status_code == 200
    await _as(client, world["student_a"])
    assert (await client.get(f"/api/v1/library/items/{item_id}")).status_code == 404


async def test_teachers_edit_and_archive_their_own_material_and_edits_keep_versions(
    client: AsyncClient, db: Db, world, make_user
) -> None:
    _, video_id, _ = await _published_pair(client, world)
    colleague = await make_user("faculty", institute_id=world["abc"].id)

    await _as(client, colleague)
    not_theirs = await client.patch(f"/api/v1/library/items/{video_id}", json={"title": "Mine now"})
    not_theirs_archive = await client.post(f"/api/v1/library/items/{video_id}/archive")
    assert [not_theirs.status_code, not_theirs_archive.status_code] == [403, 403]

    await _as(client, world["faculty"])
    edited = await client.patch(
        f"/api/v1/library/items/{video_id}", json={"title": "Ohm's Law, explained again"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2 and edited.json()["status"] == "published"

    await _as(client, world["abc_admin"])
    again = await client.patch(f"/api/v1/library/items/{video_id}", json={"title": "Ohm's Law"})
    versions = await client.get(f"/api/v1/library/items/{video_id}/versions")
    assert again.json()["version"] == 3
    assert sorted(v["version"] for v in versions.json()) == [1, 2]
    first = next(v for v in versions.json() if v["version"] == 1)
    assert first["fields"]["title"] == "Ohm's Law explained"
    assert await db.count(ContentItemVersion, {}) == 2

    await _as(client, world["faculty"])
    archived = await client.post(f"/api/v1/library/items/{video_id}/archive")
    assert archived.status_code == 200 and archived.json()["status"] == "archived"


async def test_bad_links_are_refused(client: AsyncClient, world) -> None:
    await _as(client, world["faculty"])
    base = {
        "institute_id": str(world["abc"].id),
        "title": "Bad",
        "node_ids": [str(world["ohm"].id)],
    }
    http_video = await client.post(
        "/api/v1/library/items",
        json={**base, "kind": "video_link", "url": "http://youtu.be/dQw4w9WgXcQ"},
    )
    other_site = await client.post(
        "/api/v1/library/items",
        json={**base, "kind": "video_link", "url": "https://evil.example/v"},
    )
    http_link = await client.post(
        "/api/v1/library/items", json={**base, "kind": "link", "url": "http://ncert.nic.in"}
    )
    exe = await client.post(
        "/api/v1/library/items/upload",
        files={"file": ("notes.pdf", b"MZ\x90binary", "application/pdf")},
        data={
            "title": "Bad",
            "node_ids": [str(world["ohm"].id)],
            "institute_id": str(world["abc"].id),
        },
    )
    assert [r.status_code for r in (http_video, other_site, http_link, exe)] == [422] * 4


async def test_material_can_only_link_to_its_own_library(client: AsyncClient, world) -> None:
    await _as(client, world["xyz_admin"])
    xyz_node = await client.post(
        "/api/v1/library/nodes",
        json={
            "parent_id": str(world["elec"].id),
            "institute_id": str(world["xyz"].id),
            "kind": "topic",
            "name": "XYZ extra",
        },
    )
    await _as(client, world["faculty"])
    response = await client.post(
        "/api/v1/library/items",
        json={
            "institute_id": str(world["abc"].id),
            "title": "Cross-linked",
            "kind": "text",
            "body": "x",
            "node_ids": [xyz_node.json()["id"]],
        },
    )
    assert response.status_code == 422


# ------------------------------------------------------------------------ syllabus tree


async def test_browsing_the_tree_with_breadcrumbs(client: AsyncClient, world) -> None:
    await _as(client, world["abc_admin"])
    tracks = (await client.get("/api/v1/library/tracks")).json()
    levels = (await client.get(f"/api/v1/library/nodes?parent_id={world['cbse'].id}")).json()
    detail = (await client.get(f"/api/v1/library/nodes/{world['ohm'].id}")).json()

    assert [t["code"] for t in tracks] == ["cbse"]
    assert tracks[0]["child_count"] == 2
    assert [lvl["name"] for lvl in levels] == ["Class 10", "Class 9"]
    assert [c["name"] for c in detail["breadcrumb"]] == [
        "CBSE",
        "Class 10",
        "Science",
    ]


async def test_a_student_browses_only_down_to_their_linked_syllabus(
    client: AsyncClient, world
) -> None:
    await _link(client, world, world["ten_a"], world["c10"])
    await _as(client, world["student_a"])

    levels = (await client.get(f"/api/v1/library/nodes?parent_id={world['cbse'].id}")).json()
    other = await client.get(f"/api/v1/library/nodes/{world['motion'].id}")

    assert [lvl["name"] for lvl in levels] == ["Class 10"]
    assert other.status_code == 404


async def test_master_nodes_are_written_only_by_the_platform(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["abc_admin"])
    master = await client.post(
        "/api/v1/library/nodes",
        json={"parent_id": str(world["elec"].id), "kind": "topic", "name": "Sneaky master topic"},
    )
    rename = await client.patch(f"/api/v1/library/nodes/{world['ohm'].id}", json={"name": "Mine"})
    own = await client.post(
        "/api/v1/library/nodes",
        json={
            "parent_id": str(world["elec"].id),
            "institute_id": str(world["abc"].id),
            "kind": "topic",
            "name": "Electric Power at Home",
        },
    )
    assert master.status_code == 403
    assert rename.status_code == 403
    assert own.status_code == 201, own.text
    assert own.json()["institute_id"] == str(world["abc"].id)

    await _as(client, world["xyz_admin"])
    assert (await client.get(f"/api/v1/library/nodes/{own.json()['id']}")).status_code == 404

    await _as(client, world["platform"])
    created = await client.post(
        "/api/v1/library/nodes",
        json={"parent_id": str(world["elec"].id), "kind": "topic", "name": "Electric Power"},
    )
    duplicate = await client.post(
        "/api/v1/library/nodes",
        json={"parent_id": str(world["elec"].id), "kind": "topic", "name": "Electric power"},
    )
    wrong_kind = await client.post(
        "/api/v1/library/nodes",
        json={"parent_id": str(world["ohm"].id), "kind": "chapter", "name": "Deeper"},
    )
    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert wrong_kind.status_code == 422
    assert await db.count(AuditLog, {"action": "library_node_created"}) == 2


async def test_faculty_add_sections_and_change_only_their_own(
    client: AsyncClient, world, make_user
) -> None:
    colleague = await make_user("faculty", institute_id=world["abc"].id)
    await _as(client, world["faculty"])
    # No kind sent: the level below a subject is always a topic.
    topic = await client.post(
        "/api/v1/library/nodes",
        json={
            "parent_id": str(world["elec"].id),
            "institute_id": str(world["abc"].id),
            "name": "Electric Power at Home",
        },
    )
    assert topic.status_code == 201, topic.text
    assert topic.json()["kind"] == "topic"
    topic_id = topic.json()["id"]
    below_topic = await client.post(
        "/api/v1/library/nodes",
        json={"parent_id": topic_id, "institute_id": str(world["abc"].id), "name": "Deeper"},
    )
    renamed = await client.patch(f"/api/v1/library/nodes/{topic_id}", json={"name": "Power"})
    master = await client.patch(f"/api/v1/library/nodes/{world['ohm'].id}", json={"name": "X"})
    reorder = await client.post(f"/api/v1/library/nodes/{topic_id}/reorder", json={"position": 0})
    assert below_topic.status_code == 422
    assert renamed.status_code == 200 and renamed.json()["name"] == "Power"
    assert master.status_code == 403
    assert reorder.status_code == 403  # ordering a whole level is the manager's job

    await _as(client, colleague)
    theirs = await client.patch(f"/api/v1/library/nodes/{topic_id}", json={"name": "Mine"})
    assert theirs.status_code == 403
    assert (await client.post(f"/api/v1/library/nodes/{topic_id}/archive")).status_code == 403

    await _as(client, world["abc_admin"])
    managed = await client.patch(f"/api/v1/library/nodes/{topic_id}", json={"name": "Power Use"})
    assert managed.status_code == 200


async def test_archiving_is_refused_while_the_subtree_has_material(
    client: AsyncClient, db: Db, world
) -> None:
    pdf_id, video_id, _ = await _published_pair(client, world)
    await _as(client, world["platform"])

    refused = await client.post(f"/api/v1/library/nodes/{world['elec'].id}/archive")
    for item_id in (pdf_id, video_id):
        assert (await client.post(f"/api/v1/library/items/{item_id}/archive")).status_code == 200
    archived = await client.post(f"/api/v1/library/nodes/{world['elec'].id}/archive")

    assert refused.status_code == 409
    assert archived.status_code == 200
    ohm = await db.get(SyllabusNode, world["ohm"].id)
    assert ohm.status == "archived"  # the whole subtree goes with it
    assert (await client.get(f"/api/v1/library/nodes?parent_id={world['c10'].id}")).json() == []


async def test_reorder_moves_a_node_among_its_siblings(client: AsyncClient, world) -> None:
    await _as(client, world["platform"])
    response = await client.post(
        f"/api/v1/library/nodes/{world['c9'].id}/reorder", json={"position": 0}
    )
    levels = (await client.get(f"/api/v1/library/nodes?parent_id={world['cbse'].id}")).json()
    assert response.status_code == 200
    assert [lvl["name"] for lvl in levels] == ["Class 9", "Class 10"]


async def test_a_disabled_module_is_refused(client: AsyncClient, world) -> None:
    await _as(client, world["nolib_admin"])
    assert (await client.get("/api/v1/library/tracks")).status_code == 403
    assert (await client.get("/api/v1/library/search?q=ohm")).status_code == 403


# --------------------------------------------------------------------- class syllabus


async def test_linking_a_class_needs_class_update(client: AsyncClient, db: Db, world) -> None:
    await _as(client, world["faculty"])
    denied = await client.put(
        f"/api/v1/library/classes/{world['ten_a'].id}/syllabus",
        json={"node_ids": [str(world["c10"].id)]},
    )
    assert denied.status_code == 403

    await _link(client, world, world["ten_a"], world["c10"])
    await _as(client, world["faculty"])
    read = (await client.get(f"/api/v1/library/classes/{world['ten_a'].id}/syllabus")).json()
    assert [n["path"] for n in read["nodes"]] == ["CBSE › Class 10"]
    assert await db.count(AuditLog, {"action": "class_syllabus_updated"}) == 1

    await _as(client, world["xyz_admin"])
    assert (
        await client.get(f"/api/v1/library/classes/{world['ten_a'].id}/syllabus")
    ).status_code == 403


async def test_my_syllabus_for_students_and_parents(client: AsyncClient, world) -> None:
    await _link(client, world, world["ten_a"], world["c10"])

    await _as(client, world["student_a"])
    mine = (await client.get("/api/v1/library/my")).json()
    await _as(client, world["parent"])
    child = (await client.get("/api/v1/library/my")).json()

    assert [(m["class_name"], [n["name"] for n in m["nodes"]]) for m in mine] == [
        ("Class 10 A", ["Class 10"])
    ]
    assert child[0]["student_user_id"] == str(world["student_a"].id)
    assert child[0]["nodes"][0]["name"] == "Class 10"


# ------------------------------------------------------------------- acceptance item 4


async def test_seeded_tracks_are_searchable_down_to_topic_level(
    client: AsyncClient, db: Db, world
) -> None:
    await seed_syllabus(db)
    await _as(client, world["platform"])

    hits = {}
    for track, query in (
        ("cbse", "Electricity"),
        ("neet", "Breathing and Exchange of Gases"),
        ("jee", "Rolling Motion"),
        ("upsc", "Probity in Governance"),
    ):
        body = (await client.get(f"/api/v1/library/search?q={query}&track={track}")).json()
        hits[track] = body["nodes"]
        assert body["nodes"], track

    for track, nodes in hits.items():
        assert any(n["kind"] == "topic" for n in nodes), track
        assert all(n["path"].count(" › ") <= 3 for n in nodes), track  # four levels at most
    assert any(n["path"] == "CBSE › Class 10 › Science › Electricity" for n in hits["cbse"])


async def test_seed_is_idempotent(db: Db, seeded) -> None:
    first = await seed_syllabus(db, "upsc")
    count = await db.count(SyllabusNode, {"track": "upsc"})
    second = await seed_syllabus(db, "upsc")

    assert first["upsc"]["created"] == count > 50
    assert second["upsc"]["created"] == 0
    assert second["upsc"]["updated"] == 0
    assert await db.count(SyllabusNode, {"track": "upsc"}) == count


async def test_all_four_tracks_seed(db: Db, seeded) -> None:
    results = await seed_syllabus(db)
    assert set(results) == {"cbse", "neet", "jee", "upsc"}
    assert results["cbse"]["by_kind"]["level"] == 12
    assert results["cbse"]["by_kind"]["topic"] > 300
    assert set(results["neet"]["by_kind"]) <= {"track", "level", "subject", "topic"}


# ------------------------------------------------------------------------------ import


def _sheet(rows: list[list[str]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["Track", "Level", "Subject", "Topic", "Medium", "Difficulty", "Exam tags"])
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


async def test_import_previews_then_applies_and_is_safe_to_repeat(
    client: AsyncClient, db: Db, world
) -> None:
    data = _sheet(
        [
            ["State Board", "Class 1", "Maths", "", "", "", ""],
            ["CUSTOM", "Class 8", "Science", "Reflection", "Hindi", "Easy", "board"],
            ["Custom", "Class 8", "Science", "Refraction", "Both", "", ""],
            ["Custom", "", "", "", "", "", ""],
        ]
    )
    upload = {"file": ("syllabus.xlsx", data, "application/octet-stream")}
    await _as(client, world["platform"])

    preview = (await client.post("/api/v1/library/import", files=upload)).json()
    before = await db.count(SyllabusNode, {"track": "custom"})
    applied = (await client.post("/api/v1/library/import?dry_run=false", files=upload)).json()
    again = (await client.post("/api/v1/library/import?dry_run=false", files=upload)).json()

    assert preview["dry_run"] is True and preview["created"] == 5
    assert before == 0
    assert (preview["rows_total"], preview["rows_valid"]) == (4, 2)
    assert [p["row"] for p in preview["problems"]] == [2, 5]
    assert applied["created"] == 5
    assert again["created"] == 0
    reflection = await db.find_one(SyllabusNode, {"name": "Reflection"})
    assert reflection.code_path == "custom/class-8/science/reflection"
    assert reflection.mediums == ["hi"] and reflection.difficulty == "easy"
    assert reflection.exam_tags == ["board"]


async def test_institute_admin_imports_into_their_own_library_only(
    client: AsyncClient, db: Db, world
) -> None:
    data = _sheet(
        [
            ["CBSE", "Class 10", "Science", "Ohm's Law", "", "", ""],
            ["CBSE", "Class 10", "Science", "Power at Home", "", "", ""],
        ]
    )
    upload = {"file": ("s.xlsx", data, "application/octet-stream")}
    await _as(client, world["abc_admin"])

    master = await client.post("/api/v1/library/import?dry_run=false", files=upload)
    own = await client.post(
        "/api/v1/library/import?dry_run=false",
        files=upload,
        data={"institute_id": str(world["abc"].id)},
    )

    assert master.status_code == 403
    assert own.status_code == 200, own.text
    assert own.json()["created"] == 1  # reuses the master path; only the new topic is added
    power = await db.find_one(SyllabusNode, {"name": "Power at Home"})
    assert power.institute_id == world["abc"].id
    assert power.parent_id == world["elec"].id


async def test_the_template_downloads(client: AsyncClient, world) -> None:
    await _as(client, world["abc_admin"])
    response = await client.get("/api/v1/library/import/template")
    assert response.status_code == 200 and response.content[:2] == b"PK"


async def test_items_are_institute_scoped_in_the_database(
    db: Db, client: AsyncClient, world
) -> None:
    await _published_pair(client, world)
    assert {i.institute_id for i in await db.find(ContentItem, {})} == {world["abc"].id}


async def test_another_institute_cannot_act_on_material_or_versions(
    client: AsyncClient, world
) -> None:
    pdf_id, _, _ = await _published_pair(client, world)

    await _as(client, world["xyz_admin"])
    archive = await client.post(f"/api/v1/library/items/{pdf_id}/archive")
    edit = await client.patch(f"/api/v1/library/items/{pdf_id}", json={"title": "Taken"})
    versions = await client.get(f"/api/v1/library/items/{pdf_id}/versions")
    assert [r.status_code for r in (archive, edit, versions)] == [404, 404, 404]

    await _as(client, world["student_a"])
    assert (await client.get(f"/api/v1/library/items/{pdf_id}/versions")).status_code == 403

    await _as(client, world["nolib_admin"])
    write = await client.post(
        "/api/v1/library/items",
        json={
            "institute_id": str(world["nolib"].id),
            "title": "No module",
            "kind": "text",
            "body": "x",
            "node_ids": [str(world["ohm"].id)],
        },
    )
    assert write.status_code == 403


# ------------------------------------------------------------------- review fixes


async def test_faculty_see_colleagues_material_but_not_their_leftover_drafts(
    client: AsyncClient, db: Db, world, make_user
) -> None:
    colleague = await make_user("faculty", institute_id=world["abc"].id)
    note = {
        "institute_id": str(world["abc"].id),
        "kind": "text",
        "body": "V = IR",
        "node_ids": [str(world["ohm"].id)],
    }
    await _as(client, colleague)
    shared = (await client.post("/api/v1/library/items", json={**note, "title": "Shared"})).json()
    draft = (await client.post("/api/v1/library/items", json={**note, "title": "Old"})).json()
    db.update_many(ContentItem, {"_id": uuid.UUID(draft["id"])}, {"status": "draft"})
    await db.commit()

    await _as(client, world["faculty"])
    own = (await client.post("/api/v1/library/items", json={**note, "title": "Own"})).json()
    page = await client.get("/api/v1/library/items?limit=100")
    listed = {i["id"] for i in page.json()["items"]}
    assert {own["id"], shared["id"]} <= listed and draft["id"] not in listed
    assert (await client.get(f"/api/v1/library/items/{draft['id']}")).status_code == 404

    await _as(client, world["abc_admin"])
    assert (await client.get(f"/api/v1/library/items/{draft['id']}")).status_code == 200


async def test_import_matches_existing_children_by_name_and_never_renames(
    client: AsyncClient, db: Db, world
) -> None:
    writer = TreeWriter(db, None)
    await writer.load("cbse")
    maths = writer.ensure(world["c10"], track="cbse", kind="subject", name="Mathematics", code="m")
    await db.commit()
    db.update_many(SyllabusNode, {"_id": world["cbse"].id}, {"name": "CBSE (Board)"})
    await db.commit()

    data = _sheet([["CBSE", "class 10", " MATHEMATICS ", "Algebra", "", "", ""]])
    await _as(client, world["platform"])
    applied = await client.post(
        "/api/v1/library/import?dry_run=false",
        files={"file": ("s.xlsx", data, "application/octet-stream")},
    )

    assert applied.status_code == 200, applied.text
    assert applied.json()["created"] == 1
    subjects = await db.find(SyllabusNode, {"parent_id": world["c10"].id, "kind": "subject"})
    assert sorted(s.name for s in subjects) == ["Mathematics", "Science"]
    algebra = await db.find_one(SyllabusNode, {"name": "Algebra"})
    assert algebra.parent_id == maths.id
    names = {
        n.id: n.name
        for n in await db.find(SyllabusNode, {"_id": {"$in": [world["cbse"].id, world["c10"].id]}})
    }
    assert names == {world["cbse"].id: "CBSE (Board)", world["c10"].id: "Class 10"}


async def test_search_accepts_both_mediums_and_item_hits_carry_their_topics(
    client: AsyncClient, world
) -> None:
    pdf_id, _, _ = await _published_pair(client, world)
    await _as(client, world["abc_admin"])

    both = await client.get("/api/v1/library/search?q=Ohm&medium=both")

    assert both.status_code == 200, both.text
    assert any(n["id"] == str(world["ohm"].id) for n in both.json()["nodes"])
    hit = next(i for i in both.json()["items"] if i["id"] == pdf_id)
    assert hit["node_ids"] == [str(world["ohm"].id)]


async def test_reviewing_at_one_institute_does_not_open_drafts_at_another(
    client: AsyncClient, db: Db, world, make_user
) -> None:
    """Library admin at XYZ, only a teacher at ABC: ABC colleagues' drafts stay hidden."""
    colleague = await make_user("faculty", institute_id=world["abc"].id)
    await _as(client, colleague)
    draft = await client.post(
        "/api/v1/library/items",
        json={
            "institute_id": str(world["abc"].id),
            "kind": "text",
            "title": "Colleague draft",
            "body": "V = IR",
            "node_ids": [str(world["ohm"].id)],
        },
    )
    assert draft.status_code == 201, draft.text
    db.update_many(ContentItem, {"_id": uuid.UUID(draft.json()["id"])}, {"status": "draft"})
    await db.commit()

    teacher = world["faculty"]
    await _as(client, world["platform"])
    promoted = await client.post(
        f"/api/v1/users/{teacher.id}/roles",
        json={"role_key": "institute_admin", "institute_id": str(world["xyz"].id)},
    )
    assert promoted.status_code == 201, promoted.text

    await _as(client, teacher)
    assert (await client.get(f"/api/v1/library/items/{draft.json()['id']}")).status_code == 404


# ------------------------------------------------------------------ presigned upload


class _SigningStorage(storage.LocalStorage):
    """Local disk that pretends to sign, like GCS: the test plays the browser's PUT."""

    async def signed_upload_url(self, key, *, content_type, max_bytes, ttl_seconds):
        return f"https://bucket.test/{key}", {
            "Content-Type": content_type,
            "x-goog-content-length-range": f"0,{max_bytes}",
        }


async def _ticket(client: AsyncClient, world, **overrides):
    return await client.post(
        "/api/v1/library/uploads",
        json={
            "file_name": "ohm.pdf",
            "content_type": "application/pdf",
            "size": len(PDF),
            "institute_id": str(world["abc"].id),
            **overrides,
        },
    )


async def _filed(client: AsyncClient, world, file_id: str):
    return await client.post(
        "/api/v1/library/items/from-upload",
        json={
            "file_id": file_id,
            "title": "Ohm's Law notes",
            "node_ids": [str(world["ohm"].id)],
            "institute_id": str(world["abc"].id),
        },
    )


async def test_without_signing_storage_the_browser_is_told_to_upload_through_the_api(
    client: AsyncClient, world
) -> None:
    await _as(client, world["faculty"])
    ticket = await _ticket(client, world)
    assert ticket.status_code == 200, ticket.text
    assert ticket.json()["upload_url"] is None and ticket.json()["file_id"] is None


async def test_a_presigned_upload_is_checked_then_published_under_its_topic(
    client: AsyncClient, db: Db, world, tmp_path, make_user
) -> None:
    storage.set_storage(_SigningStorage(tmp_path))
    await _link(client, world, world["ten_a"], world["c10"])
    await _as(client, world["faculty"])

    ticket = (await _ticket(client, world)).json()
    assert ticket["upload_url"].startswith("https://bucket.test/")
    assert ticket["headers"]["Content-Type"] == "application/pdf"
    stored = await db.get(StoredFile, uuid.UUID(ticket["file_id"]))
    assert stored.status == "pending"

    early = await _filed(client, world, ticket["file_id"])  # the PUT has not happened
    assert early.status_code == 422
    await storage.get_storage().put(stored.storage_key, PDF, "application/pdf")
    filed = await _filed(client, world, ticket["file_id"])
    assert filed.status_code == 201, filed.text
    assert (filed.json()["kind"], filed.json()["status"]) == ("pdf", "published")
    assert (await _filed(client, world, ticket["file_id"])).status_code == 404  # used once
    stored = await db.get(StoredFile, stored.id)
    assert stored.status == "attached" and stored.size == len(PDF) and stored.sha256 != "0" * 64

    await _as(client, world["student_a"])
    download = await client.get(f"/api/v1/files/{ticket['file_id']}")
    assert download.status_code == 200 and download.content == PDF


async def test_a_presigned_upload_that_is_not_what_it_claims_is_deleted(
    client: AsyncClient, db: Db, world, tmp_path, make_user
) -> None:
    storage.set_storage(_SigningStorage(tmp_path))
    await _as(client, world["faculty"])
    wrong_type = await _ticket(client, world, file_name="x.exe", content_type="application/x-exe")
    too_big = await _ticket(client, world, size=10_000 * 1024 * 1024)
    assert [wrong_type.status_code, too_big.status_code] == [422, 422]

    ticket = (await _ticket(client, world)).json()
    stored = await db.get(StoredFile, uuid.UUID(ticket["file_id"]))
    await storage.get_storage().put(stored.storage_key, b"MZ\x90binary", "application/pdf")

    colleague = await make_user("faculty", institute_id=world["abc"].id)
    await _as(client, colleague)
    assert (await _filed(client, world, ticket["file_id"])).status_code == 404  # not theirs

    await _as(client, world["faculty"])
    refused = await _filed(client, world, ticket["file_id"])
    assert refused.status_code == 422
    assert await db.get(StoredFile, stored.id) is None
    assert not (tmp_path / stored.storage_key).exists()
    assert await db.count(ContentItem, {}) == 0


# ------------------------------------------------------------- four-level migration


def _legacy(parent: SyllabusNode | None, kind: str, name: str, **extra) -> SyllabusNode:
    """A node as the old six-level library wrote it — no level rules applied."""
    code = slugify(name)
    return SyllabusNode(
        track="neet",
        parent_id=parent.id if parent else None,
        ancestors=[*parent.ancestors, parent.id] if parent else [],
        kind=kind,
        name=name,
        code=code,
        code_path=f"{parent.code_path}/{code}" if parent else code,
        **extra,
    )


async def test_old_unit_and_chapter_trees_flatten_to_four_levels(db: Db, world, make_user) -> None:
    neet = _legacy(None, "track", "NEET")
    c11 = _legacy(neet, "level", "Class 11")
    bio = _legacy(c11, "subject", "Biology")
    cell = _legacy(bio, "topic", "Cell", order=0)
    physio = _legacy(bio, "unit", "Human Physiology", order=1)
    breathing = _legacy(physio, "chapter", "Breathing", order=0)
    lungs = _legacy(breathing, "topic", "Lungs")
    cell_again = _legacy(physio, "chapter", "Cell", order=1)  # same code as the topic above
    db.add_all([neet, c11, bio, cell, physio, breathing, lungs, cell_again])
    note = ContentItem(
        title="Lungs notes",
        kind="text",
        body="x",
        node_ids=[lungs.id, breathing.id],
        created_by=world["faculty"].id,
        status="published",
    )
    db.add(note)
    db.add(
        ClassSyllabus(class_id=world["ten_a"].id, institute_id=world["abc"].id, node_id=physio.id)
    )
    await db.commit()

    counts = await flatten_to_four_levels()
    again = await flatten_to_four_levels()

    assert counts == {"moved": 2, "archived": 2, "items_relinked": 1, "class_links_moved": 1}
    assert again == {"moved": 0, "archived": 0, "items_relinked": 0, "class_links_moved": 0}
    fresh = {n.id: n for n in await db.find(SyllabusNode, {})}
    assert (fresh[breathing.id].kind, fresh[breathing.id].parent_id) == ("topic", bio.id)
    assert fresh[breathing.id].ancestors == [neet.id, c11.id, bio.id]
    assert fresh[breathing.id].code_path == "neet/class-11/biology/breathing"
    assert fresh[cell_again.id].code_path == "neet/class-11/biology/cell-2"
    assert fresh[cell.id].code_path == "neet/class-11/biology/cell"
    assert {fresh[physio.id].status, fresh[lungs.id].status} == {"archived"}
    assert (await db.get(ContentItem, note.id)).node_ids == [breathing.id]
    link = await db.find_one(ClassSyllabus, {"class_id": world["ten_a"].id})
    assert link.node_id == bio.id
