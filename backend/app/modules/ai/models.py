"""AI Control Room collections (Phase 3, Module A).

Money is stored as integer **paise**, never a float: a float total drifts by fractions of a
paisa per request, and after a month of a few hundred thousand requests the dashboard and
the bill disagree. Prices are entered by an administrator as USD per million tokens (the
unit providers publish), and converted with the platform's agreed USD→INR rate.

Budget counters only ever move by ``$inc`` (``Db.increment``), so concurrent requests never
overwrite each other's spend.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.core.db import TimestampedDocument, UuidDocument, utcnow

Provider = Literal["gemini", "anthropic", "fake"]
SafetyLevel = Literal["standard", "kids"]
OnExceed = Literal["block", "fallback"]
UsageStatus = Literal["ok", "blocked", "error", "cached"]
#: Requests a provider answered, including those its own safety filter refused (logged as
#: ``blocked`` / ``safety``, but still billed): what the daily limit counts and what the
#: spend breakdowns add up.
ANSWERED = {"$or": [{"status": {"$in": ["ok", "cached"]}}, {"block_reason": "safety"}]}

SETTINGS_KEY = "global"
#: Usage rows are kept for 13 months, then removed by MongoDB itself (TTL index).
USAGE_RETENTION_SECONDS = 395 * 24 * 3600


class AiSettings(TimestampedDocument):
    """The platform-wide singleton. ``global_enabled`` is the master kill switch."""

    key: str = SETTINGS_KEY
    global_enabled: bool = True
    alert_thresholds: list[int] = Field(default_factory=lambda: [80, 100])
    #: Rate used to turn a provider's USD price into rupees. Agreed with the client and
    #: entered here, not fetched: a cost that changes when nobody changed anything cannot
    #: be reconciled against an invoice.
    usd_to_inr: float = Field(default=88.0, gt=0)
    #: Off by default: the question a student typed is personal data and is not kept.
    log_prompts: bool = False
    updated_by: uuid.UUID | None = None

    class Settings:
        name = "ai_settings"
        use_state_management = True
        validate_on_save = True
        indexes = [IndexModel([("key", ASCENDING)], unique=True, name="uq_ai_settings_key")]  # noqa: RUF012


class AiModel(TimestampedDocument):
    provider: Provider
    model_id: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=2, max_length=120)
    input_price_per_mtok_usd: float = Field(ge=0)
    output_price_per_mtok_usd: float = Field(ge=0)
    enabled: bool = True

    class Settings:
        name = "ai_models"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("model_id", ASCENDING)], unique=True, name="uq_ai_models_model_id"),
        ]


class AiFeature(TimestampedDocument):
    """One AI feature — "playground" now; "homework_hint", "topic_notes"… in later
    milestones. Its prompt and limits are data, so they can be tuned without a release."""

    key: str = Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(max_length=120)
    model_id: str = Field(max_length=80)
    fallback_model_id: str | None = Field(default=None, max_length=80)
    max_output_tokens: int = Field(default=1024, ge=16, le=16384)
    system_prompt: str = Field(default="", max_length=8000)
    safety_level: SafetyLevel = "standard"
    #: 0 turns caching off for this feature.
    cache_ttl_hours: int = Field(default=0, ge=0, le=24 * 30)
    enabled: bool = True

    class Settings:
        name = "ai_features"
        use_state_management = True
        validate_on_save = True
        indexes = [IndexModel([("key", ASCENDING)], unique=True, name="uq_ai_features_key")]  # noqa: RUF012


class AiBudget(TimestampedDocument):
    """One month of one budget: the platform's, or one institute's allocation.

    ``None`` for a limit means "no cap at this level" — an institute with no allocation
    set is still capped by the platform budget above it.
    """

    scope: Literal["platform", "institute"]
    institute_id: uuid.UUID | None = None
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    limit_tokens: int | None = Field(default=None, ge=0)
    limit_paise: int | None = Field(default=None, ge=0)
    used_tokens: int = 0
    used_paise: int = 0
    on_exceed: OnExceed = "block"
    alerts_sent: list[int] = Field(default_factory=list)
    #: An institute admin's split of their allocation: feature key -> paise per month.
    feature_limits: dict[str, int] = Field(default_factory=dict)
    feature_used_paise: dict[str, int] = Field(default_factory=dict)
    disabled_features: list[str] = Field(default_factory=list)
    #: The institute kill switch (ignored on the platform row, which has the global one).
    enabled: bool = True

    class Settings:
        name = "ai_budgets"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("scope", ASCENDING), ("institute_id", ASCENDING), ("month", ASCENDING)],
                unique=True,
                name="uq_ai_budgets_scope_institute_month",
            ),
        ]


class AiRoleLimit(TimestampedDocument):
    """Daily AI requests per person, by role. ``institute_id`` null is the platform default;
    an institute row may only lower it."""

    institute_id: uuid.UUID | None = None
    role_key: str = Field(max_length=40)
    daily_requests: int = Field(ge=0, le=100_000)

    class Settings:
        name = "ai_role_limits"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("institute_id", ASCENDING), ("role_key", ASCENDING)],
                unique=True,
                name="uq_ai_role_limits_institute_role",
            ),
        ]


class AiUsage(UuidDocument):
    """One AI request, append-only. No prompt text unless ``log_prompts`` is on."""

    created_at: datetime = Field(default_factory=utcnow)
    institute_id: uuid.UUID | None = None
    user_id: uuid.UUID
    role_key: str | None = Field(default=None, max_length=40)
    feature_key: str = Field(max_length=40)
    provider: str | None = Field(default=None, max_length=20)
    model_id: str | None = Field(default=None, max_length=80)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_paise: int = 0
    latency_ms: int = 0
    status: UsageStatus
    block_reason: str | None = Field(default=None, max_length=60)
    fallback_used: bool = False
    prompt: str | None = None

    class Settings:
        name = "ai_usage"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("institute_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_ai_usage_institute_created",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_ai_usage_user_created",
            ),
            IndexModel(
                [("feature_key", ASCENDING), ("created_at", DESCENDING)],
                name="ix_ai_usage_feature_created",
            ),
            IndexModel(
                [("created_at", ASCENDING)],
                expireAfterSeconds=USAGE_RETENTION_SECONDS,
                name="ttl_ai_usage_created",
            ),
        ]


class AiCache(UuidDocument):
    """A saved answer to a repeated identical request. Removed by MongoDB at ``expires_at``."""

    key: str = Field(min_length=64, max_length=64)
    feature_key: str = Field(max_length=40)
    model_id: str = Field(max_length=80)
    response: str
    input_tokens: int = 0
    output_tokens: int = 0
    expires_at: datetime

    class Settings:
        name = "ai_cache"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("key", ASCENDING)], unique=True, name="uq_ai_cache_key"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_ai_cache"),
        ]
