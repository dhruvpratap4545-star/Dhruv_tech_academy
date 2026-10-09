"""Keyset (cursor) pagination.

OFFSET pagination degrades linearly: page 500 makes PostgreSQL walk 10,000 rows it then
throws away, and rows shifting between requests cause duplicates and gaps. Keyset paging
asks for "the next N rows after this exact position", which is one index seek regardless of
depth and is stable while the table changes underneath.

The sort key is ``(created_at, id)``. ``created_at`` alone is not unique, so ``id`` breaks
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

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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


def apply_keyset(
    stmt: Select[Any],
    *,
    created_at_col: ColumnElement[datetime],
    id_col: ColumnElement[uuid.UUID],
    cursor: str | None,
    limit: int,
    descending: bool = True,
) -> Select[Any]:
    """Order the statement and seek past the cursor.

    One row more than ``limit`` is fetched so the caller can tell whether another page
    exists without a second COUNT query. Use :func:`split_page` to trim it.
    """
    if cursor:
        after_time, after_id = decode_cursor(cursor)
        # Strict lexicographic comparison on (created_at, id): same timestamp falls back
        # to the id, so no row is ever visited twice or skipped.
        if descending:
            stmt = stmt.where(
                or_(
                    created_at_col < after_time,
                    and_(created_at_col == after_time, id_col < after_id),
                )
            )
        else:
            stmt = stmt.where(
                or_(
                    created_at_col > after_time,
                    and_(created_at_col == after_time, id_col > after_id),
                )
            )

    order = (created_at_col.desc(), id_col.desc()) if descending else (created_at_col, id_col)
    return stmt.order_by(*order).limit(limit + 1)


async def count_matching(db: AsyncSession, stmt: Select[Any]) -> int:
    """How many rows the filters match in total, ignoring the page window.

    Keyset paging gives no total of its own — that is the trade for its speed, and it is
    why "Next" is the only control a cursor-paged list can honestly offer. A separate
    COUNT buys back "page 3 of 7", which is what people actually want from a list of
    users: a sense of how much there is, and the ability to jump.

    The cost is one extra aggregate per request over the same filtered set. At this
    product's scale that is a few milliseconds; if a table ever grows past the point where
    it is not, the fix is an estimate for large results, not removing the number.

    Ordering, limit and offset are stripped first: they change nothing about the count, and
    PostgreSQL rejects ORDER BY inside the subquery when the sort column is not selected.
    """
    counted = stmt.order_by(None).limit(None).offset(None)
    return await db.scalar(select(func.count()).select_from(counted.subquery())) or 0


async def paginate(
    db: AsyncSession,
    stmt: Select[Any],
    *,
    created_at_col: ColumnElement[datetime],
    id_col: ColumnElement[uuid.UUID],
    cursor: str | None,
    limit: int,
    descending: bool = True,
    include_total: bool = True,
) -> tuple[list[Any], str | None, int]:
    """Count, seek, fetch and trim — the whole of one page, in one call.

    The count is taken from ``stmt`` *before* the cursor condition is added, so it stays
    the total for the filters rather than "everything after row 60".

    ``include_total=False`` skips the aggregate for callers that throw it away. Global
    search is the one that matters: it fires on every keystroke over an ``ILIKE '%term%'``
    that cannot use an index, and counting the matches as well as fetching the first ten
    doubles the cost of the most latency-sensitive query in the application, to produce a
    number nothing displays.
    """
    total = await count_matching(db, stmt) if include_total else 0
    windowed = apply_keyset(
        stmt,
        created_at_col=created_at_col,
        id_col=id_col,
        cursor=cursor,
        limit=limit,
        descending=descending,
    )
    rows = list((await db.execute(windowed)).scalars().all())
    page, next_cursor = split_page(rows, limit)
    return page, next_cursor, total


def split_page(rows: list[Any], limit: int) -> tuple[list[Any], str | None]:
    """Trim the sentinel row and build the cursor for the next page."""
    if len(rows) <= limit:
        return rows, None
    page = rows[:limit]
    last = page[-1]
    return page, encode_cursor(last.created_at, last.id)
