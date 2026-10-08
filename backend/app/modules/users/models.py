"""User and preference tables (PRD §6).

A user is one person, identified by email, independent of how many roles they hold or how
many institutes they belong to. Roles live in ``user_role_assignments`` (rbac), never here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, MediumStr, ShortStr, TimestampMixin, Uuid, UuidPkMixin

USER_STATUSES = ("invited", "active", "suspended", "deleted")
THEMES = ("light", "dark", "system")


class User(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'deleted')", name="users_status"
        ),
        # Case-insensitive uniqueness. Emails are also lowercased on write, so this is
        # belt and braces — it stops a direct SQL insert creating a duplicate identity.
        Index("uq_users_lower_email", func.lower(ShortStr.__class__ and "email"), unique=True),
    )

    email: Mapped[str] = mapped_column(ShortStr, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(MediumStr)
    full_name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="invited")

    # Login protection (PRD §7.4). Counters live on the row so a lockout survives a restart
    # and applies across every instance, unlike an in-memory counter.
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # DPDP consent (PRD §11): recorded once, at sign-up, with what was agreed to.
    consent_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(String(20))

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class UserPreference(TimestampMixin, Base):
    """One row per user. The user id is the primary key — there is nothing else to key on."""

    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("theme IN ('light', 'dark', 'system')", name="user_preferences_theme"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[str] = mapped_column(String(10), nullable=False, default="system")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
