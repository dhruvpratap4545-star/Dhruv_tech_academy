"""Audit writer and reader (PRD §7.6).

Writes join the caller's transaction deliberately. If the action rolls back, its audit row
rolls back with it — an audit log that records things which did not happen is worse than
none. The flip side is that the audit row must never be the reason a request fails, so
``record`` only stages the insert; the service that owns the use case commits.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta, timezone
from typing import Any, Final

from sqlalchemy import Select, func, select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import current_request_id
from app.core.pagination import paginate
from app.modules.audit import events
from app.modules.audit.models import AuditLog

# Keys that must never reach the audit metadata, whatever a caller passes.
_FORBIDDEN_KEYS = frozenset(
    {
        "password",
        "new_password",
        "current_password",
        "otp",
        "code",
        "token",
        "access_token",
        "refresh_token",
        "password_hash",
        "otp_hash",
        "authorization",
        "cookie",
    }
)


def _scrub(extra: dict[str, Any] | None) -> dict[str, Any] | None:
    """Last line of defence before a secret is written to a permanent table.

    The real protection is callers not passing secrets, but audit rows are forever and this
    costs one dict comprehension.
    """
    if not extra:
        return None
    cleaned = {k: v for k, v in extra.items() if k.lower() not in _FORBIDDEN_KEYS}
    return cleaned or None


def record(
    db: AsyncSession,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    institute_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AuditLog:
    """Stage an audit row. Not a coroutine — nothing is flushed until the caller commits."""
    entry = AuditLog(
        action=action,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        institute_id=institute_id,
        ip=ip,
        user_agent=user_agent,
        extra=_scrub(extra),
        request_id=current_request_id(),
    )
    db.add(entry)
    return entry


def _visible_logs(
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    action: str | None,
    actor_user_id: uuid.UUID | None,
) -> Select[tuple[AuditLog]]:
    stmt = select(AuditLog)
    # None means platform staff: every row, including platform-level rows with no institute.
    if institute_ids is not None:
        stmt = stmt.where(AuditLog.institute_id.in_(institute_ids))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    return stmt


async def list_logs(
    db: AsyncSession,
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    action: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[AuditLog], str | None, int]:
    return await paginate(
        db,
        _visible_logs(institute_ids=institute_ids, action=action, actor_user_id=actor_user_id),
        created_at_col=AuditLog.created_at,
        id_col=AuditLog.id,
        cursor=cursor,
        limit=limit,
    )


# --------------------------------------------------------------------- sign-in reporting

SIGNIN_ACTIONS: Final = (events.LOGIN_SUCCESS, events.LOGIN_FAILURE, events.ACCOUNT_LOCKED)

# Days are bucketed in Indian time, not UTC. Every user of this platform is in India, and a
# sign-in at 02:00 IST belongs to that morning as they experienced it — bucketing in UTC
# would file it under the previous day and make the chart disagree with the audit list
# sitting right next to it.
#
# A fixed offset rather than ``ZoneInfo("Asia/Kolkata")``: India has never observed daylight
# saving, so the two are identical in every case, and the fixed offset needs no system
# timezone database. ``zoneinfo`` raises on a bare Windows install and on slim container
# images that drop tzdata — a dashboard is not worth that failure mode.
REPORT_TIMEZONE: Final = "Asia/Kolkata"
IST: Final = timezone(timedelta(hours=5, minutes=30))


async def daily_signin_counts(
    db: AsyncSession,
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    days: int,
) -> list[tuple[date, str, int]]:
    """(day, action, count) for the last ``days`` days, scoped like the audit list itself.

    One grouped query rather than one per day. It rides the baseline's
    ``(action, created_at)`` index: equality on the three actions, range on the timestamp.
    """
    local_day = func.date_trunc("day", func.timezone(REPORT_TIMEZONE, AuditLog.created_at))
    since = func.timezone(REPORT_TIMEZONE, func.now()) - sa_text(f"interval '{int(days) - 1} days'")

    stmt = (
        select(local_day.label("day"), AuditLog.action, func.count())
        .where(
            AuditLog.action.in_(SIGNIN_ACTIONS),
            func.timezone(REPORT_TIMEZONE, AuditLog.created_at) >= func.date_trunc("day", since),
        )
        .group_by(local_day, AuditLog.action)
        .order_by(local_day)
    )
    if institute_ids is not None:
        stmt = stmt.where(AuditLog.institute_id.in_(institute_ids))

    rows = await db.execute(stmt)
    return [(day.date(), action, int(count)) for day, action, count in rows.all()]
