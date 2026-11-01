"""The weekly parent digest: one email per parent, covering each linked child's week.

Run by ``python -m app.cli homework-digest`` from a Cloud Run Job that Cloud Scheduler
triggers on Sundays at 18:00 IST. Idempotence is not attempted — the job runs once a week,
and a rerun after a failure sending a second copy is far better than nobody getting one.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import timedelta

from app.core.db import Db, ids_in, utcnow
from app.modules.homework.access import enabled_institutes, learner_visible
from app.modules.homework.models import Homework, HomeworkSubmission
from app.modules.homework.status import student_status
from app.modules.notifications.email import EmailMessage
from app.modules.org.models import ClassEnrollment
from app.modules.users.models import Guardian, User

logger = logging.getLogger(__name__)

WINDOW = timedelta(days=7)


async def build_digests(db: Db) -> list[EmailMessage]:
    """Homework published or due in the last seven days, plus anything due in the next
    seven, for every child with a guardian whose account is active."""
    from app.modules.notifications.templates import homework_digest

    now = utcnow()
    links = await db.raw(Guardian, {}, {"parent_user_id": 1, "student_user_id": 1})
    if not links:
        return []
    people = {
        u["_id"]: u
        for u in await db.raw(
            User,
            {
                "_id": ids_in(
                    {x for link in links for x in link.values() if isinstance(x, uuid.UUID)}
                )
            },
            {"full_name": 1, "email": 1, "status": 1},
        )
    }
    enrolments = await db.raw(
        ClassEnrollment,
        {
            "student_user_id": ids_in({link["student_user_id"] for link in links}),
            "status": "active",
        },
        {"student_user_id": 1, "class_id": 1},
    )
    classes_of: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for e in enrolments:
        classes_of[e["student_user_id"]].add(e["class_id"])

    homework = await db.find(
        Homework,
        {
            "class_id": ids_in({c for cs in classes_of.values() for c in cs}),
            "institute_id": ids_in(await enabled_institutes(db)),
            **learner_visible(now),
            "$or": [
                {"publish_at": {"$gte": now - WINDOW}},
                {"due_at": {"$gte": now - WINDOW, "$lte": now + WINDOW}},
            ],
        },
        sort=[("due_at", 1)],
    )
    submissions = {
        (s.homework_id, s.student_user_id): s
        for s in await db.find(HomeworkSubmission, {"homework_id": ids_in(h.id for h in homework)})
    }

    by_parent: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for link in links:
        by_parent[link["parent_user_id"]].append(link["student_user_id"])

    messages = []
    for parent_id, children in by_parent.items():
        parent = people.get(parent_id)
        if parent is None or parent.get("status") != "active":
            continue
        sections = []
        for child_id in children:
            child = people.get(child_id)
            if child is None:
                continue
            items = []
            for h in homework:
                if h.class_id not in classes_of.get(child_id, set()):
                    continue
                sub = submissions.get((h.id, child_id))
                items.append(
                    {
                        "title": h.title,
                        "subject": h.subject,
                        "due_at": h.due_at,
                        "status": student_status(
                            due_at=h.due_at,
                            submission_status=sub.status if sub else None,
                            now=now,
                        ),
                        "marks": sub.marks if sub else None,
                        "total_marks": h.total_marks,
                    }
                )
            if items:
                sections.append((child["full_name"], items))
        if sections:
            messages.append(homework_digest(parent["email"], parent["full_name"], sections))
    return messages


async def send_digests(db: Db) -> int:
    from app.modules.notifications.email import send_email

    messages = await build_digests(db)
    for message in messages:
        await send_email(message)
    logger.info("homework digest sent", extra={"count": len(messages)})
    return len(messages)
