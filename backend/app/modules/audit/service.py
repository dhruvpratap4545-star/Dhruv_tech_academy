"""Audit writer and reader (PRD §7.6).

Writes join the caller's unit of work deliberately. If the action fails, its audit entry is
discarded with it — an audit log that records things which did not happen is worse than
none. The flip side is that the audit row must never be the reason a request fails, so
``record`` only stages the insert; the service that owns the use case commits.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Final

from app.core.db import Db, ids_in, utcnow
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
    db: Db,
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
) -> dict[str, Any]:
    match: dict[str, Any] = {}
    # None means platform staff: every entry, including platform-level ones with no institute.
    if institute_ids is not None:
        match["institute_id"] = ids_in(institute_ids)
    if action:
        match["action"] = action
    if actor_user_id:
        match["actor_user_id"] = actor_user_id
    return match


async def list_logs(
    db: Db,
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    action: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[Sequence[AuditLog], str | None, int]:
    return await paginate(
        db,
        AuditLog,
        _visible_logs(institute_ids=institute_ids, action=action, actor_user_id=actor_user_id),
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
IST_OFFSET: Final = "+05:30"


async def daily_signin_counts(
    db: Db,
    *,
    institute_ids: frozenset[uuid.UUID] | None,
    days: int,
) -> list[tuple[date, str, int]]:
    """(day, action, count) for the last ``days`` days, scoped like the audit list itself.

    One grouped aggregation rather than one query per day. It rides the
    ``(action, created_at)`` index: equality on the three actions, range on the timestamp.
    Days are cut at Indian midnight by formatting each timestamp at the +05:30 offset.
    """
    first_day = datetime.now(IST).date() - timedelta(days=int(days) - 1)
    since = datetime.combine(first_day, time.min, tzinfo=IST)

    match: dict[str, Any] = {
        "action": {"$in": list(SIGNIN_ACTIONS)},
        "created_at": {"$gte": since, "$lte": utcnow()},
    }
    if institute_ids is not None:
        match["institute_id"] = ids_in(institute_ids)

    rows = await db.aggregate(
        AuditLog,
        [
            {"$match": match},
            {
                "$group": {
                    "_id": {
                        "day": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$created_at",
                                "timezone": IST_OFFSET,
                            }
                        },
                        "action": "$action",
                    },
                    "n": {"$sum": 1},
                }
            },
            {"$sort": {"_id.day": 1}},
        ],
    )
    return [(date.fromisoformat(r["_id"]["day"]), r["_id"]["action"], int(r["n"])) for r in rows]
