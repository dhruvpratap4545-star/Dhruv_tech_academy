"""Homework Board endpoints (``/api/v1/homework``). Resolve, authorise, delegate, commit.

Literal paths (``/mine``, ``/children/…``, ``/reports/…``) are declared before the
``/{homework_id}`` routes, so a word is never read as an id.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
)

from app.core.pagination import Page, clamp_limit
from app.modules.auth.service import RequestMeta
from app.modules.homework import reports, schemas
from app.modules.homework import service as homework_service
from app.modules.notifications.email import EmailMessage, send_email
from app.modules.rbac.deps import DbSession, client_ip, require_permission, user_agent
from app.modules.rbac.service import Authorized

router = APIRouter()

Manage = Annotated[Authorized, Depends(require_permission("homework:manage"))]
Read = Annotated[Authorized, Depends(require_permission("homework:read"))]
Submit = Annotated[Authorized, Depends(require_permission("homework:submit"))]
Report = Annotated[Authorized, Depends(require_permission("homework:report"))]
Tab = Literal["pending", "submitted", "checked", "overdue"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _meta(request: Request) -> RequestMeta:
    return RequestMeta(ip=client_ip(request), user_agent=user_agent(request))


def _send_all(background: BackgroundTasks, messages: list[EmailMessage]) -> None:
    """One background task for the whole batch, so a class of sixty is one job, not sixty."""
    if not messages:
        return

    async def deliver() -> None:
        for message in messages:
            await send_email(message)

    background.add_task(deliver)


async def _one(db, homework) -> schemas.HomeworkOut:
    return (await homework_service.present(db, [homework]))[0]


# ------------------------------------------------------------------- student and parent


@router.get(
    "/mine",
    response_model=list[schemas.StudentHomeworkOut],
    summary="A student's homework board, soonest due first",
)
async def my_board(
    db: DbSession, guard: Submit, tab: Tab | None = None
) -> list[schemas.StudentHomeworkOut]:
    return await homework_service.my_board(db, guard=guard, tab=tab)


@router.get(
    "/children/{student_id}",
    response_model=list[schemas.StudentHomeworkOut],
    summary="A parent's view of one linked child's homework",
    description="404 unless you are a recorded guardian of this learner.",
)
async def child_board(
    student_id: uuid.UUID, db: DbSession, guard: Read, tab: Tab | None = None
) -> list[schemas.StudentHomeworkOut]:
    return await homework_service.child_board(db, guard=guard, student_id=student_id, tab=tab)


# ------------------------------------------------------------------------------ reports


@router.get(
    "/reports/summary",
    response_model=schemas.ReportOut,
    summary="Completion rate by class, subject and teacher",
)
async def report_summary(
    db: DbSession,
    guard: Report,
    class_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    institute_id: uuid.UUID | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> schemas.ReportOut:
    return await reports.summary(
        db,
        guard=guard,
        class_id=class_id,
        branch_id=branch_id,
        institute_id=institute_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/reports/export", summary="Download the homework report as Excel")
async def report_export(
    db: DbSession,
    guard: Report,
    class_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    institute_id: uuid.UUID | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Response:
    data = await reports.export(
        db,
        guard=guard,
        class_id=class_id,
        branch_id=branch_id,
        institute_id=institute_id,
        date_from=date_from,
        date_to=date_to,
    )
    return Response(
        content=data,
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="homework-report.xlsx"'},
    )


# ---------------------------------------------------------------------- teacher, admin


@router.post("", response_model=schemas.HomeworkOut, status_code=201, summary="Set homework")
async def create_homework(
    payload: schemas.HomeworkCreate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    guard: Manage,
) -> schemas.HomeworkOut:
    homework, messages = await homework_service.create_homework(
        db, guard=guard, payload=payload, meta=_meta(request)
    )
    await db.commit()
    _send_all(background, messages)
    return await _one(db, homework)


@router.get("", response_model=Page[schemas.HomeworkOut], summary="List homework in your reach")
async def list_homework(
    db: DbSession,
    guard: Read,
    class_id: uuid.UUID | None = None,
    institute_id: uuid.UUID | None = None,
    status: Literal["draft", "published", "archived"] | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[schemas.HomeworkOut]:
    rows, next_cursor, total = await homework_service.list_homework(
        db,
        guard=guard,
        class_id=class_id,
        institute_id=institute_id,
        status=status,
        cursor=cursor,
        limit=clamp_limit(limit),
    )
    return Page[schemas.HomeworkOut](
        items=await homework_service.present(db, rows), next_cursor=next_cursor, total=total
    )


@router.get(
    "/{homework_id}",
    response_model=schemas.StudentHomeworkOut,
    summary="One homework; for a student, with their own submission",
    description="A parent gets their linked child's submission; ``student_id`` picks the "
    "child (404 unless linked and enrolled in the class).",
)
async def get_homework(
    homework_id: uuid.UUID, db: DbSession, guard: Read, student_id: uuid.UUID | None = None
) -> schemas.StudentHomeworkOut:
    return await homework_service.get_homework_detail(
        db, context=guard.context, homework_id=homework_id, student_id=student_id
    )


@router.patch("/{homework_id}", response_model=schemas.HomeworkOut, summary="Edit homework")
async def update_homework(
    homework_id: uuid.UUID,
    payload: schemas.HomeworkUpdate,
    request: Request,
    db: DbSession,
    guard: Manage,
) -> schemas.HomeworkOut:
    homework = await homework_service.update_homework(
        db, guard=guard, homework_id=homework_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return await _one(db, homework)


@router.post(
    "/{homework_id}/publish",
    response_model=schemas.HomeworkOut,
    summary="Publish now, or schedule for later",
)
async def publish_homework(
    homework_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    guard: Manage,
    payload: schemas.PublishRequest | None = None,
) -> schemas.HomeworkOut:
    homework, messages = await homework_service.publish_homework(
        db,
        guard=guard,
        homework_id=homework_id,
        payload=payload or schemas.PublishRequest(),
        meta=_meta(request),
    )
    await db.commit()
    _send_all(background, messages)
    return await _one(db, homework)


@router.post(
    "/{homework_id}/archive",
    response_model=schemas.HomeworkOut,
    summary="Archive homework (nothing is deleted)",
)
async def archive_homework(
    homework_id: uuid.UUID, request: Request, db: DbSession, guard: Manage
) -> schemas.HomeworkOut:
    homework = await homework_service.archive_homework(
        db, guard=guard, homework_id=homework_id, meta=_meta(request)
    )
    await db.commit()
    return await _one(db, homework)


@router.post(
    "/{homework_id}/duplicate",
    response_model=schemas.HomeworkOut,
    status_code=201,
    summary="Copy as a new draft, optionally into another class you teach",
)
async def duplicate_homework(
    homework_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Manage,
    payload: schemas.DuplicateRequest | None = None,
) -> schemas.HomeworkOut:
    homework = await homework_service.duplicate_homework(
        db,
        guard=guard,
        homework_id=homework_id,
        payload=payload or schemas.DuplicateRequest(),
        meta=_meta(request),
    )
    await db.commit()
    return await _one(db, homework)


@router.post(
    "/{homework_id}/attachments",
    response_model=schemas.HomeworkOut,
    summary="Attach PDFs or images (at most five in total)",
)
async def add_attachments(
    homework_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Manage,
    files: Annotated[list[UploadFile], File(description="PDF, JPG or PNG; 10 MB each.")],
) -> schemas.HomeworkOut:
    homework = await homework_service.add_attachments(
        db, guard=guard, homework_id=homework_id, uploads=files, meta=_meta(request)
    )
    await db.commit()
    return await _one(db, homework)


@router.get(
    "/{homework_id}/tracker",
    response_model=schemas.TrackerOut,
    summary="Every enrolled student and where they are with this homework",
)
async def tracker(homework_id: uuid.UUID, db: DbSession, guard: Manage) -> schemas.TrackerOut:
    return await homework_service.tracker(db, guard=guard, homework_id=homework_id)


@router.post(
    "/{homework_id}/remind",
    response_model=schemas.RemindOut,
    summary="Email students who have not submitted (once per six hours)",
)
async def remind(
    homework_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    guard: Manage,
) -> schemas.RemindOut:
    messages = await homework_service.remind(
        db, guard=guard, homework_id=homework_id, meta=_meta(request)
    )
    await db.commit()
    _send_all(background, messages)
    return schemas.RemindOut(sent=len(messages))


@router.get(
    "/{homework_id}/share-text",
    response_model=schemas.ShareTextOut,
    summary="WhatsApp share text: title, class, due date and a link — no names or marks",
)
async def share_text(homework_id: uuid.UUID, db: DbSession, guard: Manage) -> schemas.ShareTextOut:
    return await homework_service.share_text(db, guard=guard, homework_id=homework_id)


@router.get(
    "/{homework_id}/submissions/{submission_id}",
    response_model=schemas.SubmissionOut,
    summary="One student's submission",
)
async def get_submission(
    homework_id: uuid.UUID, submission_id: uuid.UUID, db: DbSession, guard: Manage
) -> schemas.SubmissionOut:
    return await homework_service.get_submission(
        db, guard=guard, homework_id=homework_id, submission_id=submission_id
    )


@router.post(
    "/{homework_id}/submissions/{submission_id}/check",
    response_model=schemas.SubmissionOut,
    summary="Give marks, a grade and a remark — or send it back for a redo",
)
async def check_submission(
    homework_id: uuid.UUID,
    submission_id: uuid.UUID,
    payload: schemas.CheckRequest,
    request: Request,
    db: DbSession,
    guard: Manage,
) -> schemas.SubmissionOut:
    submission = await homework_service.check_submission(
        db,
        guard=guard,
        homework_id=homework_id,
        submission_id=submission_id,
        payload=payload,
        meta=_meta(request),
    )
    await db.commit()
    return (await homework_service.present_submissions(db, [submission], with_names=True))[0]


@router.put(
    "/{homework_id}/submission",
    response_model=schemas.SubmissionOut,
    summary="Submit or resubmit: a typed answer and/or up to five photos or PDFs",
)
async def submit(
    homework_id: uuid.UUID,
    request: Request,
    db: DbSession,
    guard: Submit,
    text: Annotated[str, Form(max_length=10_000)] = "",
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> schemas.SubmissionOut:
    submission = await homework_service.submit(
        db,
        guard=guard,
        homework_id=homework_id,
        text=text,
        uploads=files or [],
        meta=_meta(request),
    )
    await db.commit()
    return (await homework_service.present_submissions(db, [submission]))[0]
