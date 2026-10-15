"""The hierarchy: Platform → Organisation → Institute → Branch → Academic Session → Class.

Every institute-scoped collection carries ``institute_id`` even where it could be derived.
That is deliberate: tenant isolation becomes one equality filter on every query, so a
missing filter shows up as a missing condition rather than a subtle lookup mistake.

MongoDB has no foreign keys, so the services check that a parent exists before writing a
child — which they already did, to return a useful 404.

Nothing here is ever hard-deleted — status moves to ``archived`` (PRD §2 rule 6).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import Field, model_validator
from pymongo import ASCENDING, IndexModel

from app.core.db import TimestampedDocument

INSTITUTE_TYPES = ("school", "college", "coaching", "academy")
ORG_STATUSES = ("active", "archived")
ENROLLMENT_STATUSES = ("active", "left")

OrgStatus = Literal["active", "archived"]


class Organisation(TimestampedDocument):
    """A group of institutes under one owner — "JSPM Group of Institutes", "MIT".

    Optional, and most institutes will never belong to one. A standalone coaching centre
    has no organisation, and everything that existed before this level keeps working with
    ``Institute.organisation_id`` left null.

    It exists for one reason: a trust or university running four colleges wants one
    administrator who can see all four, without being given the whole platform. Without
    this level the only way to express that is four separate Institute Admin assignments,
    which then have to be remembered every time a fifth college is added.
    """

    name: str = Field(max_length=120)
    code: str = Field(max_length=40)
    status: OrgStatus = "active"
    logo_url: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=120)

    class Settings:
        name = "organisations"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("code", ASCENDING)], unique=True, name="uq_organisations_code")
        ]


class Institute(TimestampedDocument):
    # Nullable, because belonging to an organisation is the exception rather than the
    # rule. There is no foreign key to enforce it — MongoDB has none — so the service
    # checks the organisation exists before writing, and archiving an organisation never
    # touches its institutes.
    organisation_id: uuid.UUID | None = None
    name: str = Field(max_length=120)
    code: str = Field(max_length=40)
    type: Literal["school", "college", "coaching", "academy"]
    status: OrgStatus = "active"
    logo_url: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=120)
    # The built-in "Direct" institute holds self-registered learners and must never be
    # archived or deleted (PRD §2). Flagged rather than matched by code at call sites.
    is_system: bool = False

    class Settings:
        name = "institutes"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("code", ASCENDING)], unique=True, name="uq_institutes_code"),
            # "Which colleges belong to this trust?" is asked on every request a group
            # administrator makes, to expand their scope.
            IndexModel([("organisation_id", ASCENDING)], name="ix_institutes_organisation_id"),
        ]


class Branch(TimestampedDocument):
    institute_id: uuid.UUID
    name: str = Field(max_length=120)
    code: str = Field(max_length=40)
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    status: OrgStatus = "active"

    class Settings:
        name = "branches"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("institute_id", ASCENDING), ("code", ASCENDING)],
                unique=True,
                name="uq_branches_institute_code",
            ),
            IndexModel(
                [("institute_id", ASCENDING), ("status", ASCENDING)],
                name="ix_branches_institute_status",
            ),
        ]


class AcademicSession(TimestampedDocument):
    institute_id: uuid.UUID
    name: str = Field(max_length=120)
    start_date: date
    end_date: date
    is_current: bool = False

    @model_validator(mode="after")
    def _dates_in_order(self) -> AcademicSession:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self

    class Settings:
        name = "academic_sessions"
        use_state_management = True
        validate_on_save = True
        # BSON has no date-only type. ISO strings sort and compare correctly as text.
        bson_encoders = {date: lambda d: d.isoformat()}  # noqa: RUF012
        indexes = [  # noqa: RUF012
            IndexModel(
                [("institute_id", ASCENDING), ("name", ASCENDING)],
                unique=True,
                name="uq_academic_sessions_institute_name",
            ),
            IndexModel(
                [("institute_id", ASCENDING), ("is_current", ASCENDING)],
                name="ix_academic_sessions_current",
            ),
        ]


class Class(TimestampedDocument):
    """A class or batch: the level faculty are assigned to and students enrol in."""

    institute_id: uuid.UUID
    branch_id: uuid.UUID
    academic_session_id: uuid.UUID
    name: str = Field(max_length=120)
    section: str | None = Field(default=None, max_length=40)
    code: str = Field(max_length=40)
    status: OrgStatus = "active"

    class Settings:
        name = "classes"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("branch_id", ASCENDING), ("academic_session_id", ASCENDING), ("code", ASCENDING)],
                unique=True,
                name="uq_classes_branch_session_code",
            ),
            IndexModel(
                [("institute_id", ASCENDING), ("status", ASCENDING)],
                name="ix_classes_institute_status",
            ),
            IndexModel(
                [("branch_id", ASCENDING), ("status", ASCENDING)], name="ix_classes_branch_status"
            ),
        ]


class ClassFaculty(TimestampedDocument):
    """Faculty to class. Drives the Faculty membership check in PRD §5.2 step 4."""

    class_id: uuid.UUID
    faculty_user_id: uuid.UUID
    subject: str | None = Field(default=None, max_length=120)
    is_class_teacher: bool = False

    class Settings:
        name = "class_faculty"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("class_id", ASCENDING), ("faculty_user_id", ASCENDING)],
                unique=True,
                name="uq_class_faculty_class_user",
            ),
            # The permission check asks "which classes does this faculty teach?" on every
            # class-scoped request, so the user field gets an index of its own. Not the
            # (faculty_user_id, class_id) pair: Beanie compares index fields unordered,
            # treats that pair as a duplicate of the unique index above, and silently
            # drops the unique one.
            IndexModel([("faculty_user_id", ASCENDING)], name="ix_class_faculty_user"),
        ]


class ClassEnrollment(TimestampedDocument):
    """Student to class. Moving classes keeps history: the old one is marked ``left``."""

    class_id: uuid.UUID
    student_user_id: uuid.UUID
    roll_no: str | None = Field(default=None, max_length=40)
    status: Literal["active", "left"] = "active"

    class Settings:
        name = "class_enrollments"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel(
                [("class_id", ASCENDING), ("student_user_id", ASCENDING)],
                unique=True,
                name="uq_class_enrollments_class_user",
            ),
            IndexModel(
                [("student_user_id", ASCENDING), ("status", ASCENDING)],
                name="ix_class_enrollments_student_status",
            ),
            IndexModel(
                [("class_id", ASCENDING), ("status", ASCENDING)],
                name="ix_class_enrollments_class_status",
            ),
        ]
