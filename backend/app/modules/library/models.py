"""Content Library collections (Phase 3, Module B).

Two libraries share these collections. ``institute_id`` null is the **master** library, run
by the Dhruv Academy content team and visible to every institute with the module switched
on. A set ``institute_id`` is that institute's own library, visible to nobody else.

The syllabus is a tree stored as documents. Each node keeps ``ancestors`` — the ids of every
node above it — so "everything under Class 10 Science" is one indexed query on that array
rather than a walk down the tree one level at a time.

Each node also keeps its ``code_path`` ("cbse/class-10/science/light-reflection-and-
refraction"). That path, not the database id, is what the seed and the spreadsheet import
match on, so re-running either updates names and adds what is missing instead of creating
a second copy of the syllabus.

Nothing is deleted: nodes and items are archived.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.core.db import TimestampedDocument, UuidDocument, utcnow

Track = Literal["cbse", "neet", "jee", "upsc", "custom"]
NodeKind = Literal["track", "level", "subject", "unit", "chapter", "topic"]
ItemKind = Literal["pdf", "image", "video_link", "link", "text"]
ItemStatus = Literal["draft", "in_review", "published", "archived"]

TRACKS: tuple[str, ...] = ("cbse", "neet", "jee", "upsc", "custom")
#: Outermost first. A child must sit deeper than its parent; levels may be skipped (a unit
#: is optional, and an exam syllabus may go straight from subject to topic).
KIND_ORDER: tuple[str, ...] = ("track", "level", "subject", "unit", "chapter", "topic")
MEDIUMS: tuple[str, ...] = ("hi", "en")


class SyllabusNode(TimestampedDocument):
    institute_id: uuid.UUID | None = None
    track: Track
    parent_id: uuid.UUID | None = None
    ancestors: list[uuid.UUID] = Field(default_factory=list)
    kind: NodeKind
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=80)
    code_path: str = Field(max_length=600)
    order: int = 0
    mediums: list[str] = Field(default_factory=lambda: list(MEDIUMS))
    difficulty: Literal["easy", "medium", "hard"] | None = None
    exam_tags: list[str] = Field(default_factory=list)
    status: Literal["active", "archived"] = "active"

    class Settings:
        name = "syllabus_nodes"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("parent_id", ASCENDING), ("order", ASCENDING)], name="ix_syllabus_parent_order"
            ),
            IndexModel([("ancestors", ASCENDING)], name="ix_syllabus_ancestors"),
            IndexModel(
                [("institute_id", ASCENDING), ("track", ASCENDING)],
                name="ix_syllabus_institute_track",
            ),
            # One node per path per library: what makes the seed and the import idempotent.
            IndexModel(
                [("code_path", ASCENDING), ("institute_id", ASCENDING)],
                unique=True,
                name="uq_syllabus_path",
            ),
        ]


class ContentItem(TimestampedDocument):
    """One piece of study material, linked to one or more topics or chapters."""

    institute_id: uuid.UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    kind: ItemKind
    file_id: uuid.UUID | None = None
    #: For ``link``: the https URL. For ``video_link``: the canonical watch URL.
    url: str | None = Field(default=None, max_length=500)
    video_provider: Literal["youtube", "vimeo"] | None = None
    video_id: str | None = Field(default=None, max_length=40)
    #: For ``text``: stored as plain text and always rendered escaped, never as HTML.
    body: str | None = Field(default=None, max_length=20_000)
    node_ids: list[uuid.UUID] = Field(default_factory=list)
    medium: Literal["hi", "en", "both"] = "en"
    author: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=200)
    status: ItemStatus = "draft"
    version: int = 1
    created_by: uuid.UUID
    reviewed_by: uuid.UUID | None = None
    review_note: str | None = Field(default=None, max_length=500)
    published_at: datetime | None = None

    class Settings:
        name = "content_items"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("node_ids", ASCENDING)], name="ix_content_items_nodes"),
            IndexModel(
                [("institute_id", ASCENDING), ("status", ASCENDING)],
                name="ix_content_items_institute_status",
            ),
            IndexModel([("created_by", ASCENDING)], name="ix_content_items_creator"),
            IndexModel([("file_id", ASCENDING)], name="ix_content_items_file"),
        ]


class ContentItemVersion(UuidDocument):
    """What an item looked like before an edit made after it was published. Append-only."""

    created_at: datetime = Field(default_factory=utcnow)
    item_id: uuid.UUID
    version: int
    fields: dict[str, Any]
    edited_by: uuid.UUID

    class Settings:
        name = "content_item_versions"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("item_id", ASCENDING), ("version", ASCENDING)],
                unique=True,
                name="uq_content_item_versions",
            ),
        ]


class ClassSyllabus(TimestampedDocument):
    """A class uses a part of the syllabus — usually a level node such as "CBSE › Class 10".

    Students and parents see only the subtrees linked to their classes.
    """

    class_id: uuid.UUID
    institute_id: uuid.UUID
    node_id: uuid.UUID

    class Settings:
        name = "class_syllabus"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("class_id", ASCENDING), ("node_id", ASCENDING)],
                unique=True,
                name="uq_class_syllabus",
            ),
            IndexModel([("institute_id", ASCENDING)], name="ix_class_syllabus_institute"),
            IndexModel([("node_id", ASCENDING)], name="ix_class_syllabus_node"),
        ]


#: Every collection this module owns, registered in `core.db.document_models()`.
MODELS: list[type[Document]] = [SyllabusNode, ContentItem, ContentItemVersion, ClassSyllabus]
