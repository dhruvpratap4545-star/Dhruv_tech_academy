"""Monthly budget rows, and the alerts sent when one fills up.

A month's row is created the first time it is needed, as a copy of the most recent earlier
month's limits with the counters at zero — so an allocation set once carries forward
without anybody re-entering it on the 1st.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.db import Db, ids_in, utcnow
from app.modules.ai.models import AiBudget
from app.modules.ai.pricing import crossed_thresholds, fullest, month_key

logger = logging.getLogger(__name__)

#: Limits and settings carried from one month to the next. Counters and alerts are not.
_CARRIED = (
    "limit_tokens",
    "limit_paise",
    "on_exceed",
    "feature_limits",
    "disabled_features",
    "enabled",
)


def _match(scope: str, institute_id: uuid.UUID | None, month: str) -> dict[str, Any]:
    return {"scope": scope, "institute_id": institute_id, "month": month}


async def month_budget(
    db: Db,
    scope: str,
    institute_id: uuid.UUID | None,
    *,
    now: datetime | None = None,
    create: bool = True,
) -> AiBudget | None:
    """This month's row, created from last month's settings when it does not exist yet.

    Created with an upsert rather than through the unit of work: two requests on the
    morning of the 1st both find no row, and both must end up with the same one. The
    unique index plus ``$setOnInsert`` makes the second a no-op.
    """
    month = month_key(now or utcnow())
    found = await db.find_one(AiBudget, _match(scope, institute_id, month))
    if found is not None or not create:
        return found

    previous = await db.raw(
        AiBudget,
        {"scope": scope, "institute_id": institute_id, "month": {"$lt": month}},
        dict.fromkeys(_CARRIED, 1),
        sort=[("month", -1)],
    )
    if not previous:
        return None  # never configured: no cap at this level

    carried = {field: previous[0].get(field) for field in _CARRIED if field in previous[0]}
    template = AiBudget(scope=scope, institute_id=institute_id, month=month, **carried)  # type: ignore[arg-type]
    document = template.model_dump(by_alias=True)
    document["_id"] = template.id
    document.pop("id", None)
    # The filter's own fields are written by the upsert from the filter itself.
    for field in ("scope", "institute_id", "month"):
        document.pop(field, None)
    with suppress(DuplicateKeyError):  # lost the race: the row exists now, which is the goal
        await AiBudget.get_pymongo_collection().update_one(
            _match(scope, institute_id, month), {"$setOnInsert": document}, upsert=True
        )
    return await db.find_one(AiBudget, _match(scope, institute_id, month))


def exceeded(budget: AiBudget | None) -> bool:
    if budget is None:
        return False
    if budget.limit_paise is not None and budget.used_paise >= budget.limit_paise:
        return True
    return budget.limit_tokens is not None and budget.used_tokens >= budget.limit_tokens


def feature_exceeded(budget: AiBudget | None, feature_key: str) -> bool:
    if budget is None or feature_key not in budget.feature_limits:
        return False
    return budget.feature_used_paise.get(feature_key, 0) >= budget.feature_limits[feature_key]


def record_spend(db: Db, budget: AiBudget, *, tokens: int, paise: int, feature_key: str) -> None:
    db.increment(
        AiBudget,
        {"_id": budget.id},
        {"used_tokens": tokens, "used_paise": paise, f"feature_used_paise.{feature_key}": paise},
    )


async def admin_recipients(db: Db, institute_id: uuid.UUID | None) -> list[tuple[str, str]]:
    """(email, name) of the people a budget alert goes to.

    Platform owners always; for an institute budget, also that institute's admins and the
    administrators of the organisation it belongs to. Only active accounts.
    """
    from app.modules.org.models import Institute
    from app.modules.rbac import catalog
    from app.modules.rbac.models import Role, UserRoleAssignment
    from app.modules.users.models import User

    roles = {
        r["key"]: r["_id"]
        for r in await db.raw(
            Role,
            {
                "key": ids_in(
                    [
                        catalog.SUPER_ADMIN,
                        catalog.PLATFORM_ADMIN,
                        catalog.INSTITUTE_ADMIN,
                        catalog.ORG_ADMIN,
                    ]
                )
            },
            {"key": 1},
        )
    }
    clauses: list[dict[str, Any]] = [
        {"role_id": ids_in([roles.get(catalog.SUPER_ADMIN), roles.get(catalog.PLATFORM_ADMIN)])}
    ]
    if institute_id is not None:
        clauses.append(
            {"role_id": roles.get(catalog.INSTITUTE_ADMIN), "institute_id": institute_id}
        )
        owner = await db.raw(Institute, {"_id": institute_id}, {"organisation_id": 1})
        organisation_id = owner[0].get("organisation_id") if owner else None
        if organisation_id is not None:
            clauses.append(
                {"role_id": roles.get(catalog.ORG_ADMIN), "organisation_id": organisation_id}
            )
    user_ids = await db.distinct(
        UserRoleAssignment, "user_id", {"revoked_at": None, "$or": clauses}
    )
    users = await db.raw(
        User, {"_id": ids_in(user_ids), "status": "active"}, {"email": 1, "full_name": 1}
    )
    return [(u["email"], u["full_name"]) for u in users]


async def send_threshold_alerts(budget_id: uuid.UUID, thresholds: list[int]) -> None:
    """Email each newly crossed threshold exactly once, ever, for this budget month.

    "Exactly once" under concurrency comes from the database, not from this process: the
    threshold is claimed with a conditional ``$addToSet`` that only matches while the
    threshold is absent. Of two requests crossing 80% together, one update modifies the
    row and sends; the other modifies nothing and does not.
    """
    from app.modules.audit import events
    from app.modules.audit import service as audit
    from app.modules.notifications.email import send_email
    from app.modules.notifications.templates import ai_budget_alert

    collection = AiBudget.get_pymongo_collection()
    raw = await collection.find_one({"_id": budget_id})
    if raw is None:
        return
    used, limit = fullest(
        raw.get("used_paise", 0),
        raw.get("limit_paise"),
        raw.get("used_tokens", 0),
        raw.get("limit_tokens"),
    )
    for threshold in crossed_thresholds(used, limit, thresholds, raw.get("alerts_sent", [])):
        claimed = await collection.update_one(
            {"_id": budget_id, "alerts_sent": {"$ne": threshold}},
            {"$addToSet": {"alerts_sent": threshold}},
        )
        if claimed.modified_count != 1:
            continue
        db = Db()
        label = await _budget_label(db, raw)
        for email, name in await admin_recipients(db, raw.get("institute_id")):
            await send_email(
                ai_budget_alert(
                    email,
                    name,
                    scope_label=label,
                    threshold=threshold,
                    used_paise=raw.get("used_paise", 0),
                    limit_paise=raw.get("limit_paise"),
                    used_tokens=raw.get("used_tokens", 0),
                    limit_tokens=raw.get("limit_tokens"),
                    on_exceed=raw.get("on_exceed", "block"),
                )
            )
        audit.record(
            db,
            action=events.AI_BUDGET_ALERT_SENT,
            target_type="ai_budget",
            target_id=budget_id,
            institute_id=raw.get("institute_id"),
            extra={"threshold": threshold, "month": raw.get("month"), "scope": raw.get("scope")},
        )
        await db.commit()
        logger.info(
            "ai budget alert sent", extra={"threshold": threshold, "budget": str(budget_id)}
        )


async def _budget_label(db: Db, raw: dict[str, Any]) -> str:
    from app.modules.org.models import Institute

    if raw.get("scope") == "platform":
        return f"the platform budget for {raw.get('month')}"
    rows = await db.raw(Institute, {"_id": raw.get("institute_id")}, {"name": 1})
    name = rows[0]["name"] if rows else "an institute"
    return f"{name}'s AI allocation for {raw.get('month')}"
