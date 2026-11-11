"""Content Library endpoints (``/api/v1/library``). Resolve, authorise, delegate, commit.

Material is created through two routes rather than one that sniffs its content type:
``POST /items`` takes JSON for links, videos and text notes, and ``POST /items/upload``
takes multipart for a PDF or image. One route per body shape keeps each one's validation
and OpenAPI description honest.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

from app.core.errors import ValidationFailed
from app.core.pagination import Page, clamp_limit
from app.modules.auth.service import RequestMeta
from app.modules.library import ai_import, schemas, spreadsheet
from app.modules.library import service as library
from app.modules.library.models import ItemStatus, Track
from app.modules.rbac.deps import DbSession, client_ip, require_permission, user_agent
from app.modules.rbac.service import Authorized

router = APIRouter()

Read = Annotated[Authorized, Depends(require_permission("library:read"))]
Contribute = Annotated[Authorized, Depends(require_permission("library:contribute"))]
Manage = Annotated[Authorized, Depends(require_permission("library:manage"))]
Publish = Annotated[Authorized, Depends(require_permission("library:publish"))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#: A syllabus spreadsheet of 5,000 rows is well under a megabyte; anything near this is
#: not a syllabus.
MAX_IMPORT_BYTES = 5 * 1024 * 1024


def _meta(request: Request) -> RequestMeta:
    return RequestMeta(ip=client_ip(request), user_agent=user_agent(request))


# -------------------------------------------------------------------------------- nodes


@router.get("/tracks", response_model=list[schemas.NodeOut], summary="Top of the syllabus tree")
async def list_tracks(db: DbSession, guard: Read) -> list[schemas.NodeOut]:
    return await library.list_nodes(db, guard=guard, parent_id=None)


@router.get(
    "/nodes",
    response_model=list[schemas.NodeOut],
    summary="Browse the tree one level at a time",
    description="Without `parent_id`, the tracks. Archived nodes only for staff who ask.",
)
async def list_nodes(
    db: DbSession,
    guard: Read,
    parent_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[schemas.NodeOut]:
    return await library.list_nodes(
        db, guard=guard, parent_id=parent_id, include_archived=include_archived
    )


@router.get("/nodes/{node_id}", response_model=schemas.NodeDetail, summary="A node and its path")
async def get_node(node_id: uuid.UUID, db: DbSession, guard: Read) -> schemas.NodeDetail:
    return await library.get_node(db, guard=guard, node_id=node_id)


@router.post("/nodes", response_model=schemas.NodeOut, status_code=201, summary="Add a node")
async def create_node(
    payload: schemas.NodeCreate, request: Request, db: DbSession, guard: Manage
) -> schemas.NodeOut:
    node = await library.create_node(db, guard=guard, payload=payload, meta=_meta(request))
    await db.commit()
    return schemas.NodeOut.model_validate(node)


@router.patch("/nodes/{node_id}", response_model=schemas.NodeOut, summary="Edit a node")
async def update_node(
    node_id: uuid.UUID,
    payload: schemas.NodeUpdate,
    request: Request,
    db: DbSession,
    guard: Manage,
) -> schemas.NodeOut:
    node = await library.update_node(
        db, guard=guard, node_id=node_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.NodeOut.model_validate(node)


@router.post(
    "/nodes/{node_id}/archive",
    response_model=schemas.NodeOut,
    summary="Archive a node and everything under it",
    description="Refused with 409 while any part of it still has material that is not archived.",
)
async def archive_node(
    node_id: uuid.UUID, request: Request, db: DbSession, guard: Manage
) -> schemas.NodeOut:
    node = await library.archive_node(db, guard=guard, node_id=node_id, meta=_meta(request))
    await db.commit()
    return schemas.NodeOut.model_validate(node)


@router.post(
    "/nodes/{node_id}/reorder",
    response_model=list[schemas.NodeOut],
    summary="Move a node to a new position among its siblings",
)
async def reorder_node(
    node_id: uuid.UUID,
    payload: schemas.NodeReorder,
    request: Request,
    db: DbSession,
    guard: Manage,
) -> list[schemas.NodeOut]:
    siblings = await library.reorder_node(
        db, guard=guard, node_id=node_id, position=payload.position, meta=_meta(request)
    )
    await db.commit()
    return [schemas.NodeOut.model_validate(s) for s in siblings]


# ------------------------------------------------------------------------------- import


@router.get("/import/template", summary="Download the syllabus import template")
async def import_template(guard: Manage) -> Response:
    return Response(
        content=spreadsheet.template(),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="syllabus-template.xlsx"'},
    )


@router.post(
    "/import",
    response_model=schemas.ImportResult,
    summary="Preview or apply a syllabus spreadsheet",
    description="`dry_run=true` (the default) changes nothing and reports what would happen, "
    "row by row. Matching is on track and code path, so re-importing a file is safe.",
)
async def import_syllabus(
    request: Request,
    db: DbSession,
    guard: Manage,
    file: Annotated[UploadFile, File(description="The .xlsx file")],
    institute_id: Annotated[uuid.UUID | None, Form()] = None,
    dry_run: Annotated[bool, Query()] = True,
) -> schemas.ImportResult:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise ValidationFailed("That spreadsheet is too large. Please split it.")
    result = await library.import_syllabus(
        db, guard=guard, data=data, institute_id=institute_id, dry_run=dry_run, meta=_meta(request)
    )
    if not dry_run:
        await db.commit()
    return result


@router.post(
    "/import/ai",
    response_model=schemas.AiExtractResult,
    summary="Read a syllabus PDF or photo into import rows, with AI",
    description="Nothing is saved: the rows come back for review, then go to "
    "`POST /import/rows`. Runs as the `syllabus_import` AI feature, so the AI switches, "
    "budgets and daily limits apply and the call appears in the usage log.",
)
async def import_with_ai(
    db: DbSession,
    guard: Manage,
    file: Annotated[UploadFile, File(description="The syllabus: PDF, JPG or PNG")],
    track: Annotated[Track, Form()],
    institute_id: Annotated[uuid.UUID | None, Form()] = None,
    level: Annotated[str | None, Form(max_length=120)] = None,
    medium: Annotated[str, Form(pattern="^(Hindi|English|Both)$")] = "Both",
    difficulty: Annotated[str, Form(pattern="^(|Easy|Medium|Hard)$")] = "",
    exam_tags: Annotated[str, Form(max_length=200)] = "",
) -> schemas.AiExtractResult:
    return await ai_import.extract(
        db,
        guard=guard,
        upload=file,
        track=track,
        institute_id=institute_id,
        level_hint=(level or "").strip() or None,
        medium=medium,
        difficulty=difficulty,
        exam_tags=exam_tags,
    )


@router.post(
    "/import/rows",
    response_model=schemas.ImportResult,
    summary="Preview or apply reviewed rows",
    description="The JSON form of `POST /import`, for rows reviewed on screen. Same checks, "
    "same matching on track and code path, `dry_run=true` by default.",
)
async def import_rows(
    request: Request,
    db: DbSession,
    guard: Manage,
    payload: schemas.ImportRowsIn,
    dry_run: Annotated[bool, Query()] = True,
) -> schemas.ImportResult:
    result = await library.import_rows(
        db,
        guard=guard,
        cells=[row.model_dump(exclude={"problems"}) for row in payload.rows],
        institute_id=payload.institute_id,
        dry_run=dry_run,
        meta=_meta(request),
    )
    if not dry_run:
        await db.commit()
    return result


@router.post("/import/rows/xlsx", summary="Download reviewed rows as an import spreadsheet")
async def rows_to_excel(guard: Manage, payload: schemas.RowsToExcelIn) -> Response:
    return Response(
        content=spreadsheet.write_rows([row.model_dump() for row in payload.rows]),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="syllabus-from-ai.xlsx"'},
    )


# ------------------------------------------------------------------------------- search


@router.get("/search", response_model=schemas.SearchResults, summary="Search topics and material")
async def search(
    db: DbSession,
    guard: Read,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    track: Track | None = None,
    class_id: uuid.UUID | None = None,
    kind: Annotated[str | None, Query(max_length=20)] = None,
    medium: Annotated[str | None, Query(pattern="^(hi|en|both)$")] = None,
) -> schemas.SearchResults:
    return await library.search(
        db, guard=guard, q=q, track=track, class_id=class_id, kind=kind, medium=medium
    )


# -------------------------------------------------------------------------------- items


@router.get("/items", response_model=Page[schemas.ItemOut], summary="Material on a topic")
async def list_items(
    db: DbSession,
    guard: Read,
    node_id: uuid.UUID | None = None,
    status: ItemStatus | None = None,
    mine: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[schemas.ItemOut]:
    rows, next_cursor, total = await library.list_items(
        db,
        guard=guard,
        node_id=node_id,
        status=status,
        mine=mine,
        cursor=cursor,
        limit=clamp_limit(limit),
    )
    return Page[schemas.ItemOut](
        items=await library.item_outs(db, rows), next_cursor=next_cursor, total=total
    )


@router.get("/items/{item_id}", response_model=schemas.ItemOut, summary="One piece of material")
async def get_item(item_id: uuid.UUID, db: DbSession, guard: Read) -> schemas.ItemOut:
    item = await library.get_item(db, guard=guard, item_id=item_id)
    return (await library.item_outs(db, [item]))[0]


@router.post(
    "/items",
    response_model=schemas.ItemOut,
    status_code=201,
    summary="Add a link, video link or text note (as a draft)",
)
async def create_item(
    payload: schemas.ItemCreate, request: Request, db: DbSession, guard: Contribute
) -> schemas.ItemOut:
    item = await library.create_item(db, guard=guard, payload=payload, meta=_meta(request))
    await db.commit()
    return (await library.item_outs(db, [item]))[0]


@router.post(
    "/items/upload",
    response_model=schemas.ItemOut,
    status_code=201,
    summary="Upload a PDF or image as material (as a draft)",
)
async def upload_item(
    request: Request,
    db: DbSession,
    guard: Contribute,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(max_length=200)],
    node_ids: Annotated[list[uuid.UUID], Form()],
    institute_id: Annotated[uuid.UUID | None, Form()] = None,
    medium: Annotated[str, Form()] = "en",
    author: Annotated[str | None, Form(max_length=120)] = None,
    source: Annotated[str | None, Form(max_length=200)] = None,
) -> schemas.ItemOut:
    item = await library.upload_item(
        db,
        guard=guard,
        upload=file,
        institute_id=institute_id,
        title=title,
        node_ids=node_ids,
        medium=medium,
        author=author,
        source=source,
        meta=_meta(request),
    )
    await db.commit()
    return (await library.item_outs(db, [item]))[0]


@router.patch("/items/{item_id}", response_model=schemas.ItemOut, summary="Edit material")
async def update_item(
    item_id: uuid.UUID,
    payload: schemas.ItemUpdate,
    request: Request,
    db: DbSession,
    guard: Contribute,
) -> schemas.ItemOut:
    item = await library.update_item(
        db, guard=guard, item_id=item_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return (await library.item_outs(db, [item]))[0]


@router.post("/items/{item_id}/submit", response_model=schemas.ItemOut, summary="Send for review")
async def submit_item(
    item_id: uuid.UUID, request: Request, db: DbSession, guard: Contribute
) -> schemas.ItemOut:
    item = await library.submit_item(db, guard=guard, item_id=item_id, meta=_meta(request))
    await db.commit()
    return (await library.item_outs(db, [item]))[0]


@router.post("/items/{item_id}/publish", response_model=schemas.ItemOut, summary="Publish")
async def publish_item(
    item_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Publish,
    payload: schemas.ReviewNote | None = None,
) -> schemas.ItemOut:
    item = await library.publish_item(
        db,
        guard=guard,
        item_id=item_id,
        note=payload.note if payload else None,
        meta=_meta(request),
    )
    await db.commit()
    return (await library.item_outs(db, [item]))[0]


@router.post(
    "/items/{item_id}/reject",
    response_model=schemas.ItemOut,
    summary="Send back to the author as a draft, with a note",
)
async def reject_item(
    item_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Publish,
    payload: schemas.ReviewNote | None = None,
) -> schemas.ItemOut:
    item = await library.reject_item(
        db,
        guard=guard,
        item_id=item_id,
        note=payload.note if payload else None,
        meta=_meta(request),
    )
    await db.commit()
    return (await library.item_outs(db, [item]))[0]


@router.post("/items/{item_id}/archive", response_model=schemas.ItemOut, summary="Archive")
async def archive_item(
    item_id: uuid.UUID, request: Request, db: DbSession, guard: Manage
) -> schemas.ItemOut:
    item = await library.archive_item(db, guard=guard, item_id=item_id, meta=_meta(request))
    await db.commit()
    return (await library.item_outs(db, [item]))[0]


@router.get(
    "/items/{item_id}/versions",
    response_model=list[schemas.VersionOut],
    summary="Earlier versions of published material",
)
async def list_versions(
    item_id: uuid.UUID, db: DbSession, guard: Contribute
) -> list[schemas.VersionOut]:
    rows = await library.list_versions(db, guard=guard, item_id=item_id)
    return [schemas.VersionOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------- class syllabus


@router.get(
    "/classes/{class_id}/syllabus",
    response_model=schemas.ClassSyllabusOut,
    summary="Which parts of the syllabus a class uses",
)
async def get_class_syllabus(
    class_id: uuid.UUID, db: DbSession, guard: Read
) -> schemas.ClassSyllabusOut:
    return await library.get_class_syllabus(db, guard=guard, class_id=class_id)


@router.put(
    "/classes/{class_id}/syllabus",
    response_model=schemas.ClassSyllabusOut,
    summary="Link a class to parts of the syllabus (needs class:update)",
)
async def set_class_syllabus(
    class_id: uuid.UUID,
    payload: schemas.ClassSyllabusUpdate,
    request: Request,
    db: DbSession,
    guard: Read,
) -> schemas.ClassSyllabusOut:
    await library.set_class_syllabus(
        db, guard=guard, class_id=class_id, node_ids=payload.node_ids, meta=_meta(request)
    )
    await db.commit()
    return await library.get_class_syllabus(db, guard=guard, class_id=class_id)


@router.get(
    "/my",
    response_model=list[schemas.MySyllabusOut],
    summary="Your classes' syllabus (a parent: each child's)",
)
async def my_syllabus(db: DbSession, guard: Read) -> list[schemas.MySyllabusOut]:
    return await library.my_syllabus(db, guard=guard)
