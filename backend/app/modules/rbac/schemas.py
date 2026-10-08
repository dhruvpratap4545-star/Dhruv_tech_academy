"""Request and response bodies for the access-control endpoints (ADR-017).

Two things leave this module: the *catalogue* (what roles and permissions exist, and what
each allows) and the *exceptions* (what has been granted to, or blocked for, one person).
Both are read far more often than they are written — an administrator reviewing access
reads a dozen times before changing anything — so the shapes here are built for reading:
every row carries the human label it needs, and nothing requires a second lookup.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ScopeLevel = Literal["platform", "institute", "branch"]
Effect = Literal["allow", "deny"]

RoleName = Annotated[str, Field(min_length=2, max_length=60)]
Reason = Annotated[str, Field(min_length=4, max_length=255)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------------------ catalogue


class PermissionOut(BaseModel):
    """One permission, with everything the UI needs to show and group it."""

    key: str
    description: str
    group: str
    module_key: str
    resource: str
    action: str


class RoleOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    scope_level: str
    rank: int
    is_system: bool
    is_active: bool
    institute_id: uuid.UUID | None
    permissions: list[str]
    # How many people currently hold it. Shown so nobody archives a role out from under
    # forty users without being told first.
    holder_count: int
    # Whether *this* caller may edit it — the server already knows, and making the UI
    # re-derive it from rank and institute is how a button appears that the API refuses.
    editable: bool


class RoleCreateRequest(StrictModel):
    """A role an institute defines for itself.

    ``rank`` must sit strictly below the creator's and ``permissions`` must be a subset of
    what the creator holds; both are enforced in the service, not here, because neither is
    knowable from the request alone.
    """

    name: RoleName
    description: Annotated[str | None, Field(max_length=255)] = None
    scope_level: ScopeLevel
    rank: Annotated[int, Field(ge=1, le=99)]
    institute_id: uuid.UUID
    permissions: Annotated[list[str], Field(min_length=1, max_length=200)]

    @field_validator("permissions")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("The same permission is listed more than once.")
        return value


class RoleUpdateRequest(StrictModel):
    """Everything optional: the UI sends only what changed.

    ``rank`` and ``scope_level`` are deliberately absent. Changing either on a role people
    already hold would silently rewrite what those people can do, in a way no audit row
    could sensibly describe. Archive it and make a new one instead.
    """

    name: RoleName | None = None
    description: Annotated[str | None, Field(max_length=255)] = None
    permissions: Annotated[list[str] | None, Field(min_length=1, max_length=200)] = None


# ----------------------------------------------------------------------- personal grants


class GrantCreateRequest(StrictModel):
    permission: Annotated[str, Field(min_length=3, max_length=40)]
    effect: Effect = "allow"
    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    reason: Reason
    expires_at: datetime | None = None


class GrantOut(BaseModel):
    id: uuid.UUID
    permission: str
    description: str
    effect: str
    institute_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    scope_label: str
    reason: str
    expires_at: datetime | None
    expired: bool
    granted_by_name: str | None
    created_at: datetime


# --------------------------------------------------------------------------- my own access


class EffectivePermission(BaseModel):
    """One line of the "what can I actually do" answer.

    Both held and unheld permissions are returned. A screen whose whole purpose is to
    explain someone's access has to show the boundary, not just the inside of it — and
    this is the one place in the product that does (ADR-018).
    """

    key: str
    description: str
    group: str
    granted: bool
    # "All institutes", "Own institute", "Own branch", or "" when not granted.
    scope_label: str
    # role | direct | blocked — where the answer came from, so an exception is visible
    # as an exception rather than blending into the role.
    source: str


class AccessRoleOut(BaseModel):
    key: str
    name: str
    rank: int
    scope_level: str
    scope_label: str
    institute_id: uuid.UUID | None
    branch_id: uuid.UUID | None


class MyAccessOut(BaseModel):
    roles: list[AccessRoleOut]
    permissions: list[EffectivePermission]
    granted_count: int
    total_count: int
    # Roles this person may hand to someone else, by name. The honest answer to "who can
    # I add?", which is the question people actually bring to this screen.
    can_grant_roles: list[str]
    direct_grants: list[GrantOut]
