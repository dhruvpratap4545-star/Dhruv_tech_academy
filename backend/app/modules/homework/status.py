"""What a homework looks like from a learner's side. Pure functions, no I/O.

Kept apart from the service so the rules a parent will argue about — "it says overdue but
she handed it in" — can be tested exhaustively without a database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

StudentStatus = Literal["pending", "overdue", "submitted", "checked", "redo"]

#: Which board tab each status sits under. "Redo" needs the student to act, so it is
#: listed with the pending work rather than hidden among things already handed in.
TABS: dict[str, tuple[StudentStatus, ...]] = {
    "pending": ("pending", "redo"),
    "submitted": ("submitted",),
    "checked": ("checked",),
    "overdue": ("overdue",),
}


def student_status(
    *, due_at: datetime, submission_status: str | None, now: datetime
) -> StudentStatus:
    if submission_status == "checked":
        return "checked"
    if submission_status == "redo":
        return "redo"
    if submission_status == "submitted":
        return "submitted"
    return "overdue" if now > due_at else "pending"


def visible_to_learners(*, status: str, publish_at: datetime | None, now: datetime) -> bool:
    """Students and parents see published homework whose publish time has arrived.

    A scheduled homework is simply invisible until then — no job flips anything, which is
    why scheduling needs no scheduler.
    """
    return status == "published" and publish_at is not None and publish_at <= now


def is_late(*, due_at: datetime, at: datetime) -> bool:
    return at > due_at


def submission_refusal(
    *,
    due_at: datetime,
    allow_late: bool,
    allow_resubmit: bool,
    existing_status: str | None,
    now: datetime,
) -> str | None:
    """Why this submission may not be made, or ``None`` when it may.

    * A first submission after the due date needs ``allow_late``.
    * A resubmission needs ``allow_resubmit`` and must arrive before the due date — except
      after the teacher asked for a redo, which reopens it whatever the settings say.
    * Checked work is final unless the teacher sends it back.
    """
    if existing_status == "redo":
        return None
    if existing_status == "checked":
        return "This homework has already been checked."
    if existing_status == "submitted":
        if not allow_resubmit:
            return "This homework cannot be submitted again."
        if now > due_at:
            return "The due date has passed, so this can no longer be changed."
        return None
    if now > due_at and not allow_late:
        return "The due date has passed and late submissions are not accepted."
    return None
