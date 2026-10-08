"""Append-only audit log (PRD §6, §7.6).

Rows are written, never updated or deleted. The writer is deliberately tolerant about the
target: an action may concern a user, an institute, a class or nothing at all, so the target
is a (type, id) pair rather than a foreign key per entity. ``metadata`` carries whatever
extra context the event needs, as JSONB.

Nothing sensitive goes in here: no passwords, OTPs, tokens or request bodies.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CodeStr, MediumStr, Uuid, UuidPkMixin


class AuditLog(UuidPkMixin, Base):
    """Deliberately not using ``TimestampMixin``: an audit row that can be updated is not
    an audit row, so there is no ``updated_at`` and ``created_at`` is declared here."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        # The two real read patterns: "what happened in this institute, newest first" and
        # "what did this person do". Both paginate by created_at descending.
        Index("ix_audit_logs_institute_id_created_at", "institute_id", "created_at"),
        Index("ix_audit_logs_actor_user_id_created_at", "actor_user_id", "created_at"),
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Null for anonymous actions: a failed login against an unknown email has no actor.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(CodeStr, nullable=False)
    target_type: Mapped[str | None] = mapped_column(CodeStr)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Scopes the row for `audit:read`. Null means a platform-level event.
    institute_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("institutes.id", ondelete="SET NULL")
    )
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(MediumStr)
    # Named `extra` in Python because `metadata` is reserved by SQLAlchemy's declarative base.
    extra: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))
