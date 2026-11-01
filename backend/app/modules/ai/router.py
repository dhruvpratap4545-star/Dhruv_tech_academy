"""AI Control Room endpoints (``/api/v1/ai``). Resolve, authorise, delegate, commit."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.pagination import Page, clamp_limit
from app.modules.ai import gateway, schemas
from app.modules.ai import service as ai
from app.modules.ai.pricing import IST
from app.modules.auth.service import RequestMeta
from app.modules.rbac.deps import DbSession, client_ip, require_permission, user_agent
from app.modules.rbac.service import Authorized

router = APIRouter()

Manage = Annotated[Authorized, Depends(require_permission("ai:manage"))]
UsageRead = Annotated[Authorized, Depends(require_permission("ai:usage_read"))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _meta(request: Request) -> RequestMeta:
    return RequestMeta(ip=client_ip(request), user_agent=user_agent(request))


def _day_start(value: date | None) -> datetime | None:
    return datetime.combine(value, time.min, tzinfo=IST) if value else None


def _day_end(value: date | None) -> datetime | None:
    """``date_to`` is inclusive: usage *on* the 15th includes the whole of the 15th."""
    return datetime.combine(value + timedelta(days=1), time.min, tzinfo=IST) if value else None


# ----------------------------------------------------------------------------- settings


@router.get("/settings", response_model=schemas.SettingsOut, summary="Platform AI settings")
async def get_settings(db: DbSession, guard: Manage) -> schemas.SettingsOut:
    from app.modules.rbac.scopes import Scope

    await guard.ensure(Scope())
    row = await ai.get_settings(db)
    await db.commit()
    return schemas.SettingsOut.model_validate(row)


@router.put(
    "/settings",
    response_model=schemas.SettingsOut,
    summary="Change platform AI settings, including the global kill switch",
)
async def update_settings(
    payload: schemas.SettingsUpdate, request: Request, db: DbSession, guard: Manage
) -> schemas.SettingsOut:
    row = await ai.update_settings(db, guard=guard, payload=payload, meta=_meta(request))
    await db.commit()
    return schemas.SettingsOut.model_validate(row)


@router.get(
    "/providers",
    response_model=list[schemas.ProviderOut],
    summary="AI providers and whether each has a key configured (never the key itself)",
)
async def list_providers(guard: Manage) -> list[schemas.ProviderOut]:
    from app.modules.rbac.scopes import Scope

    await guard.ensure(Scope())
    return ai.list_providers()


# ------------------------------------------------------------------------------- models


@router.get("/models", response_model=list[schemas.ModelOut], summary="Model registry and prices")
async def list_models(db: DbSession, guard: Manage) -> list[schemas.ModelOut]:
    from app.modules.rbac.scopes import Scope

    await guard.ensure(Scope())
    return [schemas.ModelOut.model_validate(m) for m in await ai.list_models(db)]


@router.post(
    "/models", response_model=schemas.ModelOut, status_code=201, summary="Register a model"
)
async def create_model(
    payload: schemas.ModelCreate, request: Request, db: DbSession, guard: Manage
) -> schemas.ModelOut:
    model = await ai.create_model(db, guard=guard, payload=payload, meta=_meta(request))
    await db.commit()
    return schemas.ModelOut.model_validate(model)


@router.patch("/models/{model_id}", response_model=schemas.ModelOut, summary="Edit a model")
async def update_model(
    model_id: uuid.UUID,
    payload: schemas.ModelUpdate,
    request: Request,
    db: DbSession,
    guard: Manage,
) -> schemas.ModelOut:
    model = await ai.update_model(
        db, guard=guard, model_id=model_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.ModelOut.model_validate(model)


# ----------------------------------------------------------------------------- features


@router.get("/features", response_model=list[schemas.FeatureOut], summary="AI features")
async def list_features(db: DbSession, guard: Manage) -> list[schemas.FeatureOut]:
    from app.modules.rbac.scopes import Scope

    await guard.ensure(Scope())
    return [schemas.FeatureOut.model_validate(f) for f in await ai.list_features(db)]


@router.patch(
    "/features/{key}",
    response_model=schemas.FeatureOut,
    summary="Model, backup model, limits, prompt and on/off for one feature",
)
async def update_feature(
    key: str, payload: schemas.FeatureUpdate, request: Request, db: DbSession, guard: Manage
) -> schemas.FeatureOut:
    feature = await ai.update_feature(
        db, guard=guard, key=key, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return schemas.FeatureOut.model_validate(feature)


# ------------------------------------------------------------------------------ budgets


@router.get("/budgets/platform", response_model=schemas.BudgetOut, summary="Platform budget")
async def get_platform_budget(db: DbSession, guard: Manage) -> schemas.BudgetOut:
    return await ai.get_platform_budget(db, guard=guard)


@router.put("/budgets/platform", response_model=schemas.BudgetOut, summary="Set platform budget")
async def update_platform_budget(
    payload: schemas.PlatformBudgetUpdate, request: Request, db: DbSession, guard: Manage
) -> schemas.BudgetOut:
    budget = await ai.update_platform_budget(db, guard=guard, payload=payload, meta=_meta(request))
    await db.commit()
    return ai.budget_out(budget, scope="platform", institute_id=None)


@router.get(
    "/budgets/institutes",
    response_model=list[schemas.BudgetOut],
    summary="This month's allocation for every institute in your scope",
)
async def list_institute_budgets(db: DbSession, guard: UsageRead) -> list[schemas.BudgetOut]:
    return await ai.list_institute_budgets(db, guard=guard)


@router.get(
    "/budgets/institutes/{institute_id}",
    response_model=schemas.BudgetOut,
    summary="One institute's allocation and usage this month",
)
async def get_institute_budget(
    institute_id: uuid.UUID, db: DbSession, guard: UsageRead
) -> schemas.BudgetOut:
    return await ai.get_institute_budget(db, guard=guard, institute_id=institute_id)


@router.put(
    "/budgets/institutes/{institute_id}",
    response_model=schemas.BudgetOut,
    summary="Set an institute's allocation, feature split or kill switch",
    description="Allocation, overflow behaviour and the kill switch need `ai:manage`. "
    "The institute's own administrators may change the feature split and disabled features.",
)
async def update_institute_budget(
    institute_id: uuid.UUID,
    payload: schemas.InstituteBudgetUpdate,
    request: Request,
    db: DbSession,
    guard: UsageRead,
) -> schemas.BudgetOut:
    await ai.update_institute_budget(
        db, guard=guard, institute_id=institute_id, payload=payload, meta=_meta(request)
    )
    await db.commit()
    return await ai.get_institute_budget(db, guard=guard, institute_id=institute_id)


# -------------------------------------------------------------------------- role limits


@router.get(
    "/role-limits",
    response_model=list[schemas.RoleLimitOut],
    summary="Daily AI requests per role (platform defaults, or one institute's)",
)
async def get_role_limits(
    db: DbSession, guard: UsageRead, institute_id: uuid.UUID | None = None
) -> list[schemas.RoleLimitOut]:
    return await ai.get_role_limits(db, guard=guard, institute_id=institute_id)


@router.put(
    "/role-limits",
    response_model=list[schemas.RoleLimitOut],
    summary="Set daily limits. Institutes may only lower the platform defaults.",
)
async def update_role_limits(
    payload: schemas.RoleLimitsUpdate, request: Request, db: DbSession, guard: UsageRead
) -> list[schemas.RoleLimitOut]:
    await ai.update_role_limits(db, guard=guard, payload=payload, meta=_meta(request))
    await db.commit()
    return await ai.get_role_limits(db, guard=guard, institute_id=payload.institute_id)


# -------------------------------------------------------------------------------- usage


def _filters(
    institute_id: uuid.UUID | None,
    feature: str | None,
    status: str | None,
    date_from: date | None,
    date_to: date | None,
) -> dict:
    return {
        "institute_id": institute_id,
        "feature_key": feature,
        "status": status,
        "date_from": _day_start(date_from),
        "date_to": _day_end(date_to),
    }


@router.get("/usage", response_model=Page[schemas.UsageOut], summary="The AI usage log")
async def list_usage(
    db: DbSession,
    guard: UsageRead,
    institute_id: uuid.UUID | None = None,
    feature: Annotated[str | None, Query(max_length=40)] = None,
    status: schemas.UsageStatusFilter | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[schemas.UsageOut]:
    rows, next_cursor, total = await ai.list_usage(
        db,
        guard=guard,
        cursor=cursor,
        limit=clamp_limit(limit),
        **_filters(institute_id, feature, status, date_from, date_to),
    )
    return Page[schemas.UsageOut](
        items=[schemas.UsageOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/usage/summary", response_model=schemas.UsageSummary, summary="Dashboard figures")
async def usage_summary(
    db: DbSession, guard: UsageRead, institute_id: uuid.UUID | None = None
) -> schemas.UsageSummary:
    return await ai.usage_summary(db, guard=guard, institute_id=institute_id)


@router.get("/usage/export", summary="Download the usage log as Excel")
async def export_usage(
    db: DbSession,
    guard: UsageRead,
    institute_id: uuid.UUID | None = None,
    feature: Annotated[str | None, Query(max_length=40)] = None,
    status: schemas.UsageStatusFilter | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    data = await ai.export_usage(
        db, guard=guard, **_filters(institute_id, feature, status, date_from, date_to)
    )
    return Response(
        content=data,
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="ai-usage.xlsx"'},
    )


# --------------------------------------------------------------------------- playground


@router.post(
    "/playground",
    response_model=schemas.PlaygroundResponse,
    summary="Run a test prompt through the full gateway",
    description="Every control applies — switches, limits, budgets, redaction — and the "
    "request is recorded in the usage log like any other.",
)
async def playground(
    payload: schemas.PlaygroundRequest, db: DbSession, guard: Manage
) -> schemas.PlaygroundResponse:
    from app.modules.rbac.scopes import Scope

    await guard.ensure(Scope())
    result = await gateway.complete(
        db,
        context=guard.context,
        institute_id=payload.institute_id,
        feature_key=payload.feature_key,
        prompt=payload.prompt,
    )
    return schemas.PlaygroundResponse(
        text=result.text,
        status=result.status,
        model_id=result.model_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_paise=result.cost_paise,
        fallback_used=result.fallback_used,
        safety_blocked=result.safety_blocked,
        redactions=result.redactions,
        usage_id=result.usage_id,
    )
