"""Append-only audit log (PRD §6, §7.6).

Documents are inserted, never updated or deleted. The writer is deliberately tolerant about
the target: an action may concern a user, an institute, a class or nothing at all, so the
target is a (type, id) pair. ``extra`` carries whatever context the event needs.

Nothing sensitive goes in here: no passwords, OTPs, tokens or request bodies.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.core.db import UuidDocument, utcnow


class AuditLog(UuidDocument):
    """No ``updated_at``: an audit entry that can be updated is not an audit entry."""

    created_at: datetime = Field(default_factory=utcnow)
    # Null for anonymous actions: a failed login against an unknown email has no actor.
    actor_user_id: uuid.UUID | None = None
    action: str = Field(max_length=40)
    target_type: str | None = Field(default=None, max_length=40)
    target_id: uuid.UUID | None = None
    # Scopes the entry for `audit:read`. Null means a platform-level event.
    institute_id: uuid.UUID | None = None
    ip: str | None = Field(default=None, max_length=45)
    user_agent: str | None = Field(default=None, max_length=255)
    extra: dict[str, Any] | None = None
    request_id: str | None = Field(default=None, max_length=64)

    class Settings:
        name = "audit_logs"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            # The real read patterns: "what happened in this institute, newest first", "what
            # did this person do", and the sign-in chart's action + time range.
            IndexModel(
                [("institute_id", ASCENDING), ("created_at", DESCENDING), ("_id", DESCENDING)],
                name="ix_audit_logs_institute_created",
            ),
            IndexModel(
                [("actor_user_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_audit_logs_actor_created",
            ),
            IndexModel(
                [("action", ASCENDING), ("created_at", DESCENDING)],
                name="ix_audit_logs_action_created",
            ),
            IndexModel(
                [("target_type", ASCENDING), ("target_id", ASCENDING)], name="ix_audit_logs_target"
            ),
        ]
