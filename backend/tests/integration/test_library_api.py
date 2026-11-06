"""Content Library end to end (Phase 3, Module B).

Covers client acceptance items 4 (the syllabus trees are searchable down to topic level)
and 5 (a PDF and a video link are uploaded, linked to a topic, reviewed and published, and
are then visible only to students of the linked class).
"""

from __future__ import annotations

import io
from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from openpyxl import Workbook

from app.core.db import Db
from app.modules.audit.models import AuditLog
from app.modules.library.models import ContentItem, ContentItemVersion, SyllabusNode
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
    sci10 = writer.ensure(c10, track="cbse", kind="subject", name="Science")
    elec = writer.ensure(sci10, track="cbse", kind="chapter", name="Electricity")
    ohm = writer.ensure(elec, track="cbse", kind="topic", name="Ohm's Law")
    c9 = writer.ensure(cbse, track="cbse", kind="level", name="Class 9")
    sci9 = writer.ensure(c9, track="cbse", kind="subject", name="Science")
    motion = writer.ensure(sci9, track="cbse", kind="chapter", name="Motion")
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
    """Faculty uploads a PDF and a video on Ohm's Law; the institute admin publishes both."""
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
    pdf_id, video_id = pdf.json()["id"], video.json()["id"]

    for item_id in (pdf_id, video_id):
        denied = await client.post(f"/api/v1/library/items/{item_id}/publish")
        assert denied.status_code == 403  # faculty contribute; they do not publish
        assert (await client.post(f"/api/v1/library/items/{item_id}/submit")).status_code == 200

    await _as(client, world["abc_admin"])
    for item_id in (pdf_id, video_id):
        published = await client.post(f"/api/v1/library/items/{item_id}/publish")
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "published"
    return pdf_id, video_id, pdf.json()["file_id"]


# ------------------------------------------------------------------- acceptance item 5


async def test_material_is_reviewed_published_and_visible_only_to_the_linked_class(
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

    assert await db.count(AuditLog, {"action": "library_item_published"}) == 2


async def test_drafts_are_seen_by_staff_but_never_by_students(client: AsyncClient, world) -> None:
    await _link(client, world, world["ten_a"], world["c10"])
    await _as(client, world["faculty"])
    draft = await client.post(
        "/api/v1/library/items",
        json={
            "institute_id": str(world["abc"].id),
            "title": "Draft note",
            "kind": "text",
            "body": "<script>alert(1)</script> V = IR",
            "node_ids": [str(world["ohm"].id)],
        },
    )
    item_id = draft.json()["id"]
    assert draft.json()["body"] == "<script>alert(1)</script> V = IR"  # stored as plain text

    await _as(client, world["abc_admin"])
    assert (await client.get(f"/api/v1/library/items/{item_id}")).status_code == 200
    await _as(client, world["student_a"])
    assert (await client.get(f"/api/v1/library/items/{item_id}")).status_code == 404
    await _as(client, world["xyz_admin"])
    assert (await client.get(f"/api/v1/library/items/{item_id}")).status_code == 404


async def test_review_rejects_back_to_draft_and_edits_after_publishing_keep_versions(
    client: AsyncClient, db: Db, world
) -> None:
    _, video_id, _ = await _published_pair(client, world)

    await _as(client, world["faculty"])
    not_theirs = await client.patch(f"/api/v1/library/items/{video_id}", json={"title": "Mine now"})
    assert not_theirs.status_code == 403  # published: only a manager edits it

    await _as(client, world["abc_admin"])
    edited = await client.patch(
        f"/api/v1/library/items/{video_id}", json={"title": "Ohm's Law, explained again"}
    )
    versions = await client.get(f"/api/v1/library/items/{video_id}/versions")
    assert edited.json()["version"] == 2 and edited.json()["status"] == "published"
    assert [v["version"] for v in versions.json()] == [1]
    assert versions.json()[0]["fields"]["title"] == "Ohm's Law explained"

    await _as(client, world["faculty"])
    note = await client.post(
        "/api/v1/library/items",
        json={
            "institute_id": str(world["abc"].id),
            "title": "Needs work",
            "kind": "link",
            "url": "https://ncert.nic.in/textbook.php",
            "node_ids": [str(world["ohm"].id)],
        },
    )
    await client.post(f"/api/v1/library/items/{note.json()['id']}/submit")
    await _as(client, world["abc_admin"])
    rejected = await client.post(
        f"/api/v1/library/items/{note.json()['id']}/reject", json={"note": "Add the source"}
    )
    assert rejected.json()["status"] == "draft"
    assert rejected.json()["review_note"] == "Add the source"
    assert await db.count(ContentItemVersion, {}) == 1


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
        "Electricity",
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


async def test_faculty_cannot_manage_the_tree(client: AsyncClient, world) -> None:
    await _as(client, world["faculty"])
    response = await client.post(
        "/api/v1/library/nodes",
        json={
            "parent_id": str(world["elec"].id),
            "institute_id": str(world["abc"].id),
            "kind": "topic",
            "name": "X",
        },
    )
    assert response.status_code == 403


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
    children = (await client.get(f"/api/v1/library/nodes?parent_id={world['c10'].id}")).json()
    sci = children[0]["id"]
    assert (await client.get(f"/api/v1/library/nodes?parent_id={sci}")).json() == []


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
        ("cbse", "Ohm's Law"),
        ("neet", "Human Physiology"),
        ("jee", "Rotational Motion"),
        ("upsc", "Probity in Governance"),
    ):
        body = (await client.get(f"/api/v1/library/search?q={query}&track={track}")).json()
        hits[track] = body["nodes"]
        assert body["nodes"], track

    ohm = next(n for n in hits["cbse"] if n["kind"] == "topic")
    assert ohm["path"].startswith("CBSE › Class 10 › Science › Electricity")
    assert any(n["kind"] == "topic" for n in hits["upsc"])


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
    assert results["cbse"]["by_kind"]["topic"] > 400


# ------------------------------------------------------------------------------ import


def _sheet(rows: list[list[str]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(
        [
            "Track",
            "Level",
            "Subject",
            "Unit",
            "Chapter",
            "Topic",
            "Medium",
            "Difficulty",
            "Exam tags",
        ]
    )
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
            ["State Board", "Class 1", "Maths", "", "", "", "", "", ""],
            ["CUSTOM", "Class 8", "Science", "", "Light", "Reflection", "Hindi", "Easy", "board"],
            ["Custom", "Class 8", "Science", "", "Light", "Refraction", "Both", "", ""],
            ["Custom", "", "", "", "", "", "", "", ""],
        ]
    )
    upload = {"file": ("syllabus.xlsx", data, "application/octet-stream")}
    await _as(client, world["platform"])

    preview = (await client.post("/api/v1/library/import", files=upload)).json()
    before = await db.count(SyllabusNode, {"track": "custom"})
    applied = (await client.post("/api/v1/library/import?dry_run=false", files=upload)).json()
    again = (await client.post("/api/v1/library/import?dry_run=false", files=upload)).json()

    assert preview["dry_run"] is True and preview["created"] == 6
    assert before == 0
    assert (preview["rows_total"], preview["rows_valid"]) == (4, 2)
    assert [p["row"] for p in preview["problems"]] == [2, 5]
    assert applied["created"] == 6
    assert again["created"] == 0
    reflection = await db.find_one(SyllabusNode, {"name": "Reflection"})
    assert reflection.code_path == "custom/class-8/science/light/reflection"
    assert reflection.mediums == ["hi"] and reflection.difficulty == "easy"
    assert reflection.exam_tags == ["board"]


async def test_institute_admin_imports_into_their_own_library_only(
    client: AsyncClient, db: Db, world
) -> None:
    data = _sheet(
        [
            ["CBSE", "Class 10", "Science", "", "Electricity", "Ohm's Law", "", "", ""],
            ["CBSE", "Class 10", "Science", "", "Electricity", "Power at Home", "", "", ""],
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


async def test_faculty_see_published_and_their_own_material_but_not_colleagues_drafts(
    client: AsyncClient, world, make_user
) -> None:
    colleague = await make_user("faculty", institute_id=world["abc"].id)
    note = {
        "institute_id": str(world["abc"].id),
        "kind": "text",
        "body": "V = IR",
        "node_ids": [str(world["ohm"].id)],
    }
    pdf_id, _, _ = await _published_pair(client, world)
    await _as(client, colleague)
    theirs = (await client.post("/api/v1/library/items", json={**note, "title": "Theirs"})).json()
    review = (await client.post("/api/v1/library/items", json={**note, "title": "Review"})).json()
    assert (await client.post(f"/api/v1/library/items/{review['id']}/submit")).status_code == 200

    await _as(client, world["faculty"])
    own = (await client.post("/api/v1/library/items", json={**note, "title": "Own"})).json()
    page = await client.get("/api/v1/library/items?limit=100")
    listed = {i["id"] for i in page.json()["items"]}
    assert own["id"] in listed and pdf_id in listed
    assert theirs["id"] not in listed and review["id"] not in listed
    assert (await client.get(f"/api/v1/library/items/{theirs['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/library/items/{review['id']}")).status_code == 404
    assert (await client.post(f"/api/v1/library/items/{own['id']}/submit")).status_code == 200
    assert (await client.get(f"/api/v1/library/nodes/{world['ohm'].id}")).status_code == 200

    await _as(client, world["abc_admin"])
    for item_id in (theirs["id"], review["id"], own["id"]):
        assert (await client.get(f"/api/v1/library/items/{item_id}")).status_code == 200


async def test_import_matches_existing_children_by_name_and_never_renames(
    client: AsyncClient, db: Db, world
) -> None:
    writer = TreeWriter(db, None)
    await writer.load("cbse")
    maths = writer.ensure(world["c10"], track="cbse", kind="subject", name="Mathematics", code="m")
    await db.commit()
    db.update_many(SyllabusNode, {"_id": world["cbse"].id}, {"name": "CBSE (Board)"})
    await db.commit()

    data = _sheet([["CBSE", "class 10", " MATHEMATICS ", "", "Algebra", "", "", "", ""]])
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
    client: AsyncClient, world, make_user
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

    teacher = world["faculty"]
    await _as(client, world["platform"])
    promoted = await client.post(
        f"/api/v1/users/{teacher.id}/roles",
        json={"role_key": "institute_admin", "institute_id": str(world["xyz"].id)},
    )
    assert promoted.status_code == 201, promoted.text

    await _as(client, teacher)
    assert (await client.get(f"/api/v1/library/items/{draft.json()['id']}")).status_code == 404
