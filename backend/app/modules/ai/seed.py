"""Defaults for the AI Control Room, written by ``python -m app.cli seed``.

Insert-only, like the rest of the seed: a price or a limit an administrator changed in the
Control Room is never put back on the next deploy. Only missing rows are created.

Model prices are Google's published paid-tier text prices on 30-10-2026, USD per million
tokens (prompts up to 200k). They are a starting point for the admin to confirm — note
that ``gemini-3.8-flash`` is scheduled to double on 01-01-2027.
"""

from __future__ import annotations

from app.core.db import Db
from app.modules.ai.models import SETTINGS_KEY, AiFeature, AiModel, AiRoleLimit, AiSettings
from app.modules.rbac import catalog

DEFAULT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODEL = "gemini-3.1-flash-lite"

MODELS: tuple[tuple[str, str, str, float, float], ...] = (
    # provider, model id, display name, input $/Mtok, output $/Mtok
    ("gemini", "gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", 0.30, 2.50),
    ("gemini", "gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", 0.25, 1.50),
    ("gemini", "gemini-3.8-flash", "Gemini 3.8 Flash", 0.75, 3.75),
)

FEATURES: tuple[dict, ...] = (
    {
        "key": "playground",
        "name": "Playground (admin test prompts)",
        "model_id": DEFAULT_MODEL,
        "fallback_model_id": FALLBACK_MODEL,
        "max_output_tokens": 1024,
        "system_prompt": (
            "You are the Dhruv Online Academy assistant. Answer clearly and briefly in the "
            "language of the question (Hindi or English)."
        ),
        "safety_level": "standard",
        "cache_ttl_hours": 0,
    },
)

#: Platform defaults from the implementation plan. Admins of every kind get 200.
ROLE_LIMITS: dict[str, int] = {
    catalog.STUDENT: 30,
    catalog.PARENT: 10,
    catalog.FACULTY: 100,
    catalog.BRANCH_ADMIN: 200,
    catalog.INSTITUTE_ADMIN: 200,
    catalog.ORG_ADMIN: 200,
    catalog.PLATFORM_ADMIN: 200,
    catalog.SUPER_ADMIN: 200,
}
#: For a custom role with no row of its own: the most restrictive default.
UNLISTED_ROLE_LIMIT = 30


async def seed_ai(db: Db) -> None:
    if await db.find_one(AiSettings, {"key": SETTINGS_KEY}) is None:
        db.add(AiSettings())

    existing_models = {m.model_id for m in await db.find(AiModel, {})}
    for provider, model_id, name, price_in, price_out in MODELS:
        if model_id not in existing_models:
            db.add(
                AiModel(
                    provider=provider,  # type: ignore[arg-type]
                    model_id=model_id,
                    display_name=name,
                    input_price_per_mtok_usd=price_in,
                    output_price_per_mtok_usd=price_out,
                )
            )

    existing_features = {f.key for f in await db.find(AiFeature, {})}
    for feature in FEATURES:
        if feature["key"] not in existing_features:
            db.add(AiFeature(**feature))

    existing_limits = {r.role_key for r in await db.find(AiRoleLimit, {"institute_id": None})}
    for role_key, limit in ROLE_LIMITS.items():
        if role_key not in existing_limits:
            db.add(AiRoleLimit(role_key=role_key, daily_requests=limit))
