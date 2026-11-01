"""AI Control Room end to end (Phase 3, Module A). Every call uses the fake provider.

Covers client acceptance items 1–3: a test request is logged with tokens and ₹; reaching a
limit blocks or downgrades and sends the 80% and 100% emails once; a kill switch takes
effect immediately.
"""

from __future__ import annotations

from datetime import timedelta

import pytest_asyncio
from httpx import AsyncClient

from app.core.db import Db, utcnow
from app.modules.ai.models import AiBudget, AiUsage
from app.modules.ai.pricing import month_key, previous_month_key
from app.modules.audit.models import AuditLog
from app.modules.rbac.models import InstituteModule


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture
async def world(db: Db, institute, make_user):
    abc, _ = await institute("ABC College", "ABC")
    xyz, _ = await institute("XYZ College", "XYZ")
    for row in (abc, xyz):
        db.add(InstituteModule(institute_id=row.id, module_key="ai", enabled=True))
    await db.commit()
    return {
        "abc": abc,
        "xyz": xyz,
        "platform": await make_user("platform_admin"),
        "abc_admin": await make_user("institute_admin", institute_id=abc.id),
        "xyz_admin": await make_user("institute_admin", institute_id=xyz.id),
        "student": await make_user("student", institute_id=abc.id),
    }


async def _ask(client: AsyncClient, world, prompt: str = "What is photosynthesis?", **extra):
    return await client.post(
        "/api/v1/ai/playground",
        json={"prompt": prompt, "institute_id": str(world["abc"].id), **extra},
    )


# ------------------------------------------------------------------- acceptance item 1


async def test_a_test_request_is_logged_with_tokens_and_rupee_cost(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["platform"])

    response = await _ask(client, world, "Explain Newton's second law " * 200)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_id"] == "gemini-3.5-flash-lite"
    assert body["input_tokens"] > 0 and body["output_tokens"] > 0
    assert body["cost_paise"] > 0

    log = (await client.get("/api/v1/ai/usage")).json()
    assert log["total"] == 1
    row = log["items"][0]
    assert row["institute_id"] == str(world["abc"].id)
    assert row["role_key"] == "platform_admin"
    assert row["cost_paise"] == body["cost_paise"]
    assert row["provider"] == "fake"


async def test_the_prompt_is_not_stored_unless_logging_is_switched_on(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["platform"])
    await _ask(client, world, "call me on 9876543210")
    await client.put("/api/v1/ai/settings", json={"log_prompts": True})
    response = await _ask(client, world, "call me on 9876543210")

    assert response.json()["redactions"] == 1
    rows = await db.find(AiUsage, {}, sort=[("created_at", 1)])
    assert rows[0].prompt is None
    assert "9876543210" not in rows[1].prompt
    assert "[phone removed]" in rows[1].prompt


async def test_admin_sets_budget_and_daily_student_limit(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["platform"])
    abc = world["abc"].id

    budget = await client.put(
        f"/api/v1/ai/budgets/institutes/{abc}", json={"limit_paise": 50_000, "on_exceed": "block"}
    )
    limits = await client.put(
        "/api/v1/ai/role-limits", json={"institute_id": str(abc), "limits": {"student": 20}}
    )

    assert budget.status_code == 200, budget.text
    assert budget.json()["limit_paise"] == 50_000
    assert budget.json()["month"] == month_key(utcnow())
    student = next(r for r in limits.json() if r["role_key"] == "student")
    assert student == {
        "role_key": "student",
        "platform_default": 30,
        "institute_value": 20,
        "effective": 20,
    }
    assert await db.count(AuditLog, {"action": "ai_budget_updated"}) == 1


# ------------------------------------------------------------------- acceptance item 2


async def test_reaching_the_budget_blocks_and_records_the_refusal(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["platform"])
    await client.put(f"/api/v1/ai/budgets/institutes/{world['abc'].id}", json={"limit_paise": 1})

    first = await _ask(client, world, "long question " * 300)
    second = await _ask(client, world)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "AI_BUDGET_EXHAUSTED"
    blocked = await db.find_one(AiUsage, {"status": "blocked"})
    assert blocked is not None and blocked.block_reason == "budget"


async def test_reaching_the_budget_can_downgrade_to_the_backup_model(
    client: AsyncClient, world
) -> None:
    await _as(client, world["platform"])
    await client.put(
        f"/api/v1/ai/budgets/institutes/{world['abc'].id}",
        json={"limit_paise": 1, "on_exceed": "fallback"},
    )
    await _ask(client, world, "long question " * 300)

    second = await _ask(client, world)

    assert second.status_code == 200
    assert second.json()["model_id"] == "gemini-3.1-flash-lite"
    assert second.json()["fallback_used"] is True


async def test_80_and_100_percent_alerts_are_emailed_exactly_once(
    client: AsyncClient, db: Db, world, outbox
) -> None:
    await _as(client, world["platform"])
    await client.put(
        f"/api/v1/ai/budgets/institutes/{world['abc'].id}",
        json={"limit_tokens": 100, "on_exceed": "fallback"},
    )
    outbox.clear()

    for _ in range(4):
        await _ask(client, world, "x" * 200)  # ~50+ tokens a request

    subjects = [m.subject for m in outbox.outbox]
    abc_admin = [m for m in outbox.outbox if m.to == world["abc_admin"].email]
    assert sum("80%" in s for s in subjects) == len(
        {m.to for m in outbox.outbox if "80%" in m.subject}
    )
    assert [m.subject for m in abc_admin].count("AI budget 80% used — Dhruv Online Academy") == 1
    assert [m.subject for m in abc_admin].count("AI budget 100% used — Dhruv Online Academy") == 1
    # The other institute's admin hears nothing about ABC's budget.
    assert not any(m.to == world["xyz_admin"].email for m in outbox.outbox)
    budget = await db.find_one(AiBudget, {"institute_id": world["abc"].id})
    assert sorted(budget.alerts_sent) == [80, 100]
    assert await db.count(AuditLog, {"action": "ai_budget_alert_sent"}) == 2


async def test_the_daily_limit_blocks_and_resets_at_indian_midnight(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["platform"])
    await client.put("/api/v1/ai/role-limits", json={"limits": {"platform_admin": 2}})
    # Yesterday's requests do not count against today.
    db.add(
        AiUsage(
            user_id=world["platform"].id,
            feature_key="playground",
            status="ok",
            created_at=utcnow() - timedelta(days=1, hours=1),
        )
    )
    await db.commit()

    assert (await _ask(client, world)).status_code == 200
    assert (await _ask(client, world)).status_code == 200
    third = await _ask(client, world)

    assert third.status_code == 429
    assert third.json()["error"]["code"] == "AI_DAILY_LIMIT"
    assert "2" in third.json()["error"]["message"]


# ------------------------------------------------------------------- acceptance item 3


async def test_the_institute_kill_switch_takes_effect_immediately(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["platform"])
    assert (await _ask(client, world)).status_code == 200

    await client.put(f"/api/v1/ai/budgets/institutes/{world['abc'].id}", json={"enabled": False})
    off = await _ask(client, world)
    other = await client.post(
        "/api/v1/ai/playground", json={"prompt": "hi", "institute_id": str(world["xyz"].id)}
    )

    assert off.status_code == 403
    assert off.json()["error"]["code"] == "AI_DISABLED"
    assert other.status_code == 200  # only ABC was switched off
    assert await db.find_one(AiUsage, {"block_reason": "institute_off"}) is not None


async def test_the_global_and_feature_switches(client: AsyncClient, world) -> None:
    await _as(client, world["platform"])

    await client.patch("/api/v1/ai/features/playground", json={"enabled": False})
    feature_off = await _ask(client, world)
    await client.patch("/api/v1/ai/features/playground", json={"enabled": True})
    await client.put("/api/v1/ai/settings", json={"global_enabled": False})
    global_off = await _ask(client, world)

    assert feature_off.status_code == 403
    assert global_off.status_code == 403


async def test_an_institute_without_the_ai_module_is_refused(
    client: AsyncClient, db: Db, world
) -> None:
    row = await db.find_one(InstituteModule, {"institute_id": world["abc"].id, "module_key": "ai"})
    row.enabled = False
    await db.commit()
    await _as(client, world["platform"])

    response = await _ask(client, world)

    assert response.status_code == 403
    assert "not switched on" in response.json()["error"]["message"]


async def test_an_institute_admin_can_switch_a_feature_off_for_their_school(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_admin"])
    response = await client.put(
        f"/api/v1/ai/budgets/institutes/{world['abc'].id}",
        json={"disabled_features": ["playground"]},
    )
    assert response.status_code == 200, response.text

    await _as(client, world["platform"])
    assert (await _ask(client, world)).status_code == 403


# ---------------------------------------------------------------------- gateway paths


async def test_a_failing_model_falls_back_and_a_total_failure_is_logged(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["platform"])
    await client.patch("/api/v1/ai/features/playground", json={"model_id": "gemini-3.8-flash"})

    fell_back = await _ask(client, world, "__fail_primary__ question")
    failed = await _ask(client, world, "__fail__ question")

    assert fell_back.status_code == 200
    assert fell_back.json()["model_id"] == "gemini-3.1-flash-lite"
    assert failed.status_code == 503
    assert await db.find_one(AiUsage, {"status": "error"}) is not None


async def test_identical_requests_are_answered_from_the_cache(client: AsyncClient, world) -> None:
    await _as(client, world["platform"])
    await client.patch("/api/v1/ai/features/playground", json={"cache_ttl_hours": 2})

    first = await _ask(client, world, "What is   osmosis?")
    second = await _ask(client, world, "what is osmosis?")

    assert first.json()["status"] == "ok"
    assert second.json()["status"] == "cached"
    assert second.json()["cost_paise"] == 0
    assert second.json()["text"] == first.json()["text"]


async def test_a_new_month_inherits_last_months_allocation_with_counters_at_zero(
    client: AsyncClient, db: Db, world
) -> None:
    db.add(
        AiBudget(
            scope="institute",
            institute_id=world["abc"].id,
            month=previous_month_key(month_key(utcnow())),
            limit_paise=99_000,
            used_paise=98_000,
            alerts_sent=[80],
            on_exceed="fallback",
        )
    )
    await db.commit()
    await _as(client, world["platform"])

    response = await client.get(f"/api/v1/ai/budgets/institutes/{world['abc'].id}")

    body = response.json()
    assert body["month"] == month_key(utcnow())
    assert (body["limit_paise"], body["used_paise"], body["alerts_sent"]) == (99_000, 0, [])
    assert body["on_exceed"] == "fallback"


# ------------------------------------------------------------------------- permissions


async def test_only_platform_staff_reach_the_control_room_settings(
    client: AsyncClient, world
) -> None:
    for role in ("abc_admin", "student"):
        await _as(client, world[role])
        assert (await client.get("/api/v1/ai/settings")).status_code == 403
        assert (await client.post("/api/v1/ai/playground", json={"prompt": "x"})).status_code == 403
        assert (await client.get("/api/v1/ai/models")).status_code == 403


async def test_institute_admin_sees_only_their_own_usage_and_budget(
    client: AsyncClient, world
) -> None:
    await _as(client, world["platform"])
    await _ask(client, world)
    await client.post(
        "/api/v1/ai/playground", json={"prompt": "hi", "institute_id": str(world["xyz"].id)}
    )

    await _as(client, world["xyz_admin"])
    usage = (await client.get("/api/v1/ai/usage")).json()
    forced = (await client.get(f"/api/v1/ai/usage?institute_id={world['abc'].id}")).json()
    other_budget = await client.get(f"/api/v1/ai/budgets/institutes/{world['abc'].id}")
    summary = (await client.get("/api/v1/ai/usage/summary")).json()

    assert {r["institute_id"] for r in usage["items"]} == {str(world["xyz"].id)}
    assert forced["total"] == 0
    assert other_budget.status_code == 403
    assert [g["label"] for g in summary["by_institute"]] == ["XYZ College"]


async def test_institute_admin_cannot_change_the_allocation_or_kill_switch(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_admin"])
    url = f"/api/v1/ai/budgets/institutes/{world['abc'].id}"

    assert (await client.put(url, json={"limit_paise": 10**9})).status_code == 403
    assert (await client.put(url, json={"enabled": False})).status_code == 403


async def test_institute_admin_may_lower_but_not_raise_daily_limits(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_admin"])
    abc = str(world["abc"].id)

    lowered = await client.put(
        "/api/v1/ai/role-limits", json={"institute_id": abc, "limits": {"student": 10}}
    )
    raised = await client.put(
        "/api/v1/ai/role-limits", json={"institute_id": abc, "limits": {"student": 31}}
    )
    platform = await client.put("/api/v1/ai/role-limits", json={"limits": {"student": 5}})
    other = await client.put(
        "/api/v1/ai/role-limits",
        json={"institute_id": str(world["xyz"].id), "limits": {"student": 5}},
    )

    assert lowered.status_code == 200
    assert raised.status_code == 422
    assert platform.status_code == 403
    assert other.status_code == 403


async def test_feature_shares_cannot_exceed_the_allocation(client: AsyncClient, world) -> None:
    await _as(client, world["platform"])
    url = f"/api/v1/ai/budgets/institutes/{world['abc'].id}"
    await client.put(url, json={"limit_paise": 1000})

    await _as(client, world["abc_admin"])
    ok = await client.put(url, json={"feature_limits": {"playground": 600}})
    too_much = await client.put(url, json={"feature_limits": {"playground": 1001}})

    assert ok.status_code == 200
    assert too_much.status_code == 422


async def test_providers_never_reveal_a_key(client: AsyncClient, world) -> None:
    await _as(client, world["platform"])
    body = (await client.get("/api/v1/ai/providers")).json()
    assert {p["name"] for p in body} == {"gemini", "anthropic", "fake"}
    assert all(set(p) == {"name", "configured", "fake_mode"} for p in body)


async def test_models_are_data_editable_from_the_control_room(
    client: AsyncClient, db: Db, world
) -> None:
    await _as(client, world["platform"])
    created = await client.post(
        "/api/v1/ai/models",
        json={
            "provider": "anthropic",
            "model_id": "claude-haiku-5-5",
            "display_name": "Claude Haiku 5.5",
            "input_price_per_mtok_usd": 1,
            "output_price_per_mtok_usd": 5,
        },
    )
    duplicate = await client.post(
        "/api/v1/ai/models",
        json={
            "provider": "gemini",
            "model_id": "gemini-3.8-flash",
            "display_name": "Again",
            "input_price_per_mtok_usd": 1,
            "output_price_per_mtok_usd": 1,
        },
    )
    model_id = created.json()["id"]
    updated = await client.patch(
        f"/api/v1/ai/models/{model_id}", json={"output_price_per_mtok_usd": 4.5}
    )
    bad_feature = await client.patch(
        "/api/v1/ai/features/playground", json={"model_id": "no-such-model"}
    )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert updated.json()["output_price_per_mtok_usd"] == 4.5
    assert bad_feature.status_code == 422


async def test_usage_summary_and_export(client: AsyncClient, world) -> None:
    await _as(client, world["platform"])
    await _ask(client, world)
    await _ask(client, world)

    summary = (await client.get("/api/v1/ai/usage/summary")).json()
    export = await client.get("/api/v1/ai/usage/export")

    assert summary["today"]["requests"] == 2
    assert summary["month"]["cost_paise"] == summary["today"]["cost_paise"]
    assert summary["by_feature"][0]["key"] == "playground"
    assert len(summary["trend"]) == 30
    assert summary["trend"][-1]["requests"] == 2
    assert export.status_code == 200
    assert export.content[:2] == b"PK"  # an xlsx is a zip
