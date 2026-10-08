"""Request and response bodies for the organisation endpoints (PRD §8).

Input and output models are separate throughout. Sharing one model between them is how
internal fields leak: a column added for bookkeeping silently appears in an API response.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

InstituteType = Literal["school", "college", "coaching", "academy"]
OrgStatus = Literal["active", "archived"]

_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,39}$")

Name = Annotated[str, Field(min_length=2, max_length=120)]
Code = Annotated[str, Field(min_length=2, max_length=40)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def normalise_code(value: str) -> str:
    """Codes are uppercase and URL-safe. Normalised on the way in so `mca`, `MCA` and `Mca`
    cannot become three different branches."""
    code = value.strip().upper().replace(" ", "-")
    if not _CODE_PATTERN.match(code):
        raise ValueError(
            "Code must be 2-40 characters: letters, numbers, hyphen or underscore, "
            "starting with a letter or number."
        )
    return code


# --------------------------------------------------------------------------- institutes


class InstituteCreate(StrictModel):
    name: Name
    code: Code
    type: InstituteType
    contact_email: EmailStr | None = None
    logo_url: str | None = Field(default=None, max_length=255)

    _code = field_validator("code")(normalise_code)


class InstituteUpdate(StrictModel):
    name: Name | None = None
    type: InstituteType | None = None
    contact_email: EmailStr | None = None
    logo_url: str | None = Field(default=None, max_length=255)


class InstituteOut(OrmModel):
    id: uuid.UUID
    name: str
    code: str
    type: str
    status: str
    contact_email: str | None
    logo_url: str | None
    is_system: bool
    created_at: datetime


class InstituteWithAdminCreate(StrictModel):
    """PRD §12: "Admin screen: create institute + its Institute Admin".

    One call, one transaction. Creating the institute and then failing to invite its admin
    would leave an institute nobody can administer.
    """

    institute: InstituteCreate
    admin_full_name: Name
    admin_email: EmailStr


class InstituteWithAdminOut(BaseModel):
    institute: InstituteOut
    admin_user_id: uuid.UUID
    admin_email: str


# ----------------------------------------------------------------------------- branches


class BranchCreate(StrictModel):
    name: Name
    code: Code
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=255)

    _code = field_validator("code")(normalise_code)


class BranchUpdate(StrictModel):
    name: Name | None = None
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    status: OrgStatus | None = None


class BranchOut(OrmModel):
    id: uuid.UUID
    institute_id: uuid.UUID
    name: str
    code: str
    city: str | None
    address: str | None
    status: str
    created_at: datetime


# --------------------------------------------------------------------- academic sessions


class AcademicSessionCreate(StrictModel):
    name: Name
    start_date: date
    end_date: date
    is_current: bool = False

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, value: date, info) -> date:
        start = info.data.get("start_date")
        if start and value < start:
            raise ValueError("End date cannot be before the start date.")
        return value


class AcademicSessionUpdate(StrictModel):
    name: Name | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None


class AcademicSessionOut(OrmModel):
    id: uuid.UUID
    institute_id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_current: bool
    created_at: datetime


# ------------------------------------------------------------------------------ classes


class ClassCreate(StrictModel):
    name: Name
    code: Code
    academic_session_id: uuid.UUID
    section: str | None = Field(default=None, max_length=40)

    _code = field_validator("code")(normalise_code)


class ClassUpdate(StrictModel):
    name: Name | None = None
    section: str | None = Field(default=None, max_length=40)
    status: OrgStatus | None = None


class ClassOut(OrmModel):
    id: uuid.UUID
    institute_id: uuid.UUID
    branch_id: uuid.UUID
    academic_session_id: uuid.UUID
    name: str
    code: str
    section: str | None
    status: str
    created_at: datetime


# ------------------------------------------------------------- faculty and enrolment


class ClassFacultyCreate(StrictModel):
    user_id: uuid.UUID
    subject: str | None = Field(default=None, max_length=120)
    is_class_teacher: bool = False


class ClassFacultyOut(OrmModel):
    id: uuid.UUID
    class_id: uuid.UUID
    faculty_user_id: uuid.UUID
    subject: str | None
    is_class_teacher: bool
    created_at: datetime


class EnrollmentCreate(StrictModel):
    user_id: uuid.UUID
    roll_no: str | None = Field(default=None, max_length=40)


class EnrollmentOut(OrmModel):
    id: uuid.UUID
    class_id: uuid.UUID
    student_user_id: uuid.UUID
    roll_no: str | None
    status: str
    created_at: datetime
