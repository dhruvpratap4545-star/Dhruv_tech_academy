"""Keyset (cursor) pagination.

OFFSET pagination degrades linearly: page 500 makes the database walk 10,000 rows it then
throws away, and rows shifting between requests cause duplicates and gaps. Keyset paging
asks for "the next N rows after this exact position", which is one index seek regardless of
depth and is stable while the table changes underneath.

The sort key is ``(created_at, _id)``. ``created_at`` alone is not unique, so ``id`` breaks
ties and makes the ordering total — without it a page boundary landing inside a group of
rows sharing a timestamp would skip or repeat records.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from beanie import Document
from pydantic import BaseModel, Field

from app.core.db import Db
from app.core.errors import ValidationFailed

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class Page[T](BaseModel):
    """Envelope for every list endpoint (PRD §8)."""

    items: list[T]
    next_cursor: str | None = Field(
        default=None,
        description="Pass back as `cursor` for the next page. Null means this is the last page.",
    )
    total: int = Field(
        default=0,
        description="How many rows match the current filters in total, across every page. "
        "Lets a screen say 'Page 3 of 7' and 'Showing 41-60 of 134' instead of leaving "
        "the reader to click Next until it stops.",
    )


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    """Opaque by design: callers must not construct or parse these, so we are free to
    change the sort key later without breaking anyone."""
    raw = json.dumps({"t": created_at.astimezone(UTC).isoformat(), "i": str(row_id)})
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return datetime.fromisoformat(data["t"]), uuid.UUID(data["i"])
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        # Never echo the cursor back — it is attacker-controlled input.
        raise ValidationFailed(
            "That page link is not valid. Please start from the first page."
        ) from exc


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1:
        raise ValidationFailed("`limit` must be at least 1.")
    return min(limit, MAX_LIMIT)


def keyset_filter(cursor: str | None, *, descending: bool = True) -> dict[str, Any]:
    """The condition that seeks past ``cursor`` on ``(created_at, _id)``.

    Strict lexicographic comparison: the same timestamp falls back to the id, so no
    document is ever visited twice or skipped.
    """
    if not cursor:
        return {}
    after_time, after_id = decode_cursor(cursor)
    op = "$lt" if descending else "$gt"
    return {
        "$or": [
            {"created_at": {op: after_time}},
            {"created_at": after_time, "_id": {op: after_id}},
        ]
    }


async def paginate[D: Document](
    db: Db,
    model: type[D],
    match: dict[str, Any],
    *,
    cursor: str | None,
    limit: int,
    descending: bool = True,
    include_total: bool = True,
) -> tuple[list[D], str | None, int]:
    """Count, seek, fetch and trim — the whole of one page, in one call.

    The count is taken over ``match`` *before* the cursor condition is added, so it stays
    the total for the filters rather than "everything after row 60". One document more
    than ``limit`` is fetched so the caller can tell whether another page exists.

    ``include_total=False`` skips the count for callers that throw it away. Global search is
    the one that matters: it fires on every keystroke over a case-insensitive *contains*
    match that cannot use an index, and counting the matches as well as fetching the first
    ten doubles the cost of the most latency-sensitive query in the application.
    """
    total = await db.count(model, match) if include_total else 0
    seek = keyset_filter(cursor, descending=descending)
    windowed = {"$and": [match, seek]} if seek and match else (seek or match)
    direction = -1 if descending else 1
    rows = await db.find(
        model,
        windowed,
        sort=[("created_at", direction), ("_id", direction)],
        limit=limit + 1,
    )
    page, next_cursor = split_page(rows, limit)
    return page, next_cursor, total


def split_page(rows: list[Any], limit: int) -> tuple[list[Any], str | None]:
    """Trim the sentinel row and build the cursor for the next page."""
    if len(rows) <= limit:
        return rows, None
    page = rows[:limit]
    last = page[-1]
    return page, encode_cursor(last.created_at, last.id)
