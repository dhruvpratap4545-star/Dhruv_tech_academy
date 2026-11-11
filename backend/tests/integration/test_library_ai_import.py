"""Reading a syllabus PDF into the library with AI, end to end.

The fake provider stands in for Gemini: it answers a structured request with a fixed
outline, so these tests check the platform's side — permissions, the AI controls, the
review step and the import — not the model's reading.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.db import Db
from app.modules.ai.models import AiFeature, AiUsage
from app.modules.ai.providers import ProviderRequest, ProviderResult
from app.modules.ai.providers.fake import FakeProvider
from app.modules.library.models import SyllabusNode
from app.modules.rbac.models import InstituteModule

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
OUTLINE = {
    "papers": ["Physics", "Chemistry"],
    "levels": [
        {
            "name": "Semester 1",
            "subjects": [
                {
                    "name": "Physics",
                    "units": [{"name": "Unit 1: Optics", "topics": ["Reflection", "Refraction"]}],
                },
                {
                    "name": "Chemistry",
                    "units": [{"name": "Unit 1: Bonding", "topics": ["Ionic bonds"]}],
                },
            ],
        }
    ],
}


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture(autouse=True)
def outline_answer(monkeypatch: pytest.MonkeyPatch) -> list[ProviderRequest]:
    """Answer structured requests with ``OUTLINE``; record every request made."""
    seen: list[ProviderRequest] = []

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        seen.append(request)
        return ProviderResult(json.dumps(OUTLINE), input_tokens=4000, output_tokens=200)

    monkeypatch.setattr(FakeProvider, "complete", complete)
    return seen


@pytest_asyncio.fixture
async def world(db: Db, institute, make_user):
    abc, _ = await institute("ABC College", "ABC", with_branch="MAIN")
    for key in ("ai", "library"):
        db.add(InstituteModule(institute_id=abc.id, module_key=key, enabled=True))
    await db.commit()
    return {
        "abc": abc,
        "admin": await make_user("institute_admin", institute_id=abc.id),
        "faculty": await make_user("faculty", institute_id=abc.id),
    }


async def _read(client: AsyncClient, world, **fields):
    form = {"track": "custom", "institute_id": str(world["abc"].id), "medium": "English"}
    form.update(fields)
    return await client.post(
        "/api/v1/library/import/ai",
        data=form,
        files={"file": ("syllabus.pdf", PDF, "application/pdf")},
    )


async def test_a_pdf_becomes_reviewable_rows_and_nothing_is_saved(
    client: AsyncClient, db: Db, world, outline_answer
) -> None:
    await _as(client, world["admin"])

    response = await _read(client, world, level="B.Sc Sem 1", exam_tags="bsc")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(r["level"], r["subject"], r["topic"]) for r in body["rows"]] == [
        ("B.Sc Sem 1", "Physics", "Reflection"),
        ("B.Sc Sem 1", "Physics", "Refraction"),
        ("B.Sc Sem 1", "Chemistry", "Ionic bonds"),
    ]
    assert all(r["problems"] == [] and r["exam_tags"] == "bsc" for r in body["rows"])
    assert body["missing_papers"] == []
    assert body["cost_paise"] > 0
    # The document went to the provider as a file, with the outline schema.
    (request,) = outline_answer
    assert request.attachments[0].content_type == "application/pdf"
    assert request.json_schema is not None
    # Logged against the institute like any AI use; no syllabus node written yet.
    usage = await db.find_one(AiUsage, {"feature_key": "syllabus_import"})
    assert usage is not None and usage.institute_id == world["abc"].id
    assert await db.count(SyllabusNode, {"institute_id": world["abc"].id}) == 0


async def test_reviewed_rows_preview_then_import(client: AsyncClient, db: Db, world) -> None:
    await _as(client, world["admin"])
    rows = (await _read(client, world)).json()["rows"]
    rows[0]["topic"] = "Reflection of light"  # the reviewer's correction
    payload = {"institute_id": str(world["abc"].id), "rows": rows}

    preview = await client.post("/api/v1/library/import/rows", json=payload)
    applied = await client.post("/api/v1/library/import/rows?dry_run=false", json=payload)

    assert preview.status_code == 200, preview.text
    assert preview.json()["rows_valid"] == 3
    assert await db.count(SyllabusNode, {"name": "Reflection of light"}) == 1
    assert applied.json()["dry_run"] is False
    assert applied.json()["by_kind"]["topic"] == 3


async def test_reviewed_rows_download_as_the_import_template(client: AsyncClient, world) -> None:
    await _as(client, world["admin"])
    rows = (await _read(client, world)).json()["rows"]

    response = await client.post("/api/v1/library/import/rows/xlsx", json={"rows": rows})

    assert response.status_code == 200
    assert response.content[:2] == b"PK"  # an .xlsx is a zip


async def test_invalid_rows_are_reported_not_imported(client: AsyncClient, db: Db, world) -> None:
    await _as(client, world["admin"])
    payload = {
        "institute_id": str(world["abc"].id),
        "rows": [{"track": "custom", "level": "Sem 1", "subject": "हिंदी", "medium": "Both"}],
    }

    response = await client.post("/api/v1/library/import/rows?dry_run=false", json=payload)

    assert response.json()["rows_valid"] == 0
    assert "English" in response.json()["problems"][0]["messages"][0]
    assert await db.count(SyllabusNode, {"institute_id": world["abc"].id}) == 0


async def test_faculty_cannot_import(client: AsyncClient, world) -> None:
    await _as(client, world["faculty"])

    assert (await _read(client, world)).status_code == 403


async def test_switching_the_ai_feature_off_stops_it(client: AsyncClient, db: Db, world) -> None:
    switched = await AiFeature.get_pymongo_collection().update_one(
        {"key": "syllabus_import"}, {"$set": {"enabled": False}}
    )
    assert switched.modified_count == 1
    await _as(client, world["admin"])

    response = await _read(client, world)

    assert response.status_code != 200
    assert "switched off" in response.json()["error"]["message"]


async def test_only_pdf_and_images_are_read(client: AsyncClient, world) -> None:
    await _as(client, world["admin"])

    response = await client.post(
        "/api/v1/library/import/ai",
        data={"track": "custom", "institute_id": str(world["abc"].id)},
        files={"file": ("notes.docx", b"PK\x03\x04 not a pdf", "application/msword")},
    )

    assert response.status_code == 422
