"""Authorization tables: roles, permissions, assignments and module access (PRD §5, §6).

Roles and permissions are rows, not code, so a new module adds permissions as data
(PRD §5.4). ``app.modules.rbac.catalog`` is the source those rows are seeded from.

An assignment names a role *and* the scope it applies at:

    institute_id NULL and branch_id NULL  -> platform scope
    institute_id set, branch_id NULL      -> whole institute
    institute_id set, branch_id set       -> one branch

Revocation is a timestamp, never a delete — who held what, and when, is audit evidence.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CodeStr, MediumStr, ShortStr, TimestampMixin, Uuid, UuidPkMixin

SCOPE_LEVELS = ("platform", "institute", "branch")


class Module(TimestampMixin, Base):
    """A product area (core, wallet, library, …). The key is the primary key: it is stable,
    human-readable, and referenced from ``permissions.module_key``."""

    __tablename__ = "modules"

    key: Mapped[str] = mapped_column(CodeStr, primary_key=True)
    name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    description: Mapped[str | None] = mapped_column(MediumStr)
    # `core` is auth/org/users/rbac itself: always on, never disabled for an institute.
    is_core: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Permission(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("key", name="uq_permissions_key"),)

    key: Mapped[str] = mapped_column(CodeStr, nullable=False)
    module_key: Mapped[str] = mapped_column(
        CodeStr, ForeignKey("modules.key", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(MediumStr)


class Role(UuidPkMixin, TimestampMixin, Base):
    """A named bundle of permissions.

    ``institute_id`` is NULL for the six built-in roles and set for one an institute
    defined for itself. Keys stay globally unique — a custom role's key is
    namespaced with its institute code, e.g. ``abc.lab_assistant`` — so every lookup in
    the engine remains a single equality test and no caller has to carry an institute
    around just to name a role.
    """

    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            "scope_level IN ('platform', 'institute', 'branch')", name="roles_scope_level"
        ),
        CheckConstraint("rank > 0", name="roles_rank_positive"),
        # A built-in role belongs to no institute; a custom one must belong to exactly one.
        CheckConstraint(
            "(is_system AND institute_id IS NULL) OR (NOT is_system AND institute_id IS NOT NULL)",
            name="roles_custom_needs_institute",
        ),
        UniqueConstraint("key", name="uq_roles_key"),
        Index("ix_roles_institute_id", "institute_id"),
    )

    key: Mapped[str] = mapped_column(CodeStr, nullable=False)
    name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    description: Mapped[str | None] = mapped_column(MediumStr)
    scope_level: Mapped[str] = mapped_column(String(16), nullable=False)
    # Higher rank = more authority. Nobody may grant a role at or above their own rank
    # (PRD §3.1). Keeping this a number means the rule is one comparison, not a lookup table.
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Parent/Guardian ships inactive: designed in M1, granted later with Kids Zone.
    # Custom roles are archived by clearing this, never deleted: assignment history must
    # still be able to name the role somebody held.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    institute_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="CASCADE")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


class RolePermission(Base):
    """Join table. No surrogate key and no timestamps — the pair *is* the row."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class InstituteRolePermission(TimestampMixin, Base):
    """One institute's adjustment to what a role allows, inside that institute only.

    The six built-in roles mean the same thing everywhere, which is what makes them
    supportable — but "Faculty" is not the same job at a coaching centre and a degree
    college, and forcing every customer onto one definition either over-grants somebody or
    blocks work the product is supposed to enable.

    So the role definition stays the baseline and this table records the *difference*:

        effect='allow'  this institute's holders of the role also get this permission
        effect='deny'   this institute's holders of the role do not get it

    Storing the difference rather than a full copy is what keeps the baseline meaningful.
    A copy would freeze on the day it was made: add a permission to Faculty in a later
    release and every institute that had ever customised the role would silently miss it.

    Platform-scoped roles are never overridden — they belong to no institute, so there is
    no institute whose view could differ.
    """

    __tablename__ = "institute_role_permissions"
    __table_args__ = (
        CheckConstraint("effect IN ('allow', 'deny')", name="institute_role_permissions_effect"),
        Index("ix_institute_role_permissions_role", "role_id"),
        # PostgreSQL does not index the referencing side of a foreign key on its own,
        # and without these every delete from `permissions` or `users` has to scan this
        # whole table to check the constraint.
        Index("ix_institute_role_permissions_permission", "permission_id"),
        Index("ix_institute_role_permissions_created_by", "created_by"),
    )

    institute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )
    effect: Mapped[str] = mapped_column(String(8), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


class UserRoleAssignment(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        # A branch-scoped assignment must name the institute the branch belongs to.
        CheckConstraint(
            "branch_id IS NULL OR institute_id IS NOT NULL",
            name="user_role_assignments_branch_needs_institute",
        ),
        # The hot path is "every live assignment for this user". Partial index keeps it
        # small: revoked rows are history and are never read by the permission check.
        Index(
            "ix_user_role_assignments_user_id_live",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_user_role_assignments_institute_id", "institute_id"),
        Index("ix_user_role_assignments_branch_id", "branch_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    institute_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="CASCADE")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="CASCADE")
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


class UserPermissionGrant(UuidPkMixin, TimestampMixin, Base):
    """One permission given to — or taken away from — a single person at a single scope.

    The per-user authorization layer. A role answers "what does this job allow?"; this answers
    "what is different about this person?". Three fields carry most of the weight:

    * ``effect`` — ``deny`` beats every allow from every role, including a Super Admin's.
      That is the whole point: "never, anywhere" should not require reasoning about what
      roles someone might also hold now or acquire later.
    * ``reason`` — required, because an exception nobody can explain is an exception nobody
      dares remove, and those accumulate until the role model means nothing.
    * ``expires_at`` — optional, but it is the difference between covering for someone's
      leave and quietly widening their job for ever.
    """

    __tablename__ = "user_permission_grants"
    __table_args__ = (
        CheckConstraint("effect IN ('allow', 'deny')", name="user_permission_grants_effect"),
        CheckConstraint(
            "branch_id IS NULL OR institute_id IS NOT NULL",
            name="user_permission_grants_branch_needs_institute",
        ),
        # Same shape as the role-assignment index, for the same reason: the permission
        # check reads only live rows, and revoked ones are history it must never pay for.
        Index(
            "ix_user_permission_grants_user_id_live",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_user_permission_grants_institute_id", "institute_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )
    effect: Mapped[str] = mapped_column(String(8), nullable=False, default="allow")
    institute_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="CASCADE")
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="CASCADE")
    )
    reason: Mapped[str] = mapped_column(MediumStr, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


class InstituteModule(TimestampMixin, Base):
    """Which modules an institute may use (PRD §5.2 step 5). Absent row means not enabled."""

    __tablename__ = "institute_modules"

    institute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="CASCADE"), primary_key=True
    )
    module_key: Mapped[str] = mapped_column(
        CodeStr, ForeignKey("modules.key", ondelete="RESTRICT"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    valid_till: Mapped[date | None] = mapped_column(Date)
