"""The AI gateway: the only way any feature in the platform calls an AI model.

Later milestones (exam solver, topic notes, OMR checking, kids zone, WhatsApp assistant)
call ``complete`` and nothing else. Every rule about AI therefore lives on this one path:

    1. switches      global, institute and feature kill switches
    2. daily limit   today's requests for this person against their role's limit (IST day)
    3. budget        the institute's and the platform's month; over → block or fallback
    4. sanitise      redact phones, emails and Aadhaar-like numbers; delimit user text
    5. cache         a fresh saved answer to the identical request is returned for free
    6. call          the provider, with a timeout; on failure, once more on the fallback
    7. record        an ``ai_usage`` row, ``$inc`` on the budgets, alerts at thresholds

**Recording uses its own unit of work** and commits inside this function. A blocked or
failed request must still appear in the usage log, and the caller's unit of work is
discarded when the gateway raises — so if recording rode on it, exactly the requests an
administrator most needs to see would vanish.

**Race tolerance.** Budgets are checked before the call and incremented after it, so
concurrent requests can overshoot a limit by the requests already in flight. That is
accepted and documented in the plan: it is bounded, and far cheaper than a lock. A hard
spending cap is also set in Google Cloud billing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.core.db import Db, utcnow
from app.core.errors import AppError, ServiceUnavailable
from app.modules.ai import budgets as budget_repo
from app.modules.ai import safety
from app.modules.ai.models import (
    ANSWERED,
    SETTINGS_KEY,
    AiBudget,
    AiCache,
    AiFeature,
    AiModel,
    AiRoleLimit,
    AiSettings,
    AiUsage,
)
from app.modules.ai.pricing import cost_paise, start_of_ist_day
from app.modules.ai.providers import (
    Attachment,
    ProviderError,
    ProviderRequest,
    ProviderResult,
    get_provider,
)
from app.modules.ai.seed import UNLISTED_ROLE_LIMIT
from app.modules.rbac.context import AuthContext
from app.modules.rbac.scopes import Scope

logger = logging.getLogger(__name__)

#: The longest prompt accepted, in characters. A request this size costs real money, and
#: anything longer is almost certainly a paste of a whole book rather than a question.
MAX_PROMPT_CHARS = 20_000


class AiUnavailable(AppError):
    """AI is switched off here — globally, for this institute, or for this feature."""

    status_code = 403
    code = "AI_DISABLED"
    default_message = "AI features are switched off right now."


class AiDailyLimit(AppError):
    status_code = 429
    code = "AI_DAILY_LIMIT"
    default_message = "You have used all of today's AI requests. Please try again tomorrow."


class AiBudgetExhausted(AppError):
    status_code = 429
    code = "AI_BUDGET_EXHAUSTED"
    default_message = "This month's AI allowance has been used up. Please contact your school."


@dataclass(slots=True)
class AiResult:
    text: str
    status: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_paise: int
    fallback_used: bool = False
    safety_blocked: bool = False
    redactions: int = 0
    usage_id: uuid.UUID | None = None


@dataclass(slots=True)
class _Plan:
    """What the checks decided: which model to call, and against which budgets."""

    feature: AiFeature
    model_id: str
    fallback_model_id: str | None
    fallback_forced: bool
    budgets: list[AiBudget]
    role_key: str | None


async def complete(
    db: Db,
    *,
    context: AuthContext,
    institute_id: uuid.UUID | None,
    feature_key: str,
    prompt: str,
    extra_context: str | None = None,
    attachments: tuple[Attachment, ...] = (),
    json_schema: dict | None = None,
    timeout_seconds: float | None = None,
) -> AiResult:
    """Run one prompt through every control, and return the answer or raise.

    ``extra_context`` is trusted material the *feature* adds (a chapter's text, a question
    paper), placed outside the user delimiters. ``prompt`` is what the person typed.
    ``attachments`` are files the feature sends as they are (a syllabus PDF): redaction
    cannot reach inside them, so a feature must only attach documents meant for the
    platform, never a student's work. ``json_schema`` asks for a structured answer.
    Raises ``AiUnavailable``, ``AiDailyLimit``, ``AiBudgetExhausted`` or
    ``ServiceUnavailable``; every one of them is recorded in the usage log first.
    """
    settings_row = await db.find_one(AiSettings, {"key": SETTINGS_KEY}) or AiSettings()
    role = context.role_at(Scope(institute_id=institute_id)) if institute_id else None
    role = role or max(context.assignments, key=lambda a: a.rank, default=None)
    role_key = role.role_key if role else None
    base = {
        "institute_id": institute_id,
        "user_id": context.user_id,
        "role_key": role_key,
        "feature_key": feature_key,
    }

    async def refuse(error: AppError, reason: str) -> None:
        await _record(base, status="blocked", block_reason=reason)
        raise error

    plan = await _check(db, settings_row, base, institute_id, feature_key, role_key, refuse)

    # 4. sanitise
    clean, redactions = safety.redact(prompt.strip()[:MAX_PROMPT_CHARS])
    system_prompt = safety.build_system_prompt(
        plan.feature.system_prompt, kids=plan.feature.safety_level == "kids"
    )
    user_text = safety.wrap_user_text(clean)
    extra, extra_redactions = safety.redact(extra_context.strip() if extra_context else "")
    redactions += extra_redactions
    if extra:
        user_text = f"{extra}\n\n{user_text}"

    # 5. cache — keyed on everything that shapes the answer, so a changed prompt, safety
    # level or token limit is not answered from a stale entry.
    key = safety.cache_key(
        feature_key,
        plan.model_id,
        clean,
        system_prompt,
        plan.feature.safety_level,
        str(plan.feature.max_output_tokens),
        extra,
        *(hashlib.sha256(a.data).hexdigest() for a in attachments),
        json.dumps(json_schema, sort_keys=True) if json_schema else "",
    )
    if plan.feature.cache_ttl_hours > 0:
        hit = await db.find_one(AiCache, {"key": key, "expires_at": {"$gt": utcnow()}})
        if hit is not None:
            usage_id = await _record(
                base,
                status="cached",
                model_id=hit.model_id,
                prompt=clean if settings_row.log_prompts else None,
            )
            return AiResult(
                text=hit.response,
                status="cached",
                model_id=hit.model_id,
                input_tokens=0,
                output_tokens=0,
                cost_paise=0,
                redactions=redactions,
                usage_id=usage_id,
            )

    # 6. call, falling back once
    started = time.monotonic()
    attempts = [plan.model_id]
    if plan.fallback_model_id and plan.fallback_model_id != plan.model_id:
        attempts.append(plan.fallback_model_id)
    model: AiModel | None = None
    result: ProviderResult | None = None
    for model_id in attempts:
        model = await db.find_one(AiModel, {"model_id": model_id, "enabled": True})
        if model is None:
            logger.warning("ai model missing or disabled", extra={"model_id": model_id})
            continue
        try:
            result = await get_provider(model.provider).complete(
                ProviderRequest(
                    model_id=model.model_id,
                    system_prompt=system_prompt,
                    user_text=user_text,
                    max_output_tokens=plan.feature.max_output_tokens,
                    safety_level=plan.feature.safety_level,
                    attachments=attachments,
                    json_schema=json_schema,
                    timeout_seconds=timeout_seconds,
                )
            )
            break
        except ProviderError as exc:
            logger.warning(
                "ai provider call failed", extra={"model_id": model_id, "error": str(exc)}
            )
            result = None
        except Exception:
            # A bug or an unexpected response shape (e.g. a body that is not JSON) is still
            # a failed call: try the fallback, and log it as an error rather than a 500.
            logger.exception("ai provider call raised", extra={"model_id": model_id})
            result = None
    latency_ms = int((time.monotonic() - started) * 1000)

    if result is None or model is None:
        await _record(base, status="error", block_reason="provider_error", latency_ms=latency_ms)
        raise ServiceUnavailable("The AI service is not responding. Please try again shortly.")

    # 7. record
    paise = cost_paise(
        result.input_tokens,
        result.output_tokens,
        input_price_per_mtok_usd=model.input_price_per_mtok_usd,
        output_price_per_mtok_usd=model.output_price_per_mtok_usd,
        usd_to_inr=settings_row.usd_to_inr,
    )
    fallback_used = plan.fallback_forced or model.model_id != plan.model_id
    tokens = result.input_tokens + result.output_tokens
    rec = Db()
    usage = AiUsage(
        **base,
        provider=get_provider(model.provider).name,
        model_id=model.model_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_paise=paise,
        latency_ms=latency_ms,
        status="blocked" if result.safety_blocked else "ok",
        block_reason="safety" if result.safety_blocked else None,
        fallback_used=fallback_used,
        prompt=clean if settings_row.log_prompts else None,
    )
    rec.add(usage)
    for budget in plan.budgets:
        budget_repo.record_spend(rec, budget, tokens=tokens, paise=paise, feature_key=feature_key)
    if plan.feature.cache_ttl_hours > 0 and not result.safety_blocked:
        await _store_cache(rec, plan, key, model.model_id, result, feature_key)
    await rec.commit()

    for budget in plan.budgets:
        await budget_repo.send_threshold_alerts(budget.id, settings_row.alert_thresholds)

    return AiResult(
        text=result.text,
        status="ok",
        model_id=model.model_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_paise=paise,
        fallback_used=fallback_used,
        safety_blocked=result.safety_blocked,
        redactions=redactions,
        usage_id=usage.id,
    )


async def _check(
    db: Db,
    settings_row: AiSettings,
    base: dict[str, Any],
    institute_id: uuid.UUID | None,
    feature_key: str,
    role_key: str | None,
    refuse,
) -> _Plan:
    """Steps 1–3. Returns the plan, or records the refusal and raises."""
    # 1. switches
    if not settings_row.global_enabled:
        await refuse(AiUnavailable(), "global_off")
    feature = await db.find_one(AiFeature, {"key": feature_key})
    if feature is None or not feature.enabled:
        await refuse(AiUnavailable("This AI feature is switched off."), "feature_off")
    assert feature is not None

    institute_budget: AiBudget | None = None
    if institute_id is not None:
        from app.modules.rbac import repository as rbac_repo
        from app.modules.rbac.catalog import AI_MODULE

        if not await rbac_repo.is_module_enabled(db, institute_id, AI_MODULE):
            await refuse(AiUnavailable("AI is not switched on for your institute."), "module_off")
        institute_budget = await budget_repo.month_budget(db, "institute", institute_id)
        if institute_budget is not None and not institute_budget.enabled:
            await refuse(AiUnavailable("AI is switched off for your institute."), "institute_off")
        if institute_budget is not None and feature_key in institute_budget.disabled_features:
            await refuse(
                AiUnavailable("This AI feature is switched off for your institute."),
                "feature_off_institute",
            )

    # 2. daily limit
    limit = await daily_limit(db, institute_id, role_key)
    used_today = await db.count(
        AiUsage,
        {
            # Per institute, like the limit itself: a teacher in two schools has each
            # school's allowance, not one shared between them.
            "user_id": base["user_id"],
            "institute_id": institute_id,
            "created_at": {"$gte": start_of_ist_day(utcnow())},
            **ANSWERED,
        },
    )
    if used_today >= limit:
        await refuse(
            AiDailyLimit(
                f"You have used all {limit} of today's AI requests. Please try again tomorrow."
            ),
            "daily_limit",
        )

    # 3. budgets
    platform_budget = await budget_repo.month_budget(db, "platform", None)
    budgets = [b for b in (institute_budget, platform_budget) if b is not None]
    over = [b for b in budgets if budget_repo.exceeded(b)]
    if budget_repo.feature_exceeded(institute_budget, feature_key):
        over.append(institute_budget)  # type: ignore[arg-type]

    model_id, fallback_model_id, forced = feature.model_id, feature.fallback_model_id, False
    if over:
        if any(b.on_exceed == "block" for b in over) or not feature.fallback_model_id:
            await refuse(AiBudgetExhausted(), "budget")
        model_id, fallback_model_id, forced = feature.fallback_model_id, None, True  # type: ignore[assignment]

    return _Plan(
        feature=feature,
        model_id=model_id,
        fallback_model_id=fallback_model_id,
        fallback_forced=forced,
        budgets=budgets,
        role_key=role_key,
    )


async def daily_limit(db: Db, institute_id: uuid.UUID | None, role_key: str | None) -> int:
    """The institute's own limit for this role if it set one, else the platform default."""
    if role_key is None:
        return UNLISTED_ROLE_LIMIT
    rows = {
        r.institute_id: r.daily_requests
        for r in await db.find(
            AiRoleLimit,
            {"role_key": role_key, "institute_id": {"$in": [None, institute_id]}},
        )
    }
    if institute_id is not None and institute_id in rows:
        return rows[institute_id]
    return rows.get(None, UNLISTED_ROLE_LIMIT)


async def _record(base: dict[str, Any], *, status: str, **fields: Any) -> uuid.UUID:
    rec = Db()
    usage = AiUsage(**base, status=status, **fields)  # type: ignore[arg-type]
    rec.add(usage)
    await rec.commit()
    return usage.id


async def _store_cache(
    rec: Db,
    plan: _Plan,
    key: str,
    model_id: str,
    result: ProviderResult,
    feature_key: str,
) -> None:
    """Upsert, not insert: two students asking the same thing at once both store it."""
    expires = utcnow() + timedelta(hours=plan.feature.cache_ttl_hours)
    await AiCache.get_pymongo_collection().update_one(
        {"key": key},
        {
            "$set": {
                "response": result.text,
                "model_id": model_id,
                "feature_key": feature_key,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "expires_at": expires,
            },
            "$setOnInsert": {"_id": uuid.uuid4()},
        },
        upsert=True,
    )
