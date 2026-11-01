"""Request and response bodies for the AI Control Room. Input and output kept apart."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.ai.models import OnExceed, Provider, SafetyLevel


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------------- settings


class SettingsOut(OrmModel):
    global_enabled: bool
    alert_thresholds: list[int]
    usd_to_inr: float
    log_prompts: bool
    updated_at: datetime


class SettingsUpdate(StrictModel):
    global_enabled: bool | None = None
    alert_thresholds: list[int] | None = Field(default=None, min_length=1, max_length=5)
    usd_to_inr: float | None = Field(default=None, gt=0, le=1000)
    log_prompts: bool | None = None

    @field_validator("alert_thresholds")
    @classmethod
    def _thresholds(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(t < 1 or t > 100 for t in value):
            raise ValueError("Alert thresholds are percentages between 1 and 100.")
        return sorted(set(value))


class ProviderOut(BaseModel):
    name: str
    configured: bool
    #: True when the fake provider is answering everything (local and test).
    fake_mode: bool


# ------------------------------------------------------------------------------- models


class ModelOut(OrmModel):
    id: uuid.UUID
    provider: str
    model_id: str
    display_name: str
    input_price_per_mtok_usd: float
    output_price_per_mtok_usd: float
    enabled: bool


class ModelCreate(StrictModel):
    provider: Provider
    model_id: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._\-]+$")
    display_name: str = Field(min_length=2, max_length=120)
    input_price_per_mtok_usd: float = Field(ge=0, le=1000)
    output_price_per_mtok_usd: float = Field(ge=0, le=1000)
    enabled: bool = True


class ModelUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    input_price_per_mtok_usd: float | None = Field(default=None, ge=0, le=1000)
    output_price_per_mtok_usd: float | None = Field(default=None, ge=0, le=1000)
    enabled: bool | None = None


# ----------------------------------------------------------------------------- features


class FeatureOut(OrmModel):
    key: str
    name: str
    model_id: str
    fallback_model_id: str | None
    max_output_tokens: int
    system_prompt: str
    safety_level: str
    cache_ttl_hours: int
    enabled: bool


class FeatureUpdate(StrictModel):
    model_id: str | None = Field(default=None, max_length=80)
    #: Send an empty string to remove the fallback.
    fallback_model_id: str | None = Field(default=None, max_length=80)
    max_output_tokens: int | None = Field(default=None, ge=16, le=16384)
    system_prompt: str | None = Field(default=None, max_length=8000)
    safety_level: SafetyLevel | None = None
    cache_ttl_hours: int | None = Field(default=None, ge=0, le=24 * 30)
    enabled: bool | None = None


# ------------------------------------------------------------------------------ budgets


class BudgetOut(BaseModel):
    scope: str
    institute_id: uuid.UUID | None
    institute_name: str | None = None
    month: str
    limit_tokens: int | None
    limit_paise: int | None
    used_tokens: int
    used_paise: int
    percent_used: float | None
    on_exceed: str
    alerts_sent: list[int]
    feature_limits: dict[str, int]
    feature_used_paise: dict[str, int]
    disabled_features: list[str]
    enabled: bool
    #: False when nothing has ever been set: the defaults shown are not stored yet.
    configured: bool


class PlatformBudgetUpdate(StrictModel):
    limit_tokens: int | None = Field(default=None, ge=0)
    limit_paise: int | None = Field(default=None, ge=0)
    on_exceed: OnExceed = "block"


class InstituteBudgetUpdate(StrictModel):
    """Every field optional. Allocation, overflow behaviour and the kill switch are the
    platform's to set; the per-feature split and disabled features are also open to the
    institute's own administrators (``ai:usage_read``)."""

    limit_tokens: int | None = Field(default=None, ge=0)
    limit_paise: int | None = Field(default=None, ge=0)
    on_exceed: OnExceed | None = None
    enabled: bool | None = None
    feature_limits: dict[str, int] | None = None
    disabled_features: list[str] | None = Field(default=None, max_length=50)

    @field_validator("feature_limits")
    @classmethod
    def _non_negative(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is not None and any(v < 0 for v in value.values()):
            raise ValueError("A feature's share cannot be negative.")
        return value


# -------------------------------------------------------------------------- role limits


class RoleLimitOut(BaseModel):
    role_key: str
    platform_default: int
    institute_value: int | None
    effective: int


class RoleLimitsUpdate(StrictModel):
    #: Omit for the platform defaults.
    institute_id: uuid.UUID | None = None
    limits: dict[str, int] = Field(min_length=1, max_length=20)

    @field_validator("limits")
    @classmethod
    def _range(cls, value: dict[str, int]) -> dict[str, int]:
        if any(v < 0 or v > 100_000 for v in value.values()):
            raise ValueError("A daily limit is between 0 and 100,000 requests.")
        return value


# -------------------------------------------------------------------------------- usage


class UsageOut(OrmModel):
    id: uuid.UUID
    created_at: datetime
    institute_id: uuid.UUID | None
    user_id: uuid.UUID
    role_key: str | None
    feature_key: str
    provider: str | None
    model_id: str | None
    input_tokens: int
    output_tokens: int
    cost_paise: int
    latency_ms: int
    status: str
    block_reason: str | None
    fallback_used: bool


class UsageTotals(BaseModel):
    requests: int = 0
    tokens: int = 0
    cost_paise: int = 0
    blocked: int = 0
    errors: int = 0


class UsageGroup(BaseModel):
    key: str | None
    label: str
    requests: int
    tokens: int
    cost_paise: int


class UsageDay(BaseModel):
    day: date
    requests: int
    cost_paise: int


class UsageSummary(BaseModel):
    today: UsageTotals
    month: UsageTotals
    by_feature: list[UsageGroup]
    by_institute: list[UsageGroup]
    trend: list[UsageDay]
    budget: BudgetOut | None


UsageStatusFilter = Literal["ok", "blocked", "error", "cached"]


# --------------------------------------------------------------------------- playground


class PlaygroundRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    institute_id: uuid.UUID | None = None
    feature_key: str = Field(default="playground", max_length=40)


class PlaygroundResponse(BaseModel):
    text: str
    status: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_paise: int
    fallback_used: bool
    safety_blocked: bool
    redactions: int
    usage_id: uuid.UUID | None
