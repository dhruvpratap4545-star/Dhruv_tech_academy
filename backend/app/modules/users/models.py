"""User and preference collections (PRD §6).

A user is one person, identified by email, independent of how many roles they hold or how
many institutes they belong to. Roles live in ``user_role_assignments`` (rbac), never here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator
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


class Guardian(TimestampedDocument):
    """Which adult is responsible for which learner.

    Many-to-many on purpose, in both directions. A parent commonly has two children at the
    same school, and a child commonly has two parents — or a parent and a grandparent, or a
    guardian who is neither. Modelling either side as "one" produces a product that cannot
    describe an ordinary family.

    This document is also the consent record. Under the DPDP Act a child's personal data is
    processed on the basis of verifiable parental consent, and this is where "who is the
    verified parent of this learner" is written down. ``verified_at`` is null until the
    adult has completed setup at their own email address, which is what makes the consent
    verifiable rather than asserted by whoever typed the row in.
    """

    parent_user_id: uuid.UUID
    student_user_id: uuid.UUID
    #: "Mother", "Father", "Guardian" — free text, because families are not an enum.
    relationship: str | None = Field(default=None, max_length=40)
    #: Who the school contacts first. At most one per student is expected, but it is not
    #: enforced: two parents both insisting they are first is a conversation for the
    #: school, not a database error at eleven at night.
    is_primary: bool = False
    #: When the adult proved they control the address. Null until they complete setup.
    verified_at: datetime | None = None
    linked_by: uuid.UUID | None = None

    @model_validator(mode="after")
    def _not_self(self) -> Guardian:
        """A person cannot be their own guardian.

        PostgreSQL stated this as a CHECK constraint. MongoDB has none, so it is a model
        validator — and `validate_on_save` makes it run on every write rather than only on
        construction. It closes a loop that would otherwise let a student read themselves
        as a parent and inherit a second set of permissions.
        """
        if self.parent_user_id == self.student_user_id:
            raise ValueError("A person cannot be their own guardian.")
        return self

    class Settings:
        name = "guardians"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("parent_user_id", ASCENDING), ("student_user_id", ASCENDING)],
                unique=True,
                name="uq_guardians_parent_student",
            ),
            IndexModel([("student_user_id", ASCENDING)], name="ix_guardians_student_user_id"),
            IndexModel([("parent_user_id", ASCENDING)], name="ix_guardians_parent_user_id"),
        ]
