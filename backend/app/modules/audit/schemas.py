"""Audit log response shapes (PRD §8)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    target_type: str | None
    target_id: uuid.UUID | None
    institute_id: uuid.UUID | None
    ip: str | None
    metadata_: dict[str, Any] | None = Field(
        default=None, alias="extra", serialization_alias="metadata"
    )
    request_id: str | None
    created_at: datetime

    @field_validator("ip", mode="before")
    @classmethod
    def _address_to_text(cls, value: object) -> str | None:
        """PostgreSQL ``INET`` comes back from asyncpg as an ``IPv4Address`` object, not a
        string, and Pydantic will not coerce one into ``str`` on its own.

        Worth the explicit conversion rather than typing the field as ``IPvAnyAddress``:
        the API contract is a plain string, and an address that somehow fails to parse
        should still be reportable in the audit log rather than failing the whole page.
        """
        if value is None:
            return None
        if isinstance(value, IPv4Address | IPv6Address):
            return str(value)
        return str(value)


class DailySignins(BaseModel):
    """One day of the dashboard chart."""

    day: date
    successful: int
    failed: int
    locked: int


class SigninStats(BaseModel):
    """Sign-in activity for the caller's scope.

    Every day in the window is present, including the quiet ones. A chart that silently
    drops empty days compresses its own x-axis and turns a weekend into a cliff.
    """

    days: list[DailySignins]
    total_successful: int
    total_failed: int
    total_locked: int
