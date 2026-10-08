"""Audit log reading (PRD §8). Writing happens inside the services that own each action."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.pagination import Page, clamp_limit
from app.modules.audit import events, schemas
from app.modules.audit import service as audit
from app.modules.rbac.deps import DbSession, require_permission
from app.modules.rbac.service import Authorized

router = APIRouter()


@router.get(
    "",
    response_model=Page[schemas.AuditLogOut],
    summary="Read the audit history for your scope",
    description="Platform staff see every event. Institute and branch admins see only "
    "events recorded against institutes they administer.",
)
async def list_audit_logs(
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("audit:read"))],
    action: Annotated[str | None, Query(max_length=40)] = None,
    actor_user_id: uuid.UUID | None = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[schemas.AuditLogOut]:
    size = clamp_limit(limit)
    institute_ids = guard.visible_institute_ids()
    rows, next_cursor = await audit.list_logs(
        db,
        institute_ids=institute_ids,
        action=action,
        actor_user_id=actor_user_id,
        cursor=cursor,
        limit=size,
    )
    return Page[schemas.AuditLogOut](
        items=[schemas.AuditLogOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )


@router.get(
    "/stats",
    response_model=schemas.SigninStats,
    summary="Daily sign-in activity for your scope",
    description="Successful sign-ins, failures and lockouts per day. Days are counted in "
    "Indian time. Scoped exactly like the audit list.",
)
async def signin_stats(
    db: DbSession,
    guard: Annotated[Authorized, Depends(require_permission("audit:read"))],
    days: Annotated[int, Query(ge=1, le=90, description="How many days back to count.")] = 14,
) -> schemas.SigninStats:
    institute_ids = guard.visible_institute_ids()
    rows = await audit.daily_signin_counts(db, institute_ids=institute_ids, days=days)

    counts: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for day, action, count in rows:
        counts[day][action] = count

    today = datetime.now(audit.IST).date()
    series = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        bucket = counts.get(day, {})
        series.append(
            schemas.DailySignins(
                day=day,
                successful=bucket.get(events.LOGIN_SUCCESS, 0),
                failed=bucket.get(events.LOGIN_FAILURE, 0),
                locked=bucket.get(events.ACCOUNT_LOCKED, 0),
            )
        )

    return schemas.SigninStats(
        days=series,
        total_successful=sum(d.successful for d in series),
        total_failed=sum(d.failed for d in series),
        total_locked=sum(d.locked for d in series),
    )
