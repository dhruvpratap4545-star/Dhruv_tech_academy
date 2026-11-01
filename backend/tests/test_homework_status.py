"""Homework Board pure rules: derived status, learner visibility, late and resubmission."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.homework.status import (
    TABS,
    is_late,
    student_status,
    submission_refusal,
    visible_to_learners,
)

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=1)
EARLIER = NOW - timedelta(days=1)


@pytest.mark.parametrize(
    ("due", "submitted", "expected"),
    [
        (LATER, None, "pending"),
        (EARLIER, None, "overdue"),
        (EARLIER, "submitted", "submitted"),
        (LATER, "checked", "checked"),
        (EARLIER, "redo", "redo"),
    ],
)
def test_student_status_is_derived(due, submitted, expected) -> None:
    assert student_status(due_at=due, submission_status=submitted, now=NOW) == expected


def test_redo_is_listed_with_pending_work() -> None:
    assert "redo" in TABS["pending"]
    assert all(len(set(TABS[a]) & set(TABS[b])) == 0 for a in TABS for b in TABS if a != b)


def test_only_published_homework_whose_time_has_come_is_visible() -> None:
    assert visible_to_learners(status="published", publish_at=EARLIER, now=NOW)
    assert not visible_to_learners(status="published", publish_at=LATER, now=NOW)
    assert not visible_to_learners(status="draft", publish_at=EARLIER, now=NOW)
    assert not visible_to_learners(status="archived", publish_at=EARLIER, now=NOW)
    assert not visible_to_learners(status="published", publish_at=None, now=NOW)


def test_late_means_after_the_due_time() -> None:
    assert is_late(due_at=EARLIER, at=NOW)
    assert not is_late(due_at=LATER, at=NOW)


def _refusal(*, due=LATER, allow_late=True, allow_resubmit=True, existing=None):
    return submission_refusal(
        due_at=due,
        allow_late=allow_late,
        allow_resubmit=allow_resubmit,
        existing_status=existing,
        now=NOW,
    )


def test_first_submission_rules() -> None:
    assert _refusal() is None
    assert _refusal(due=EARLIER) is None  # late, but allowed
    assert "late submissions are not accepted" in _refusal(due=EARLIER, allow_late=False)


def test_resubmission_rules() -> None:
    assert _refusal(existing="submitted") is None
    assert "cannot be submitted again" in _refusal(existing="submitted", allow_resubmit=False)
    assert "due date has passed" in _refusal(existing="submitted", due=EARLIER)
    assert "already been checked" in _refusal(existing="checked")


def test_a_redo_reopens_whatever_the_settings() -> None:
    assert _refusal(existing="redo", due=EARLIER, allow_late=False, allow_resubmit=False) is None
