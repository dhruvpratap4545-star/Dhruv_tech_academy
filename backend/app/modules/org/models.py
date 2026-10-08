"""Organisation hierarchy: Platform → Institute → Branch → Academic Session → Class (PRD §2).

Every institute-scoped table carries ``institute_id`` even where it could be derived through
a join. That is deliberate: tenant isolation becomes one predicate on every query, so a
missing filter shows up as a missing WHERE clause rather than a subtle join mistake.

Nothing here is ever hard-deleted — status moves to ``archived`` (PRD §2 rule 6).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CodeStr, MediumStr, ShortStr, TimestampMixin, Uuid, UuidPkMixin

INSTITUTE_TYPES = ("school", "college", "coaching", "academy")
ORG_STATUSES = ("active", "archived")
ENROLLMENT_STATUSES = ("active", "left")


class Institute(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "institutes"
    __table_args__ = (
        CheckConstraint(
            "type IN ('school', 'college', 'coaching', 'academy')", name="institutes_type"
        ),
        CheckConstraint("status IN ('active', 'archived')", name="institutes_status"),
        UniqueConstraint("code", name="uq_institutes_code"),
    )

    name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    code: Mapped[str] = mapped_column(CodeStr, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    logo_url: Mapped[str | None] = mapped_column(MediumStr)
    contact_email: Mapped[str | None] = mapped_column(ShortStr)
    # The built-in "Direct" institute holds self-registered learners and must never be
    # archived or deleted (PRD §2). Flagged rather than matched by code at call sites.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Branch(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="branches_status"),
        UniqueConstraint("institute_id", "code", name="uq_branches_institute_id_code"),
        Index("ix_branches_institute_id_status", "institute_id", "status"),
    )

    institute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    code: Mapped[str] = mapped_column(CodeStr, nullable=False)
    city: Mapped[str | None] = mapped_column(ShortStr)
    address: Mapped[str | None] = mapped_column(MediumStr)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class AcademicSession(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "academic_sessions"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="academic_sessions_dates"),
        UniqueConstraint("institute_id", "name", name="uq_academic_sessions_institute_id_name"),
        Index("ix_academic_sessions_institute_id_is_current", "institute_id", "is_current"),
    )

    institute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Class(UuidPkMixin, TimestampMixin, Base):
    """A class or batch: the level faculty are assigned to and students enrol in."""

    __tablename__ = "classes"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="classes_status"),
        UniqueConstraint(
            "branch_id", "academic_session_id", "code", name="uq_classes_branch_id_session_code"
        ),
        Index("ix_classes_institute_id_status", "institute_id", "status"),
        Index("ix_classes_branch_id_status", "branch_id", "status"),
    )

    institute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    academic_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("academic_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(ShortStr, nullable=False)
    section: Mapped[str | None] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(CodeStr, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class ClassFaculty(UuidPkMixin, TimestampMixin, Base):
    """Faculty to class. Drives the Faculty membership check in PRD §5.2 step 4."""

    __tablename__ = "class_faculty"
    __table_args__ = (
        UniqueConstraint("class_id", "faculty_user_id", name="uq_class_faculty_class_id_user_id"),
        # The permission check asks "which classes does this faculty teach?" on every
        # class-scoped request, so the user column leads this index.
        Index("ix_class_faculty_faculty_user_id_class_id", "faculty_user_id", "class_id"),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
    )
    faculty_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    subject: Mapped[str | None] = mapped_column(ShortStr)
    is_class_teacher: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ClassEnrollment(UuidPkMixin, TimestampMixin, Base):
    """Student to class. Moving classes keeps history: the old row is marked ``left``."""

    __tablename__ = "class_enrollments"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'left')", name="class_enrollments_status"),
        UniqueConstraint(
            "class_id", "student_user_id", name="uq_class_enrollments_class_id_user_id"
        ),
        Index("ix_class_enrollments_student_user_id_status", "student_user_id", "status"),
        Index("ix_class_enrollments_class_id_status", "class_id", "status"),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
    )
    student_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    roll_no: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
