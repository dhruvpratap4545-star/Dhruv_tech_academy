"""Request and response bodies for the Homework Board. Input and output kept apart."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.ai.pricing import IST
from app.modules.files.schemas import FileOut

Medium = Literal["en", "hi", "bilingual"]
PublishMode = Literal["draft", "now", "schedule"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _assume_ist(value: datetime | None) -> datetime | None:
    """A date and time typed without a zone is Indian time — every user is in India."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=IST)
    return value


class HomeworkCreate(StrictModel):
    class_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=80)
    node_id: uuid.UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    instructions: str = Field(default="", max_length=10_000)
    medium: Medium | None = None
    total_marks: int | None = Field(default=None, ge=0, le=1000)
    #: ``draft`` saves it; ``now`` publishes it; ``schedule`` publishes at ``publish_at``.
    publish: PublishMode = "draft"
    publish_at: datetime | None = None
    due_at: datetime
    allow_late: bool = True
    allow_resubmit: bool = True

    _ist = field_validator("publish_at", "due_at")(_assume_ist)


class HomeworkUpdate(StrictModel):
    subject: str | None = Field(default=None, min_length=1, max_length=80)
    node_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    instructions: str | None = Field(default=None, max_length=10_000)
    medium: Medium | None = None
    total_marks: int | None = Field(default=None, ge=0, le=1000)
    due_at: datetime | None = None
    publish_at: datetime | None = None
    allow_late: bool | None = None
    allow_resubmit: bool | None = None
    #: A subset of the current attachments, to remove some. New files go through
    #: ``POST /{id}/attachments``.
    attachment_ids: list[uuid.UUID] | None = Field(default=None, max_length=5)

    _ist = field_validator("publish_at", "due_at")(_assume_ist)


class PublishRequest(StrictModel):
    #: Omit to publish now.
    publish_at: datetime | None = None

    _ist = field_validator("publish_at")(_assume_ist)


class DuplicateRequest(StrictModel):
    #: Copy into another class you teach. Omit for the same class.
    class_id: uuid.UUID | None = None


class HomeworkOut(BaseModel):
    id: uuid.UUID
    institute_id: uuid.UUID
    branch_id: uuid.UUID
    class_id: uuid.UUID
    class_name: str
    subject: str
    node_id: uuid.UUID | None
    title: str
    instructions: str
    attachments: list[FileOut]
    medium: str | None
    total_marks: int | None
    publish_at: datetime | None
    due_at: datetime
    allow_late: bool
    allow_resubmit: bool
    status: str
    #: Published and its publish time has arrived: students can see it.
    is_visible: bool
    created_by: uuid.UUID
    created_at: datetime


class SubmissionOut(BaseModel):
    id: uuid.UUID
    homework_id: uuid.UUID
    student_user_id: uuid.UUID
    student_name: str | None = None
    text: str
    files: list[FileOut]
    submitted_at: datetime
    is_late: bool
    attempts: int
    status: str
    marks: float | None
    grade: str | None
    remark: str | None
    checked_at: datetime | None


class StudentHomeworkOut(BaseModel):
    """One row on a student's (or a parent's) board."""

    homework: HomeworkOut
    student_status: str
    submission: SubmissionOut | None


class CheckRequest(StrictModel):
    marks: float | None = Field(default=None, ge=0, le=1000)
    grade: str | None = Field(default=None, max_length=10)
    remark: str | None = Field(default=None, max_length=2000)
    #: Send it back to the student instead of marking it checked.
    redo: bool = False


class TrackerRow(BaseModel):
    student_user_id: uuid.UUID
    full_name: str
    roll_no: str | None
    student_status: str
    submission_id: uuid.UUID | None
    submitted_at: datetime | None
    is_late: bool
    marks: float | None


class TrackerOut(BaseModel):
    homework_id: uuid.UUID
    counts: dict[str, int]
    late: int
    rows: list[TrackerRow]


class RemindOut(BaseModel):
    sent: int


class ShareTextOut(BaseModel):
    text: str
    url: str
    whatsapp_url: str


class ReportRow(BaseModel):
    key: str | None
    label: str
    homework: int
    expected: int
    submitted: int
    late: int
    completion_rate: float


class ReportOut(BaseModel):
    date_from: date | None
    date_to: date | None
    totals: ReportRow
    by_class: list[ReportRow]
    by_subject: list[ReportRow]
    by_teacher: list[ReportRow]
