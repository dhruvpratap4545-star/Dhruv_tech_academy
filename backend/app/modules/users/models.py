"""User and preference tables (PRD §6).

A user is one person, identified by email, independent of how many roles they hold or how
many institutes they belong to. Roles live in ``user_role_assignments`` (rbac), never here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
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


class Guardian(UuidPkMixin, TimestampMixin, Base):
    """Which adult is responsible for which learner.

    Many-to-many on purpose, in both directions. A parent commonly has two children at the
    same school, and a child commonly has two parents — or a parent and a grandparent, or a
    guardian who is neither. Modelling either side as "one" produces a product that cannot
    describe an ordinary family.

    This row is also the consent record. Under the DPDP Act a child's personal data is
    processed on the basis of verifiable parental consent, and this is where "who is the
    verified parent of this learner" is written down. ``verified_at`` is null until the
    adult has completed setup at their own email address, which is what makes the consent
    verifiable rather than asserted by whoever typed the row in.
    """

    __tablename__ = "guardians"
    __table_args__ = (
        UniqueConstraint("parent_user_id", "student_user_id", name="uq_guardians_parent_student"),
        # A person cannot be their own guardian. Cheap to state, and it closes a loop that
        # would otherwise make a student able to read themselves as a parent and inherit
        # a second set of permissions.
        CheckConstraint("parent_user_id <> student_user_id", name="guardians_not_self"),
        Index("ix_guardians_student_user_id", "student_user_id"),
        Index("ix_guardians_parent_user_id", "parent_user_id"),
    )

    parent_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: "Mother", "Father", "Guardian" — free text, because families are not an enum.
    relationship: Mapped[str | None] = mapped_column(String(40))
    #: Who the school contacts first. At most one per student is expected, but it is not
    #: enforced: two parents both insisting they are first is a conversation for the
    #: school, not a database error at eleven at night.
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: When the adult proved they control the address. Null until they complete setup.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
