"""Who may see what in the Content Library.

Three kinds of reader, decided once per request:

* **Platform staff** (``library:read`` at platform scope) see everything, in every state.
* **Institute reviewers** (holding ``library:manage`` or ``library:publish``) see the
  published master library plus everything in their own institutes' libraries, drafts
  included — a reviewer has to see what they are reviewing.
* **Other institute staff** (faculty, custom roles) see published material plus whatever
  they created themselves, in any state — never a colleague's draft.
* **Students and parents** see published material only, and only inside the parts of the
  syllabus linked to their classes (a parent: their children's classes). This is the same
  membership narrowing the users module applies to ``user:read``: the permission is held
  institute-wide, and the link is what confines it.

Module gating: an institute only counts if the ``library`` module is switched on for it.
A reader left with no such institute is refused with 403, exactly as the engine refuses a
disabled module everywhere else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.core.db import Db, ids_in
from app.core.errors import Forbidden
from app.modules.library.models import ClassSyllabus, SyllabusNode
from app.modules.rbac import repository as rbac_repo
from app.modules.rbac.catalog import LIBRARY_MODULE, PARENT, STUDENT
from app.modules.rbac.scopes import PLATFORM
from app.modules.rbac.service import Authorized

NARROWED_ROLES = frozenset({STUDENT, PARENT})


@dataclass(frozen=True, slots=True)
class Reader:
    user_id: uuid.UUID
    platform: bool
    #: Institutes the reader reaches with the module switched on.
    institute_ids: frozenset[uuid.UUID]
    narrowed: bool
    #: Institutes where the reader holds ``library:manage`` or ``library:publish`` and so
    #: sees drafts. Per institute: an admin at one school who only teaches at another must
    #: not see the second school's drafts.
    review_institute_ids: frozenset[uuid.UUID] = frozenset()
    #: For narrowed readers: every node inside their linked subtrees, and the nodes above
    #: them (so the tree can be browsed down to the linked level).
    subtree_ids: frozenset[uuid.UUID] = frozenset()
    path_ids: frozenset[uuid.UUID] = frozenset()

    def library_filter(self) -> dict[str, Any]:
        """Which libraries: master plus the reader's own institutes."""
        if self.platform:
            return {}
        return {"institute_id": {"$in": [None, *self.institute_ids]}}


async def enabled_institutes(db: Db, institute_ids: frozenset[uuid.UUID]) -> frozenset[uuid.UUID]:
    from app.modules.rbac.models import InstituteModule

    if not institute_ids:
        return frozenset()
    enabled = await db.distinct(
        InstituteModule,
        "institute_id",
        {"institute_id": ids_in(institute_ids), **rbac_repo.live_module_match(LIBRARY_MODULE)},
    )
    return frozenset(enabled)


async def linked_class_ids(db: Db, user_id: uuid.UUID, role_keys: set[str]) -> frozenset[uuid.UUID]:
    """A student's own classes, and for a parent their children's classes."""
    from app.modules.users.models import Guardian

    classes: set[uuid.UUID] = set()
    if STUDENT in role_keys:
        classes |= await rbac_repo.student_class_ids(db, user_id)
    if PARENT in role_keys:
        children = await db.distinct(Guardian, "student_user_id", {"parent_user_id": user_id})
        for child in children:
            classes |= await rbac_repo.student_class_ids(db, child)
    return frozenset(classes)


async def subtree_of(db: Db, root_ids: frozenset[uuid.UUID]) -> frozenset[uuid.UUID]:
    if not root_ids:
        return frozenset()
    rows = await db.raw(
        SyllabusNode,
        {"$or": [{"_id": ids_in(root_ids)}, {"ancestors": {"$in": list(root_ids)}}]},
        {"_id": 1},
    )
    return frozenset(r["_id"] for r in rows)


async def resolve_reader(db: Db, guard: Authorized) -> Reader:
    """Build the reader for a request holding ``library:read`` (or another library key)."""
    scopes = guard.usable_scopes()
    if any(s.level == PLATFORM for s in scopes):
        return Reader(
            user_id=guard.user_id, platform=True, institute_ids=frozenset(), narrowed=False
        )

    visible = guard.visible_institute_ids() or frozenset()
    institutes = await enabled_institutes(db, visible)
    if not institutes:
        raise Forbidden("The content library is not switched on for your institute.")

    role_keys = {a.role_key for a in guard.context.assignments}
    if not (role_keys and role_keys <= NARROWED_ROLES):
        return Reader(
            user_id=guard.user_id,
            platform=False,
            institute_ids=institutes,
            narrowed=False,
            review_institute_ids=institutes
            & frozenset().union(
                *(
                    Authorized(guard._db, guard.context, key).visible_institute_ids() or ()
                    for key in ("library:manage", "library:publish")
                )
            ),
        )

    classes = await linked_class_ids(db, guard.user_id, role_keys)
    roots = (
        frozenset(await db.distinct(ClassSyllabus, "node_id", {"class_id": ids_in(classes)}))
        if classes
        else frozenset()
    )
    subtree = await subtree_of(db, roots)
    above: set[uuid.UUID] = set()
    for row in await db.raw(SyllabusNode, {"_id": ids_in(roots)}, {"ancestors": 1}):
        above.update(row.get("ancestors", []))
    return Reader(
        user_id=guard.user_id,
        platform=False,
        institute_ids=institutes,
        narrowed=True,
        subtree_ids=subtree,
        path_ids=frozenset(above),
    )


def node_filter(reader: Reader, *, include_archived: bool = False) -> dict[str, Any]:
    match: dict[str, Any] = dict(reader.library_filter())
    if not include_archived or reader.narrowed:
        match["status"] = "active"
    if reader.narrowed:
        match["_id"] = ids_in(reader.subtree_ids | reader.path_ids)
    return match


def item_filter(reader: Reader) -> dict[str, Any]:
    """Archived items are excluded unless the caller filters for them explicitly."""
    if reader.platform:
        return {}
    if reader.narrowed:
        return {
            **reader.library_filter(),
            "status": "published",
            "node_ids": {"$in": list(reader.subtree_ids)},
        }
    return {
        **reader.library_filter(),
        "$or": [
            {"status": "published"},
            {"created_by": reader.user_id},
            {"institute_id": {"$in": list(reader.review_institute_ids)}},
        ],
    }
