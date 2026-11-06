"""Regressions for the AI Control Room review fixes. Every call uses the fake provider."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.db import Db
from app.modules.ai import gateway
from app.modules.ai.models import AiBudget, AiUsage
from app.modules.ai.providers import ProviderRequest, ProviderResult
from app.modules.ai.providers.fake import FakeProvider
from app.modules.audit.models import AuditLog
from app.modules.rbac import service as rbac
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
    }


async def _ask(client: AsyncClient, world, prompt: str = "What is osmosis?", where: str = "abc"):
    return await client.post(
        "/api/v1/ai/playground", json={"prompt": prompt, "institute_id": str(world[where].id)}
    )


async def test_institute_admin_dashboard_shows_their_allocation(client: AsyncClient, world) -> None:
    await _as(client, world["platform"])
    await client.put(
        f"/api/v1/ai/budgets/institutes/{world['abc'].id}", json={"limit_paise": 50_000}
    )

    await _as(client, world["abc_admin"])
    budget = (await client.get("/api/v1/ai/usage/summary")).json()["budget"]

    assert budget["institute_id"] == str(world["abc"].id)
    assert budget["limit_paise"] == 50_000


async def test_institute_admin_lists_feature_names_but_not_prompts(
    client: AsyncClient, world
) -> None:
    await _as(client, world["abc_admin"])

    names = await client.get("/api/v1/ai/features/names")

    assert names.status_code == 200
    assert "playground" in [f["key"] for f in names.json()]
    assert all(set(f) == {"key", "name"} for f in names.json())
    assert (await client.get("/api/v1/ai/features")).status_code == 403


async def test_a_changed_system_prompt_or_safety_level_misses_the_cache(
    client: AsyncClient, world
) -> None:
    await _as(client, world["platform"])
    await client.patch("/api/v1/ai/features/playground", json={"cache_ttl_hours": 2})

    assert (await _ask(client, world)).json()["status"] == "ok"
    assert (await _ask(client, world)).json()["status"] == "cached"
    await client.patch("/api/v1/ai/features/playground", json={"system_prompt": "Be brief."})
    assert (await _ask(client, world)).json()["status"] == "ok"
    await client.patch("/api/v1/ai/features/playground", json={"safety_level": "kids"})
    assert (await _ask(client, world)).json()["status"] == "ok"


async def test_an_unexpected_provider_exception_falls_back_and_is_logged(
    client: AsyncClient, db: Db, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = FakeProvider.complete

    async def flaky(self, request: ProviderRequest) -> ProviderResult:
        if "__boom__" in request.user_text or not request.model_id.endswith("-lite"):
            raise ValueError("response was not JSON")
        return await original(self, request)

    monkeypatch.setattr(FakeProvider, "complete", flaky)
    await _as(client, world["platform"])
    await client.patch("/api/v1/ai/features/playground", json={"model_id": "gemini-3.8-flash"})

    fell_back = await _ask(client, world)
    failed = await _ask(client, world, "__boom__")

    assert fell_back.status_code == 200
    assert fell_back.json()["model_id"] == "gemini-3.1-flash-lite"
    assert failed.status_code == 503
    assert await db.count(AiUsage, {"status": "error", "block_reason": "provider_error"}) == 1


async def test_percent_and_alerts_follow_whichever_limit_is_nearer(
    client: AsyncClient, db: Db, world, outbox
) -> None:
    await _as(client, world["platform"])
    url = f"/api/v1/ai/budgets/institutes/{world['abc'].id}"
    await client.put(url, json={"limit_paise": 10**9, "limit_tokens": 100, "on_exceed": "fallback"})

    for _ in range(4):
        await _ask(client, world, "x" * 200)

    budget = await db.find_one(AiBudget, {"institute_id": world["abc"].id})
    assert sorted(budget.alerts_sent) == [80, 100]
    assert (await client.get(url)).json()["percent_used"] >= 100


async def test_the_daily_limit_counts_each_institute_separately(client: AsyncClient, world) -> None:
    await _as(client, world["platform"])
    await client.put("/api/v1/ai/role-limits", json={"limits": {"platform_admin": 1}})

    assert (await _ask(client, world, where="abc")).status_code == 200
    assert (await _ask(client, world, where="xyz")).status_code == 200
    assert (await _ask(client, world, where="abc")).status_code == 429


async def test_a_safety_refusal_is_logged_as_blocked_and_still_counts(
    client: AsyncClient, db: Db, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(self, request: ProviderRequest) -> ProviderResult:
        return ProviderResult("I can't help with that.", 100_000, 2, safety_blocked=True)

    monkeypatch.setattr(FakeProvider, "complete", refuse)
    await _as(client, world["platform"])
    await client.put("/api/v1/ai/role-limits", json={"limits": {"platform_admin": 1}})

    assert (await _ask(client, world)).json()["safety_blocked"] is True
    assert (await _ask(client, world)).status_code == 429
    row = await db.find_one(AiUsage, {"block_reason": "safety"})
    assert row is not None and row.status == "blocked" and row.cost_paise > 0
    summary = (await client.get("/api/v1/ai/usage/summary")).json()
    assert summary["by_feature"][0]["cost_paise"] == summary["month"]["cost_paise"]


async def test_extra_context_is_redacted(db: Db, world, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    original = FakeProvider.complete

    async def spy(self, request: ProviderRequest) -> ProviderResult:
        seen.append(request.user_text)
        return await original(self, request)

    monkeypatch.setattr(FakeProvider, "complete", spy)
    context = await rbac.get_context(db, world["platform"].id)

    result = await gateway.complete(
        db,
        context=context,
        institute_id=world["abc"].id,
        feature_key="playground",
        prompt="Summarise this.",
        extra_context="Call 9876543210 or mail kid@example.com",
    )

    assert "9876543210" not in seen[0] and "kid@example.com" not in seen[0]
    assert result.redactions == 2


async def test_feature_audit_records_old_and_new_values(client: AsyncClient, db: Db, world) -> None:
    await _as(client, world["platform"])

    await client.patch(
        "/api/v1/ai/features/playground", json={"enabled": False, "system_prompt": "Secret."}
    )

    row = await db.find_one(AuditLog, {"action": "ai_feature_updated"})
    assert row.extra["changes"] == {"enabled": {"from": True, "to": False}}
    assert row.extra["fields"] == ["enabled", "system_prompt"]
    assert "Secret." not in str(row.extra)
