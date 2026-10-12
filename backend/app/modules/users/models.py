"""User and preference collections (PRD §6).

A user is one person, identified by email, independent of how many roles they hold or how
many institutes they belong to. Roles live in ``user_role_assignments`` (rbac), never here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.core.db import TimestampedDocument

USER_STATUSES = ("invited", "active", "suspended", "deleted")
THEMES = ("light", "dark", "system")

# Lowercased on the way in, so the plain unique index on `email` is case-insensitive in
# effect — the job the `lower(email)` index did in PostgreSQL.
Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=120)]


class User(TimestampedDocument):
    email: Email
    password_hash: str | None = Field(default=None, max_length=255)
    full_name: str = Field(max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    status: Literal["invited", "active", "suspended", "deleted"] = "invited"

    # Login protection (PRD §7.4). Counters live on the document so a lockout survives a
    # restart and applies across every instance, unlike an in-memory counter.
    failed_login_count: int = Field(default=0, ge=0)
    locked_until: datetime | None = None
    password_changed_at: datetime | None = None
    last_login_at: datetime | None = None

    # DPDP consent (PRD §11): recorded once, at sign-up, with what was agreed to.
    consent_accepted_at: datetime | None = None
    consent_version: str | None = Field(default=None, max_length=20)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    class Settings:
        name = "users"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012 - Beanie reads this class attribute as configuration
            IndexModel([("email", ASCENDING)], unique=True, name="uq_users_email"),
            # Keyset pagination: newest first, id as the tie-breaker.
            IndexModel([("created_at", DESCENDING), ("_id", DESCENDING)], name="ix_users_page"),
        ]


class UserPreference(TimestampedDocument):
    """One per user."""

    user_id: uuid.UUID
    theme: Literal["light", "dark", "system"] = "system"
    language: str = Field(default="en", max_length=10)

    class Settings:
        name = "user_preferences"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("user_id", ASCENDING)], unique=True, name="uq_user_preferences_user"),
        ]
