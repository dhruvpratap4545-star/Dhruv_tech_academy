"""Homework Board collections (Phase 3, Module C).

A homework belongs to one class and carries ``institute_id`` and ``branch_id`` copied from
it, so every list is a plain equality filter and tenant isolation never depends on a lookup.

What a *student* sees as the status — Pending, Overdue, Submitted, Checked, Redo — is not
stored anywhere. It is derived from the homework's due date and the submission, when it is
read (``homework/status.py``). A stored "overdue" flag would need a job to flip it at the
due time, and Cloud Run has no cron; deriving it needs nothing.

Homework is archived, never deleted, so reports and history stay complete.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.core.db import TimestampedDocument

HomeworkStatus = Literal["draft", "published", "archived"]
SubmissionStatus = Literal["submitted", "checked", "redo"]

MAX_FILES = 5


class Homework(TimestampedDocument):
    institute_id: uuid.UUID
    branch_id: uuid.UUID
    class_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=80)
    #: Optional link to a chapter or topic in the Content Library.
    node_id: uuid.UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    instructions: str = Field(default="", max_length=10_000)
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_FILES)
    medium: str | None = Field(default=None, max_length=20)
    total_marks: int | None = Field(default=None, ge=0, le=1000)
    #: When students can first see it. Set on publish; in the future means "scheduled".
    publish_at: datetime | None = None
    due_at: datetime
    allow_late: bool = True
    allow_resubmit: bool = True
    status: HomeworkStatus = "draft"
    created_by: uuid.UUID
    #: For the reminder rate limit: one reminder per homework per six hours.
    last_reminded_at: datetime | None = None

    class Settings:
        name = "homework"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("class_id", ASCENDING), ("status", ASCENDING), ("due_at", ASCENDING)],
                name="ix_homework_class_status_due",
            ),
            IndexModel(
                [("institute_id", ASCENDING), ("created_at", DESCENDING), ("_id", DESCENDING)],
                name="ix_homework_institute_created",
            ),
            IndexModel([("created_by", ASCENDING)], name="ix_homework_created_by"),
        ]


class HomeworkSubmission(TimestampedDocument):
    """One student's answer to one homework. Resubmitting updates this document; the
    attempt count and the audit log keep the history."""

    homework_id: uuid.UUID
    class_id: uuid.UUID
    institute_id: uuid.UUID
    student_user_id: uuid.UUID
    text: str = Field(default="", max_length=10_000)
    file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_FILES)
    submitted_at: datetime
    is_late: bool = False
    attempts: int = Field(default=1, ge=1)
    status: SubmissionStatus = "submitted"
    marks: float | None = Field(default=None, ge=0)
    grade: str | None = Field(default=None, max_length=10)
    remark: str | None = Field(default=None, max_length=2000)
    checked_by: uuid.UUID | None = None
    checked_at: datetime | None = None

    class Settings:
        name = "homework_submissions"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("homework_id", ASCENDING), ("student_user_id", ASCENDING)],
                unique=True,
                name="uq_homework_submissions_homework_student",
            ),
            IndexModel(
                [("student_user_id", ASCENDING), ("status", ASCENDING)],
                name="ix_homework_submissions_student_status",
            ),
            IndexModel(
                [("homework_id", ASCENDING), ("status", ASCENDING)],
                name="ix_homework_submissions_homework_status",
            ),
        ]


#: Every collection this module owns, registered in `core.db.document_models()`.
MODELS: list[type[Document]] = [Homework, HomeworkSubmission]
