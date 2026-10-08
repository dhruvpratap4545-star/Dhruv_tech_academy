"""Request and response bodies for the user endpoints (PRD §8).

``UserOut`` is the only user shape that leaves this service. It deliberately has no
``password_hash``, ``failed_login_count`` or ``locked_until`` — those exist for the login
flow and telling an attacker how close an account is to locking helps nobody.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

UserStatus = Literal["invited", "active", "suspended"]
Theme = Literal["light", "dark", "system"]

Name = Annotated[str, Field(min_length=2, max_length=120)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ScopeRef(BaseModel):
    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None


class InviteUserRequest(StrictModel):
    """PRD §4.2. The role and its scope are part of the invitation: a user with no role
    could log in and see nothing, which reads as a broken account."""

    full_name: Name
    email: EmailStr
    role_key: str = Field(max_length=40)
    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    phone: str | None = Field(default=None, max_length=20)
    class_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=50,
        description="Classes to link the new user to: enrolment for a student, teaching "
        "assignment for a faculty member.",
    )


class AssignRoleRequest(StrictModel):
    role_key: str = Field(max_length=40)
    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None


class RevokeRoleRequest(StrictModel):
    role_key: str = Field(max_length=40)
    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None


class UpdateStatusRequest(StrictModel):
    status: Literal["active", "suspended"]
    reason: str | None = Field(default=None, max_length=255)


class UpdateProfileRequest(StrictModel):
    full_name: Name | None = None
    phone: str | None = Field(default=None, max_length=20)


class UpdatePreferencesRequest(StrictModel):
    theme: Theme | None = None
    language: str | None = Field(default=None, max_length=10)


class RoleAssignmentOut(BaseModel):
    """A role plus where it applies.

    The names travel with the ids so a list can render "ABC College · MCA" without a
    lookup request per row.
    """

    role_key: str
    role_name: str
    # The rank travels too. Custom roles have keys the frontend has never seen,
    # so a hardcoded key->rank table there would silently score them zero and get every
    # "who outranks whom" decision wrong.
    rank: int = 0
    institute_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    institute_name: str | None = None
    branch_name: str | None = None


class UserOut(OrmModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    status: str
    last_login_at: datetime | None
    created_at: datetime


class UserDetailOut(UserOut):
    roles: list[RoleAssignmentOut] = Field(default_factory=list)


class PreferencesOut(OrmModel):
    theme: str
    language: str


class OverviewOut(BaseModel):
    """Counts for the dashboard tiles, scoped to what the caller may see.

    Every number here is a real COUNT over the caller's scope. The alternative — tiles
    showing the length of the first page — would quietly understate anything past 20.
    """

    users_total: int
    users_active: int
    users_invited: int
    users_suspended: int
    institutes_total: int
    security_events_24h: int


class MeOut(BaseModel):
    """What the frontend needs to render the shell: who you are, what you may do, where.

    ``permissions`` is the flat set of keys the user holds anywhere. The UI uses it to
    decide which menus to draw; it is never the authorization decision, which the backend
    makes per request against the target scope.
    """

    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    status: str
    permissions: list[str]
    roles: list[RoleAssignmentOut]
    institute_ids: list[uuid.UUID]
    preferences: PreferencesOut


class InviteUserResponse(BaseModel):
    user: UserOut
    invitation_sent: bool = True


class RoleOut(OrmModel):
    key: str
    name: str
    scope_level: str
    rank: int
