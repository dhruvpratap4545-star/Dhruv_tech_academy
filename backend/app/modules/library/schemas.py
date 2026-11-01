"""Request and response bodies for the Content Library. Input and output kept apart."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.library.models import ItemKind, NodeKind, Track


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


Medium = Literal["hi", "en"]
Difficulty = Literal["easy", "medium", "hard"]


# -------------------------------------------------------------------------------- nodes


class NodeOut(OrmModel):
    id: uuid.UUID
    institute_id: uuid.UUID | None
    track: str
    parent_id: uuid.UUID | None
    kind: str
    name: str
    code: str
    order: int
    mediums: list[str]
    difficulty: str | None
    exam_tags: list[str]
    status: str
    #: Filled where it matters for browsing: does this node have children to open?
    child_count: int = 0


class Crumb(BaseModel):
    id: uuid.UUID
    name: str
    kind: str


class NodeDetail(BaseModel):
    node: NodeOut
    breadcrumb: list[Crumb]
    children: list[NodeOut]


class NodeCreate(StrictModel):
    parent_id: uuid.UUID | None = None
    #: Omit for the master library (platform only). Ignored when it must follow the parent.
    institute_id: uuid.UUID | None = None
    track: Track | None = None
    kind: NodeKind
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=80)
    mediums: list[Medium] = Field(default_factory=lambda: ["hi", "en"], min_length=1)
    difficulty: Difficulty | None = None
    exam_tags: list[str] = Field(default_factory=list, max_length=10)


class NodeUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    mediums: list[Medium] | None = Field(default=None, min_length=1)
    difficulty: Difficulty | None = None
    exam_tags: list[str] | None = Field(default=None, max_length=10)


class NodeReorder(StrictModel):
    #: The node's new position among its siblings, counting from 0.
    position: int = Field(ge=0, le=10_000)


# --------------------------------------------------------------------------------- items


class FileInfo(OrmModel):
    id: uuid.UUID
    original_name: str
    content_type: str
    size: int


class ItemOut(OrmModel):
    id: uuid.UUID
    institute_id: uuid.UUID | None
    title: str
    kind: str
    file_id: uuid.UUID | None
    file: FileInfo | None = None
    url: str | None
    video_provider: str | None
    video_id: str | None
    body: str | None
    node_ids: list[uuid.UUID]
    medium: str
    author: str | None
    source: str | None
    status: str
    version: int
    created_by: uuid.UUID
    reviewed_by: uuid.UUID | None
    review_note: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ItemCreate(StrictModel):
    """JSON body for link, video link and text material. Files go to ``/items/upload``."""

    institute_id: uuid.UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    kind: Literal["video_link", "link", "text"]
    url: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=20_000)
    node_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    medium: Literal["hi", "en", "both"] = "en"
    author: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=200)


class ItemUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=20_000)
    node_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=20)
    medium: Literal["hi", "en", "both"] | None = None
    author: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=200)


class ReviewNote(StrictModel):
    note: str | None = Field(default=None, max_length=500)


class VersionOut(OrmModel):
    id: uuid.UUID
    item_id: uuid.UUID
    version: int
    fields: dict
    edited_by: uuid.UUID
    created_at: datetime


ItemKindFilter = ItemKind


# ---------------------------------------------------------------------------- search, my


class SearchNodeHit(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    track: str
    path: str


class SearchItemHit(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    medium: str
    status: str


class SearchResults(BaseModel):
    query: str
    nodes: list[SearchNodeHit]
    items: list[SearchItemHit]


class LinkedNode(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    track: str
    path: str


class ClassSyllabusOut(BaseModel):
    class_id: uuid.UUID
    class_name: str
    nodes: list[LinkedNode]


class ClassSyllabusUpdate(StrictModel):
    node_ids: list[uuid.UUID] = Field(max_length=20)

    @field_validator("node_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))


class MySyllabusOut(BaseModel):
    """One entry per class the reader belongs to; a parent gets one per child's class."""

    class_id: uuid.UUID
    class_name: str
    student_user_id: uuid.UUID | None = None
    student_name: str | None = None
    nodes: list[LinkedNode]


# -------------------------------------------------------------------------------- import


class ImportProblem(BaseModel):
    row: int
    messages: list[str]


class ImportResult(BaseModel):
    dry_run: bool
    rows_total: int
    rows_valid: int
    problems: list[ImportProblem]
    created: int
    updated: int
    unchanged: int
    by_kind: dict[str, int]
