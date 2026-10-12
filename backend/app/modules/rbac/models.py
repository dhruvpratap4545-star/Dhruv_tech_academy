"""Authorization collections: roles, permissions, assignments and module access (PRD §5, §6).

Roles and permissions are documents, not code, so a new module adds permissions as data
(PRD §5.4). ``app.modules.rbac.catalog`` is the source those are seeded from.

An assignment names a role *and* the scope it applies at:

    institute_id null and branch_id null  -> platform scope
    institute_id set, branch_id null      -> whole institute
    institute_id set, branch_id set       -> one branch

Revocation is a timestamp, never a delete — who held what, and when, is audit evidence.
The rules PostgreSQL enforced as CHECK constraints are model validators here, so a document
breaking them cannot be built, let alone saved.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator
from pymongo import ASCENDING, IndexModel

from app.core.db import TimestampedDocument, UuidDocument

SCOPE_LEVELS = ("platform", "institute", "branch")

Effect = Literal["allow", "deny"]


def _branch_needs_institute(institute_id: uuid.UUID | None, branch_id: uuid.UUID | None) -> None:
    if branch_id is not None and institute_id is None:
        raise ValueError("a branch-scoped entry must name its institute")


class Module(TimestampedDocument):
    """A product area (core, wallet, library, …), keyed by a stable human-readable key."""

    key: str = Field(max_length=40)
    name: str = Field(max_length=120)
    description: str | None = Field(default=None, max_length=255)
    # `core` is auth/org/users/rbac itself: always on, never disabled for an institute.
    is_core: bool = False

    class Settings:
        name = "modules"
        use_state_management = True
        validate_on_save = True
        indexes = [IndexModel([("key", ASCENDING)], unique=True, name="uq_modules_key")]  # noqa: RUF012


class Permission(TimestampedDocument):
    key: str = Field(max_length=40)
    module_key: str = Field(max_length=40)
    description: str | None = Field(default=None, max_length=255)

    class Settings:
        name = "permissions"
        use_state_management = True
        validate_on_save = True
        indexes = [IndexModel([("key", ASCENDING)], unique=True, name="uq_permissions_key")]  # noqa: RUF012


class Role(TimestampedDocument):
    """A named bundle of permissions.

    ``institute_id`` is null for the built-in roles and set for one an institute defined
    for itself. Keys stay globally unique — a custom role's key is namespaced with its
    institute code, e.g. ``abc.lab_assistant`` — so every lookup in the engine remains a
    single equality test.
    """

    key: str = Field(max_length=40)
    name: str = Field(max_length=120)
    description: str | None = Field(default=None, max_length=255)
    scope_level: Literal["platform", "institute", "branch"]
    # Higher rank = more authority. Nobody may grant a role at or above their own rank
    # (PRD §3.1). Keeping this a number means the rule is one comparison, not a lookup table.
    rank: int = Field(gt=0)
    is_system: bool = True
    # Parent/Guardian ships inactive. Custom roles are archived by clearing this, never
    # deleted: assignment history must still be able to name the role somebody held.
    is_active: bool = True
    institute_id: uuid.UUID | None = None
    created_by: uuid.UUID | None = None

    @model_validator(mode="after")
    def _custom_needs_institute(self) -> Role:
        # A built-in role belongs to no institute; a custom one to exactly one.
        if self.is_system != (self.institute_id is None):
            raise ValueError("system roles have no institute; custom roles need one")
        return self

    class Settings:
        name = "roles"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("key", ASCENDING)], unique=True, name="uq_roles_key"),
            IndexModel([("institute_id", ASCENDING)], name="ix_roles_institute"),
        ]


class RolePermission(UuidDocument):
    """Role ↔ permission link. No timestamps — the pair *is* the record."""

    role_id: uuid.UUID
    permission_id: uuid.UUID

    class Settings:
        name = "role_permissions"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("role_id", ASCENDING), ("permission_id", ASCENDING)],
                unique=True,
                name="uq_role_permissions_pair",
            ),
        ]


class InstituteRolePermission(TimestampedDocument):
    """One institute's adjustment to what a role allows, inside that institute only.

    The role definition stays the baseline and this records the *difference*:

        effect='allow'  this institute's holders of the role also get this permission
        effect='deny'   this institute's holders of the role do not get it

    Storing the difference rather than a full copy keeps the baseline meaningful: add a
    permission to Faculty in a later release and every institute that customised the role
    still picks it up. Platform-scoped roles are never overridden.
    """

    institute_id: uuid.UUID
    role_id: uuid.UUID
    permission_id: uuid.UUID
    effect: Effect
    created_by: uuid.UUID | None = None

    class Settings:
        name = "institute_role_permissions"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("institute_id", ASCENDING), ("role_id", ASCENDING), ("permission_id", ASCENDING)],
                unique=True,
                name="uq_institute_role_permissions",
            ),
            IndexModel([("role_id", ASCENDING)], name="ix_institute_role_permissions_role"),
        ]


class UserRoleAssignment(TimestampedDocument):
    user_id: uuid.UUID
    role_id: uuid.UUID
    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    granted_by: uuid.UUID | None = None
    revoked_at: datetime | None = None
    revoked_by: uuid.UUID | None = None

    @model_validator(mode="after")
    def _scope_shape(self) -> UserRoleAssignment:
        _branch_needs_institute(self.institute_id, self.branch_id)
        return self

    class Settings:
        name = "user_role_assignments"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            # The hot path: every live assignment for this user.
            IndexModel(
                [("user_id", ASCENDING), ("revoked_at", ASCENDING)],
                name="ix_user_role_assignments_user_live",
            ),
            IndexModel([("institute_id", ASCENDING)], name="ix_user_role_assignments_institute"),
            IndexModel([("branch_id", ASCENDING)], name="ix_user_role_assignments_branch"),
            IndexModel([("role_id", ASCENDING)], name="ix_user_role_assignments_role"),
        ]


class UserPermissionGrant(TimestampedDocument):
    """One permission given to — or taken away from — a single person at a single scope.

    * ``effect`` — ``deny`` beats every allow from every role, a Super Admin's included.
    * ``reason`` — required: an exception nobody can explain is one nobody dares remove.
    * ``expires_at`` — optional: covering someone's leave, not widening their job for ever.
    """

    user_id: uuid.UUID
    permission_id: uuid.UUID
    effect: Effect = "allow"
    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    reason: str = Field(min_length=1, max_length=255)
    expires_at: datetime | None = None
    granted_by: uuid.UUID | None = None
    revoked_at: datetime | None = None
    revoked_by: uuid.UUID | None = None

    @model_validator(mode="after")
    def _scope_shape(self) -> UserPermissionGrant:
        _branch_needs_institute(self.institute_id, self.branch_id)
        return self

    class Settings:
        name = "user_permission_grants"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("user_id", ASCENDING), ("revoked_at", ASCENDING)],
                name="ix_user_permission_grants_user_live",
            ),
            IndexModel([("institute_id", ASCENDING)], name="ix_user_permission_grants_institute"),
        ]


class InstituteModule(TimestampedDocument):
    """Which modules an institute may use (PRD §5.2 step 5). Absent means not enabled."""

    institute_id: uuid.UUID
    module_key: str = Field(max_length=40)
    enabled: bool = True
    valid_till: date | None = None

    class Settings:
        name = "institute_modules"
        use_state_management = True
        validate_on_save = True
        bson_encoders = {date: lambda d: d.isoformat()}  # noqa: RUF012
        indexes = [  # noqa: RUF012
            IndexModel(
                [("institute_id", ASCENDING), ("module_key", ASCENDING)],
                unique=True,
                name="uq_institute_modules",
            ),
        ]
