"""Inviting a whole class from a spreadsheet (PRD §4.2).

A school's learner list already exists, in a file, with the parents' addresses beside the
children's. Typing it into a form five hundred times is not a feature; reading the file is.

Three rules shape this module.

**No row may take another row down with it.** Each learner is written inside a savepoint,
so a duplicate email on line 212 rolls back line 212 and nothing else. Without that, one
bad row at the end discards four hundred good ones and the school has no idea which to
remove before trying again.

**Nothing is written until it has been shown.** The preview runs exactly the same code with
``dry_run`` set, so what the screen promises and what the import does cannot drift apart.

**Every authorization check is the single-invite check.** Nothing here decides who may be
invited — it calls ``service.invite_user`` and ``service.link_guardian`` per row, which is
why a faculty member uploading a file still cannot add a student to a class they do not
teach.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailed
from app.modules.auth.service import RequestMeta
from app.modules.notifications.email import EmailMessage
from app.modules.org.models import Branch, Class
from app.modules.rbac.catalog import STUDENT
from app.modules.rbac.service import Authorized
from app.modules.users import repository as repo
from app.modules.users import schemas, service
from app.modules.users.models import User
from app.modules.users.spreadsheet import SheetRow, read_rows

#: The largest file that will be read at all. A .xlsx holding five hundred learners is a
#: few tens of kilobytes; anything near this is a different kind of file, and refusing it
#: before parsing keeps a zip bomb from being unpacked into memory.
MAX_BYTES = 2 * 1024 * 1024


@dataclass(slots=True)
class _Directory:
    """The institute's branches and classes, by the names a person would type.

    Built once per upload rather than queried per row: five hundred rows would otherwise be
    a thousand round trips to learn the same forty answers.
    """

    branches: dict[str, list[Branch]]
    classes: dict[uuid.UUID, dict[str, list[Class]]]

    def find_branch(self, name: str) -> tuple[Branch | None, str | None]:
        found = self.branches.get(name.casefold(), [])
        if not found:
            return None, f"there is no branch called “{name}” in this institute"
        if len(found) > 1:
            return None, f"two branches are called “{name}” — rename one, or use its code"
        return found[0], None

    def find_class(
        self, branch: Branch, name: str, section: str
    ) -> tuple[Class | None, str | None]:
        found = self.classes.get(branch.id, {}).get(name.casefold(), [])
        if not found:
            return None, f"there is no class called “{name}” in {branch.name}"
        if section:
            exact = [c for c in found if (c.section or "").casefold() == section.casefold()]
            if not exact:
                return None, f"“{name}” in {branch.name} has no section “{section}”"
            return exact[0], None
        if len(found) > 1:
            sections = ", ".join(sorted(c.section or "—" for c in found))
            return None, f"“{name}” has more than one section ({sections}) — name the section"
        return found[0], None


async def _directory(db: AsyncSession, institute_id: uuid.UUID) -> _Directory:
    branches: dict[str, list[Branch]] = {}
    for branch in await db.scalars(
        select(Branch).where(Branch.institute_id == institute_id, Branch.status == "active")
    ):
        # Both the name and the code are accepted, because a school's own file is as
        # likely to say "MCA" as "Master of Computer Applications".
        for key in {branch.name.casefold(), branch.code.casefold()}:
            branches.setdefault(key, []).append(branch)

    classes: dict[uuid.UUID, dict[str, list[Class]]] = {}
    for row in await db.scalars(
        select(Class).where(Class.institute_id == institute_id, Class.status == "active")
    ):
        for key in {row.name.casefold(), row.code.casefold()}:
            classes.setdefault(row.branch_id, {}).setdefault(key, []).append(row)

    return _Directory(branches=branches, classes=classes)


async def _institute_for(guard: Authorized, institute_id: uuid.UUID | None) -> uuid.UUID:
    """Which institute the file is being loaded into.

    Inferred only when there is nothing to infer: somebody who administers exactly one
    institute should not have to say which. Anybody with a choice has to make it, because
    importing five hundred learners into the wrong college is not a mistake with an undo.
    """
    if institute_id is not None:
        return institute_id
    visible = guard.visible_institute_ids()
    if visible is None or len(visible) != 1:
        raise ValidationFailed("Choose which institute these learners belong to.")
    return next(iter(visible))


def _resolve_places(
    row: SheetRow, directory: _Directory
) -> tuple[Branch | None, Class | None, str | None]:
    """Turn the branch and class a row names into rows of the hierarchy.

    Both columns are optional. A file with neither invites learners into the institute at
    large, which is what a coaching centre with one location wants.
    """
    branch: Branch | None = None
    if row.branch:
        branch, problem = directory.find_branch(row.branch)
        if problem:
            return None, None, problem

    if not row.class_name:
        return branch, None, None
    if branch is None:
        return None, None, "name the branch this class is in"

    klass, problem = directory.find_class(branch, row.class_name, row.section)
    if problem:
        return branch, None, problem
    return branch, klass, None


async def _invite_one(
    db: AsyncSession,
    *,
    guard: Authorized,
    row: SheetRow,
    institute_id: uuid.UUID,
    branch: Branch | None,
    klass: Class | None,
    meta: RequestMeta,
) -> tuple[schemas.BulkInviteRow, list[EmailMessage]]:
    """Write one learner and, if the row names one, their parent.

    Both happen inside the caller's savepoint. A learner invited without the parent link
    that was promised is worse than a skipped row: the school believes the parent has
    been told, and nobody has.
    """
    result = schemas.BulkInviteRow(
        row=row.number,
        full_name=row.full_name,
        email=row.email,
        outcome="invited",
        branch=branch.name if branch else None,
        class_name=klass.name if klass else None,
        parent_email=row.parent_email or None,
    )
    messages: list[EmailMessage] = []

    student, message = await service.invite_user(
        db,
        guard=guard,
        payload=schemas.InviteUserRequest(
            full_name=row.full_name,
            email=row.email,
            role_key=STUDENT,
            institute_id=institute_id,
            branch_id=branch.id if branch else None,
            class_ids=[klass.id] if klass else [],
        ),
        meta=meta,
        commit=False,
    )
    if message is not None:
        messages.append(message)

    if not row.has_parent:
        return result, messages

    # A parent who fails is reported on their own line of the result and does not undo the
    # learner: the child is on the platform either way, and the school can add the adult
    # afterwards from the learner's own screen.
    existing = await repo.get_user_by_email(db, row.parent_email)
    try:
        async with db.begin_nested():
            _, parent_message = await service.link_guardian(
                db,
                guard=guard,
                student_id=student.id,
                payload=schemas.GuardianLinkRequest(
                    email=row.parent_email,
                    full_name=row.parent_name or None,
                    relationship=row.relationship or None,
                ),
                meta=meta,
                commit=False,
            )
    except Exception as exc:
        result.parent_outcome = "skipped"
        result.parent_reason = _reason(exc)
    else:
        result.parent_outcome = "linked" if existing is not None else "invited"
        if parent_message is not None:
            messages.append(parent_message)

    return result, messages


def _reason(exc: Exception) -> str:
    """The sentence to show beside a row that was not imported.

    Domain errors already carry a sentence written for the person reading it. Anything
    else is a defect, and saying so is more honest than printing a stack trace's first
    line into a spreadsheet report.
    """
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message:
        return message
    return "could not be added — please report this row"


async def run(
    db: AsyncSession,
    *,
    guard: Authorized,
    data: bytes,
    institute_id: uuid.UUID | None,
    meta: RequestMeta,
    dry_run: bool,
) -> tuple[schemas.BulkInviteResponse, list[EmailMessage]]:
    """Read the file and, unless this is a preview, invite everybody in it."""
    if len(data) > MAX_BYTES:
        raise ValidationFailed(
            "That file is too large. Export just the learner list as .xlsx and try again."
        )

    rows = read_rows(data)
    institute = await _institute_for(guard, institute_id)
    # Proves the caller reaches into this institute at all before a single row is
    # considered, so an upload aimed at somebody else's college fails as one clear refusal
    # rather than as five hundred identical skips. `ensure_within` rather than `ensure`,
    # because a Branch Admin legitimately loads a file into their own branch of it.
    scopes = await guard.ensure_within(institute)
    institute_wide = Authorized.covers_whole_institute(scopes, institute)

    directory = await _directory(db, institute)
    seen_emails = await _already_registered(db, rows)

    results: list[schemas.BulkInviteRow] = []
    messages: list[EmailMessage] = []

    for row in rows:
        branch, klass, problem = _resolve_places(row, directory)
        reasons = [*row.problems]
        if problem:
            reasons.append(problem)
        if row.email in seen_emails:
            reasons.append("somebody with that address is already on the platform")
        if branch is None and not institute_wide:
            # Said here rather than letting the invitation refuse it, because "you do not
            # have permission" on a row is a riddle: the caller has permission, in their
            # own branch, and the row simply never said which branch it meant.
            reasons.append("name the branch — your access covers part of this institute")

        if reasons:
            results.append(
                schemas.BulkInviteRow(
                    row=row.number,
                    full_name=row.full_name,
                    email=row.email,
                    outcome="skipped",
                    reason="; ".join(reasons),
                    branch=branch.name if branch else (row.branch or None),
                    class_name=klass.name if klass else (row.class_name or None),
                    parent_email=row.parent_email or None,
                )
            )
            continue

        if dry_run:
            results.append(
                schemas.BulkInviteRow(
                    row=row.number,
                    full_name=row.full_name,
                    email=row.email,
                    outcome="ready",
                    branch=branch.name if branch else None,
                    class_name=klass.name if klass else None,
                    parent_email=row.parent_email or None,
                    parent_outcome="ready" if row.has_parent else None,
                )
            )
            continue

        try:
            async with db.begin_nested():
                result, sent = await _invite_one(
                    db,
                    guard=guard,
                    row=row,
                    institute_id=institute,
                    branch=branch,
                    klass=klass,
                    meta=meta,
                )
        except Exception as exc:
            results.append(
                schemas.BulkInviteRow(
                    row=row.number,
                    full_name=row.full_name,
                    email=row.email,
                    outcome="skipped",
                    reason=_reason(exc),
                    branch=branch.name if branch else None,
                    class_name=klass.name if klass else None,
                    parent_email=row.parent_email or None,
                )
            )
        else:
            results.append(result)
            messages.extend(sent)

    # A preview writes nothing at all — the loop above never reaches `_invite_one` — so
    # there is nothing to undo and no commit to make.
    if not dry_run:
        await db.commit()

    return (
        schemas.BulkInviteResponse(
            dry_run=dry_run,
            institute_id=institute,
            rows=results,
            invited=sum(1 for r in results if r.outcome == "invited"),
            parents=sum(1 for r in results if r.parent_outcome in ("invited", "linked")),
            skipped=sum(1 for r in results if r.outcome == "skipped"),
        ),
        messages,
    )


async def _already_registered(db: AsyncSession, rows: Sequence[SheetRow]) -> set[str]:
    """Which of the file's learner addresses already have an account.

    Asked once for the whole file. The invitation would refuse each of them anyway, but
    finding out here means the preview can say so before anything is written — which is
    the common case, because a school re-uploading last term's file expects most of it to
    be already there.
    """
    emails = [row.email for row in rows if row.email]
    if not emails:
        return set()
    found = await db.scalars(
        select(func.lower(User.email)).where(func.lower(User.email).in_(emails))
    )
    return set(found)
