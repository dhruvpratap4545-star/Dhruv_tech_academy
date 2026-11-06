"""AI Control Room use cases: settings, models, features, budgets, limits and usage.

Who may do what:

* ``ai:manage`` is platform-only. Providers, models, prices, the platform budget, each
  institute's allocation and every kill switch belong to Dhruv Academy, whose money it is.
* ``ai:usage_read`` lets an institute's administrators see their own usage and allocation,
  share that allocation between features, switch features off for their school, and
  *lower* (never raise) the daily limits for their institute.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from app.core.db import Db, ids_in, utcnow
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import paginate
from app.modules.ai import budgets as budget_repo
from app.modules.ai import schemas
from app.modules.ai.models import (
    ANSWERED,
    SETTINGS_KEY,
    AiBudget,
    AiFeature,
    AiModel,
    AiRoleLimit,
    AiSettings,
    AiUsage,
)
from app.modules.ai.pricing import IST, fullest, month_key, percent_used, start_of_ist_day
from app.modules.ai.providers import PROVIDER_NAMES
from app.modules.ai.seed import ROLE_LIMITS, UNLISTED_ROLE_LIMIT
from app.modules.audit import events
from app.modules.audit import service as audit
from app.modules.auth.service import RequestMeta
from app.modules.org.models import Institute
from app.modules.rbac import service as rbac
from app.modules.rbac.scopes import Scope
from app.modules.rbac.service import Authorized

IST_OFFSET = "+05:30"
EXPORT_MAX_ROWS = 50_000


def _audit(
    db: Db,
    guard: Authorized,
    meta: RequestMeta,
    action: str,
    *,
    target_type: str,
    target_id: uuid.UUID | None = None,
    institute_id: uuid.UUID | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action=action,
        actor_user_id=guard.user_id,
        target_type=target_type,
        target_id=target_id,
        institute_id=institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra=extra,
    )


def _is_platform_manager(guard: Authorized) -> bool:
    return guard.context.can("ai:manage", Scope())


# ----------------------------------------------------------------------------- settings


async def get_settings(db: Db) -> AiSettings:
    found = await db.find_one(AiSettings, {"key": SETTINGS_KEY})
    if found is None:
        found = AiSettings()
        db.add(found)
    return found


async def update_settings(
    db: Db, *, guard: Authorized, payload: schemas.SettingsUpdate, meta: RequestMeta
) -> AiSettings:
    await guard.ensure(Scope())
    row = await get_settings(db)
    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changed.items():
        setattr(row, field, value)
    row.updated_by = guard.user_id
    _audit(db, guard, meta, events.AI_SETTINGS_UPDATED, target_type="ai_settings", extra=changed)
    return row


def list_providers() -> list[schemas.ProviderOut]:
    from app.core.config import settings
    from app.modules.ai.providers.anthropic import AnthropicProvider
    from app.modules.ai.providers.gemini import GeminiProvider

    configured = {
        "gemini": GeminiProvider().configured(),
        "anthropic": AnthropicProvider().configured(),
        "fake": True,
    }
    return [
        schemas.ProviderOut(name=n, configured=configured[n], fake_mode=settings.use_fake_ai)
        for n in PROVIDER_NAMES
    ]


# ------------------------------------------------------------------------------- models


async def list_models(db: Db) -> Sequence[AiModel]:
    return await db.find(AiModel, {}, sort=[("provider", 1), ("model_id", 1)])


async def create_model(
    db: Db, *, guard: Authorized, payload: schemas.ModelCreate, meta: RequestMeta
) -> AiModel:
    await guard.ensure(Scope())
    if await db.exists(AiModel, {"model_id": payload.model_id}):
        raise Conflict("That model is already registered.")
    model = AiModel(**payload.model_dump())
    db.add(model)
    _audit(
        db,
        guard,
        meta,
        events.AI_MODEL_CREATED,
        target_type="ai_model",
        target_id=model.id,
        extra={"model_id": model.model_id, "provider": model.provider},
    )
    return model


async def update_model(
    db: Db,
    *,
    guard: Authorized,
    model_id: uuid.UUID,
    payload: schemas.ModelUpdate,
    meta: RequestMeta,
) -> AiModel:
    await guard.ensure(Scope())
    model = await db.get(AiModel, model_id)
    if model is None:
        raise NotFound("That model does not exist.")
    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changed.items():
        setattr(model, field, value)
    _audit(
        db,
        guard,
        meta,
        events.AI_MODEL_UPDATED,
        target_type="ai_model",
        target_id=model.id,
        extra={"model_id": model.model_id, **changed},
    )
    return model


# ----------------------------------------------------------------------------- features


async def list_features(db: Db) -> Sequence[AiFeature]:
    return await db.find(AiFeature, {}, sort=[("key", 1)])


async def update_feature(
    db: Db, *, guard: Authorized, key: str, payload: schemas.FeatureUpdate, meta: RequestMeta
) -> AiFeature:
    await guard.ensure(Scope())
    feature = await db.find_one(AiFeature, {"key": key})
    if feature is None:
        raise NotFound("That AI feature does not exist.")
    changed = payload.model_dump(exclude_unset=True)
    if changed.get("fallback_model_id") == "":
        changed["fallback_model_id"] = None
    changed = {k: v for k, v in changed.items() if v is not None or k == "fallback_model_id"}
    for field in ("model_id", "fallback_model_id"):
        if changed.get(field) and not await db.exists(AiModel, {"model_id": changed[field]}):
            raise ValidationFailed("Choose a model that is registered in Providers & Models.")
    # The prompt itself is not copied into the audit row: it can be long, and the row
    # only needs to say that it changed. Every other field records its old and new value.
    values = {
        f: {"from": getattr(feature, f), "to": v}
        for f, v in changed.items()
        if f != "system_prompt"
    }
    for field, value in changed.items():
        setattr(feature, field, value)
    _audit(
        db,
        guard,
        meta,
        events.AI_FEATURE_UPDATED,
        target_type="ai_feature",
        target_id=feature.id,
        extra={"key": key, "fields": sorted(changed), "changes": values},
    )
    return feature


# ------------------------------------------------------------------------------ budgets


def budget_out(
    budget: AiBudget | None,
    *,
    scope: str,
    institute_id: uuid.UUID | None,
    institute_name: str | None = None,
) -> schemas.BudgetOut:
    if budget is None:
        return schemas.BudgetOut(
            scope=scope,
            institute_id=institute_id,
            institute_name=institute_name,
            month=month_key(utcnow()),
            limit_tokens=None,
            limit_paise=None,
            used_tokens=0,
            used_paise=0,
            percent_used=None,
            on_exceed="block",
            alerts_sent=[],
            feature_limits={},
            feature_used_paise={},
            disabled_features=[],
            enabled=True,
            configured=False,
        )
    used, limit = fullest(
        budget.used_paise, budget.limit_paise, budget.used_tokens, budget.limit_tokens
    )
    return schemas.BudgetOut(
        scope=budget.scope,
        institute_id=budget.institute_id,
        institute_name=institute_name,
        month=budget.month,
        limit_tokens=budget.limit_tokens,
        limit_paise=budget.limit_paise,
        used_tokens=budget.used_tokens,
        used_paise=budget.used_paise,
        percent_used=percent_used(used, limit),
        on_exceed=budget.on_exceed,
        alerts_sent=budget.alerts_sent,
        feature_limits=budget.feature_limits,
        feature_used_paise=budget.feature_used_paise,
        disabled_features=budget.disabled_features,
        enabled=budget.enabled,
        configured=True,
    )


async def _ensure_month_row(db: Db, scope: str, institute_id: uuid.UUID | None) -> AiBudget:
    """This month's row, creating an empty one if no month was ever configured."""
    found = await budget_repo.month_budget(db, scope, institute_id)
    if found is None:
        found = AiBudget(scope=scope, institute_id=institute_id, month=month_key(utcnow()))  # type: ignore[arg-type]
        db.add(found)
    return found


async def get_platform_budget(db: Db, *, guard: Authorized) -> schemas.BudgetOut:
    await guard.ensure(Scope())
    budget = await budget_repo.month_budget(db, "platform", None)
    return budget_out(budget, scope="platform", institute_id=None)


async def update_platform_budget(
    db: Db, *, guard: Authorized, payload: schemas.PlatformBudgetUpdate, meta: RequestMeta
) -> AiBudget:
    await guard.ensure(Scope())
    budget = await _ensure_month_row(db, "platform", None)
    _apply_limits(budget, payload.model_dump(exclude_unset=True))
    _audit(
        db,
        guard,
        meta,
        events.AI_BUDGET_UPDATED,
        target_type="ai_budget",
        target_id=budget.id,
        extra={
            "scope": "platform",
            "month": budget.month,
            **payload.model_dump(exclude_unset=True),
        },
    )
    return budget


_NOT_NULLABLE = frozenset({"on_exceed", "enabled", "feature_limits", "disabled_features"})


def _apply_limits(budget: AiBudget, changed: dict[str, Any]) -> None:
    """Raising a limit re-arms the alerts above the new usage level, so a budget topped up
    after an 80% alert warns again when it reaches 80% of the new figure."""
    for field, value in changed.items():
        # `null` for a limit means "no limit"; for these it means nothing and used to be
        # written as-is, after which summing `feature_limits` raised a 500.
        if value is None and field in _NOT_NULLABLE:
            continue
        setattr(budget, field, value)
    if "limit_paise" in changed or "limit_tokens" in changed:
        used, limit = fullest(
            budget.used_paise, budget.limit_paise, budget.used_tokens, budget.limit_tokens
        )
        percent = percent_used(used, limit) or 0
        budget.alerts_sent = [t for t in budget.alerts_sent if t <= percent]


async def _institute_name(db: Db, institute_id: uuid.UUID) -> str:
    rows = await db.raw(Institute, {"_id": institute_id}, {"name": 1})
    if not rows:
        raise NotFound("That institute does not exist.")
    return rows[0]["name"]


async def get_institute_budget(
    db: Db, *, guard: Authorized, institute_id: uuid.UUID
) -> schemas.BudgetOut:
    name = await _institute_name(db, institute_id)
    await guard.ensure(await rbac.resolve_scope(db, institute_id=institute_id))
    budget = await budget_repo.month_budget(db, "institute", institute_id)
    return budget_out(budget, scope="institute", institute_id=institute_id, institute_name=name)


async def list_institute_budgets(db: Db, *, guard: Authorized) -> list[schemas.BudgetOut]:
    """This month for every institute the caller can see. Institutes with no allocation
    are included, so the platform admin sees who has none."""
    visible = guard.visible_institute_ids()
    match: dict[str, Any] = {"status": "active"}
    if visible is not None:
        match["_id"] = ids_in(visible)
    institutes = await db.raw(Institute, match, {"name": 1}, sort=[("name", 1)])
    rows = {
        b.institute_id: b
        for b in await db.find(
            AiBudget,
            {
                "scope": "institute",
                "month": month_key(utcnow()),
                "institute_id": ids_in(i["_id"] for i in institutes),
            },
        )
    }
    return [
        budget_out(
            rows.get(i["_id"]), scope="institute", institute_id=i["_id"], institute_name=i["name"]
        )
        for i in institutes
    ]


PLATFORM_ONLY_BUDGET_FIELDS = frozenset({"limit_tokens", "limit_paise", "on_exceed", "enabled"})


async def update_institute_budget(
    db: Db,
    *,
    guard: Authorized,
    institute_id: uuid.UUID,
    payload: schemas.InstituteBudgetUpdate,
    meta: RequestMeta,
) -> AiBudget:
    await _institute_name(db, institute_id)
    await guard.ensure(await rbac.resolve_scope(db, institute_id=institute_id))
    changed = payload.model_dump(exclude_unset=True)
    if PLATFORM_ONLY_BUDGET_FIELDS & set(changed) and not _is_platform_manager(guard):
        raise Forbidden("Only Dhruv Academy can change an institute's allocation or kill switch.")

    budget = await _ensure_month_row(db, "institute", institute_id)
    _apply_limits(budget, changed)
    shares = sum(budget.feature_limits.values())
    if budget.feature_limits and budget.limit_paise is not None and shares > budget.limit_paise:
        raise ValidationFailed("The features' shares add up to more than the allocation.")

    extra = {k: v for k, v in changed.items() if k != "feature_limits"}
    if "feature_limits" in changed:
        extra["feature_limits"] = dict(changed["feature_limits"] or {})
    _audit(
        db,
        guard,
        meta,
        events.AI_BUDGET_UPDATED,
        target_type="ai_budget",
        target_id=budget.id,
        institute_id=institute_id,
        extra={"scope": "institute", "month": budget.month, **extra},
    )
    return budget


# -------------------------------------------------------------------------- role limits


async def get_role_limits(
    db: Db, *, guard: Authorized, institute_id: uuid.UUID | None
) -> list[schemas.RoleLimitOut]:
    if institute_id is None:
        await guard.ensure(Scope())
    else:
        await guard.ensure(await rbac.resolve_scope(db, institute_id=institute_id))
    rows = await db.find(AiRoleLimit, {"institute_id": {"$in": [None, institute_id]}})
    defaults = {r.role_key: r.daily_requests for r in rows if r.institute_id is None}
    own = {r.role_key: r.daily_requests for r in rows if r.institute_id is not None}
    keys = list(ROLE_LIMITS) + sorted(set(defaults) - set(ROLE_LIMITS))
    out = []
    for key in keys:
        default = defaults.get(key, UNLISTED_ROLE_LIMIT)
        value = own.get(key) if institute_id else None
        out.append(
            schemas.RoleLimitOut(
                role_key=key,
                platform_default=default,
                institute_value=value,
                effective=value if value is not None else default,
            )
        )
    return out


async def update_role_limits(
    db: Db, *, guard: Authorized, payload: schemas.RoleLimitsUpdate, meta: RequestMeta
) -> None:
    institute_id = payload.institute_id
    if institute_id is None and not _is_platform_manager(guard):
        raise Forbidden("Only Dhruv Academy can change the platform's daily limits.")
    if institute_id is not None:
        await _institute_name(db, institute_id)
        await guard.ensure(await rbac.resolve_scope(db, institute_id=institute_id))

    defaults = {
        r.role_key: r.daily_requests for r in await db.find(AiRoleLimit, {"institute_id": None})
    }
    existing = {r.role_key: r for r in await db.find(AiRoleLimit, {"institute_id": institute_id})}
    for role_key, value in payload.limits.items():
        if institute_id is not None and not _is_platform_manager(guard):
            ceiling = defaults.get(role_key, UNLISTED_ROLE_LIMIT)
            if value > ceiling:
                raise ValidationFailed(
                    f"Your institute can lower the {role_key.replace('_', ' ')} limit, "
                    f"but not raise it above {ceiling}."
                )
        row = existing.get(role_key)
        if row is None:
            db.add(AiRoleLimit(institute_id=institute_id, role_key=role_key, daily_requests=value))
        else:
            row.daily_requests = value
    _audit(
        db,
        guard,
        meta,
        events.AI_ROLE_LIMITS_UPDATED,
        target_type="ai_role_limits",
        institute_id=institute_id,
        extra={"limits": payload.limits},
    )


# -------------------------------------------------------------------------------- usage


def _usage_match(
    visible: frozenset[uuid.UUID] | None,
    *,
    institute_id: uuid.UUID | None = None,
    feature_key: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Visibility first, then filters. An institute filter outside the caller's reach
    produces an empty result rather than an error, like the other list screens."""
    match: dict[str, Any] = {}
    if institute_id is not None:
        if visible is not None and institute_id not in visible:
            match["institute_id"] = {"$in": []}
        else:
            match["institute_id"] = institute_id
    elif visible is not None:
        match["institute_id"] = ids_in(visible)
    if feature_key:
        match["feature_key"] = feature_key
    if status:
        match["status"] = status
    window: dict[str, datetime] = {}
    if date_from:
        window["$gte"] = date_from
    if date_to:
        window["$lt"] = date_to
    if window:
        match["created_at"] = window
    return match


async def list_usage(
    db: Db, *, guard: Authorized, cursor: str | None, limit: int, **filters: Any
) -> tuple[Sequence[AiUsage], str | None, int]:
    match = _usage_match(guard.visible_institute_ids(), **filters)
    return await paginate(db, AiUsage, match, cursor=cursor, limit=limit)


async def _totals(db: Db, match: dict[str, Any]) -> schemas.UsageTotals:
    rows = await db.aggregate(
        AiUsage,
        [
            {"$match": match},
            {
                "$group": {
                    "_id": None,
                    "requests": {"$sum": {"$cond": [{"$in": ["$status", ["ok", "cached"]]}, 1, 0]}},
                    "tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
                    "cost_paise": {"$sum": "$cost_paise"},
                    "blocked": {"$sum": {"$cond": [{"$eq": ["$status", "blocked"]}, 1, 0]}},
                    "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                }
            },
        ],
    )
    if not rows:
        return schemas.UsageTotals()
    row = rows[0]
    return schemas.UsageTotals(**{k: int(row[k]) for k in schemas.UsageTotals.model_fields})


async def _grouped(db: Db, match: dict[str, Any], field: str) -> list[dict[str, Any]]:
    return await db.aggregate(
        AiUsage,
        [
            {"$match": {**match, **ANSWERED}},
            {
                "$group": {
                    "_id": f"${field}",
                    "requests": {"$sum": 1},
                    "tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
                    "cost_paise": {"$sum": "$cost_paise"},
                }
            },
            {"$sort": {"cost_paise": -1}},
            {"$limit": 50},
        ],
    )


async def usage_summary(
    db: Db, *, guard: Authorized, institute_id: uuid.UUID | None
) -> schemas.UsageSummary:
    """One screen's worth of aggregation, every number scoped like the usage log.

    Each figure is one grouped pipeline over the ``(institute_id, created_at)`` index,
    never a per-day or per-institute loop.
    """
    visible = guard.visible_institute_ids()
    if institute_id is not None and visible is not None and institute_id not in visible:
        # Checked before anything is read: the budget block below is not filtered by the
        # usage match, so another institute's allocation and spend leaked through it.
        raise NotFound("That institute does not exist.")
    if institute_id is None and visible is not None and len(visible) == 1:
        # An institute's own administrator: their allocation is the budget to show.
        (institute_id,) = visible
    now = utcnow()
    today = start_of_ist_day(now)
    month_start = today.replace(day=1)
    trend_start = today - timedelta(days=29)
    base = _usage_match(visible, institute_id=institute_id)

    def since(moment: datetime) -> dict[str, Any]:
        return {**base, "created_at": {"$gte": moment}}

    features = await _grouped(db, since(month_start), "feature_key")
    institutes = await _grouped(db, since(month_start), "institute_id")
    names = {
        r["_id"]: r["name"]
        for r in await db.raw(
            Institute, {"_id": ids_in(g["_id"] for g in institutes if g["_id"])}, {"name": 1}
        )
    }
    days = await db.aggregate(
        AiUsage,
        [
            {"$match": {**since(trend_start), **ANSWERED}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$created_at",
                            "timezone": IST_OFFSET,
                        }
                    },
                    "requests": {"$sum": 1},
                    "cost_paise": {"$sum": "$cost_paise"},
                }
            },
        ],
    )
    by_day = {d["_id"]: d for d in days}
    trend = []
    for offset in range(30):
        day = (trend_start + timedelta(days=offset)).astimezone(IST).date()
        found = by_day.get(day.isoformat(), {})
        trend.append(
            schemas.UsageDay(
                day=day,
                requests=int(found.get("requests", 0)),
                cost_paise=int(found.get("cost_paise", 0)),
            )
        )

    if institute_id is not None:
        budget = budget_out(
            await budget_repo.month_budget(db, "institute", institute_id),
            scope="institute",
            institute_id=institute_id,
            institute_name=names.get(institute_id),
        )
    elif visible is None:
        budget = budget_out(
            await budget_repo.month_budget(db, "platform", None),
            scope="platform",
            institute_id=None,
        )
    else:
        budget = None

    return schemas.UsageSummary(
        today=await _totals(db, since(today)),
        month=await _totals(db, since(month_start)),
        by_feature=[
            schemas.UsageGroup(
                key=g["_id"],
                label=str(g["_id"]),
                requests=g["requests"],
                tokens=g["tokens"],
                cost_paise=g["cost_paise"],
            )
            for g in features
        ],
        by_institute=[
            schemas.UsageGroup(
                key=str(g["_id"]) if g["_id"] else None,
                label=names.get(g["_id"], "Platform (no institute)"),
                requests=g["requests"],
                tokens=g["tokens"],
                cost_paise=g["cost_paise"],
            )
            for g in institutes
        ],
        trend=trend,
        budget=budget,
    )


async def export_usage(db: Db, *, guard: Authorized, **filters: Any) -> bytes:
    """The usage log as a workbook, for billing and review. Capped, newest first."""
    from openpyxl import Workbook

    match = _usage_match(guard.visible_institute_ids(), **filters)
    rows = await db.raw(
        AiUsage,
        match,
        {"prompt": 0},
        sort=[("created_at", -1)],
        limit=EXPORT_MAX_ROWS,
    )
    names = {
        r["_id"]: r["name"]
        for r in await db.raw(
            Institute, {"_id": ids_in({r.get("institute_id") for r in rows} - {None})}, {"name": 1}
        )
    }
    book = Workbook()
    sheet = book.active
    sheet.title = "AI usage"
    sheet.append(
        [
            "Time (IST)",
            "Institute",
            "User ID",
            "Role",
            "Feature",
            "Provider",
            "Model",
            "Input tokens",
            "Output tokens",
            "Cost (₹)",
            "Latency (ms)",
            "Status",
            "Reason",
            "Backup model used",
        ]
    )
    for r in rows:
        sheet.append(
            [
                r["created_at"].astimezone(IST).strftime("%d-%m-%Y %H:%M:%S"),
                names.get(r.get("institute_id"), "Platform"),
                str(r["user_id"]),
                r.get("role_key") or "",
                r["feature_key"],
                r.get("provider") or "",
                r.get("model_id") or "",
                r.get("input_tokens", 0),
                r.get("output_tokens", 0),
                round(r.get("cost_paise", 0) / 100, 2),
                r.get("latency_ms", 0),
                r["status"],
                r.get("block_reason") or "",
                "yes" if r.get("fallback_used") else "",
            ]
        )
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
