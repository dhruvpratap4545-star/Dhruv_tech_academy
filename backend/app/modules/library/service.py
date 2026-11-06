"""Content Library use cases (Phase 3, Module B).

Write rules, enforced here and nowhere else:

* **Master library** rows (``institute_id`` null) are written only with a platform-scope
  grant — ``library:manage`` for the tree, ``library:contribute`` / ``library:publish`` for
  material, which by default only platform staff hold at that scope.
* **Institute library** rows are written with the permission held anywhere inside that
  institute (``ensure_within``). A Branch Admin holds ``library:manage`` at their branch,
  and the syllabus belongs to the institute as a whole, so asking for institute-level
  authority would lock every branch head out of a job the role matrix gives them.
* Faculty **contribute**: they create drafts and submit them for review, and edit only their
  own drafts. ``library:publish`` moves ``in_review`` → ``published``; nothing else does.
* Every edit to a published item snapshots the previous state into ``content_item_versions``.

Reads go through ``access.resolve_reader``; anything a reader may not see is a 404.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import UploadFile

from app.core.db import Db, ids_in, ilike, utcnow
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import paginate
from app.modules.audit import events
from app.modules.audit import service as audit
from app.modules.auth.service import RequestMeta
from app.modules.files import service as files
from app.modules.files.models import StoredFile
from app.modules.library import access, schemas, spreadsheet
from app.modules.library.access import Reader, item_filter, node_filter, resolve_reader
from app.modules.library.models import (
    ClassSyllabus,
    ContentItem,
    ContentItemVersion,
    SyllabusNode,
)
from app.modules.library.rules import (
    check_https_link,
    check_kind,
    child_path,
    normalise_code,
    parse_video_url,
    slugify,
)
from app.modules.library.tree import TreeWriter
from app.modules.org.models import Class
from app.modules.rbac.context import AuthContext
from app.modules.rbac.scopes import Scope
from app.modules.rbac.service import Authorized

#: A master-library upload belongs to no institute; it is filed under the platform.
MASTER_FILE_INSTITUTE = files.PLATFORM_OWNER

#: Fields copied into a version snapshot — what a reader sees, not the bookkeeping.
VERSIONED_FIELDS = (
    "title",
    "kind",
    "file_id",
    "url",
    "video_provider",
    "video_id",
    "body",
    "node_ids",
    "medium",
    "author",
    "source",
)


def _audit(
    db: Db,
    actor: uuid.UUID,
    meta: RequestMeta,
    action: str,
    *,
    target_type: str,
    target_id: uuid.UUID | None,
    institute_id: uuid.UUID | None,
    extra: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action=action,
        actor_user_id=actor,
        target_type=target_type,
        target_id=target_id,
        institute_id=institute_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
        extra=extra,
    )


async def authorize(guard: Authorized, institute_id: uuid.UUID | None) -> None:
    """The guard's permission, for the master library or within one institute."""
    if institute_id is None:
        await guard.ensure(Scope())
    else:
        await guard.ensure_within(institute_id)


def with_permission(db: Db, guard: Authorized, permission: str) -> Authorized:
    """A guard for a second permission the same request needs, refused if not held."""
    if not guard.context.holds(permission):
        raise Forbidden()
    return Authorized(db, guard.context, permission)


# -------------------------------------------------------------------------------- nodes


async def _child_counts(db: Db, reader: Reader, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = await db.aggregate(
        SyllabusNode,
        [
            {"$match": {**node_filter(reader), "parent_id": {"$in": ids}}},
            {"$group": {"_id": "$parent_id", "n": {"$sum": 1}}},
        ],
    )
    return {r["_id"]: r["n"] for r in rows}


async def node_outs(db: Db, reader: Reader, nodes: Sequence[SyllabusNode]) -> list[schemas.NodeOut]:
    counts = await _child_counts(db, reader, [n.id for n in nodes])
    return [
        schemas.NodeOut.model_validate(n).model_copy(update={"child_count": counts.get(n.id, 0)})
        for n in nodes
    ]


async def list_nodes(
    db: Db, *, guard: Authorized, parent_id: uuid.UUID | None, include_archived: bool = False
) -> list[schemas.NodeOut]:
    reader = await resolve_reader(db, guard)
    match = {**node_filter(reader, include_archived=include_archived), "parent_id": parent_id}
    nodes = await db.find(SyllabusNode, match, sort=[("order", 1), ("name", 1)])
    return await node_outs(db, reader, nodes)


async def _require_node(db: Db, reader: Reader, node_id: uuid.UUID) -> SyllabusNode:
    # `$and`, never a dict merge: a narrowed reader's filter already constrains `_id`, and
    # merging would replace that constraint with the requested id — any node by id.
    node = await db.find_one(
        SyllabusNode, {"$and": [node_filter(reader, include_archived=True), {"_id": node_id}]}
    )
    if node is None:
        raise NotFound("That part of the syllabus does not exist.")
    return node


async def get_node(db: Db, *, guard: Authorized, node_id: uuid.UUID) -> schemas.NodeDetail:
    reader = await resolve_reader(db, guard)
    node = await _require_node(db, reader, node_id)
    above = {n.id: n for n in await db.find(SyllabusNode, {"_id": ids_in(node.ancestors)})}
    children = await db.find(
        SyllabusNode, {**node_filter(reader), "parent_id": node.id}, sort=[("order", 1)]
    )
    return schemas.NodeDetail(
        node=(await node_outs(db, reader, [node]))[0],
        breadcrumb=[
            schemas.Crumb(id=a.id, name=a.name, kind=a.kind)
            for a in (above.get(i) for i in node.ancestors)
            if a is not None
        ],
        children=await node_outs(db, reader, children),
    )


async def create_node(
    db: Db, *, guard: Authorized, payload: schemas.NodeCreate, meta: RequestMeta
) -> SyllabusNode:
    parent: SyllabusNode | None = None
    if payload.parent_id is not None:
        parent = await db.get(SyllabusNode, payload.parent_id)
        if parent is None or parent.status != "active":
            raise NotFound("That parent node does not exist.")
        # A node lives in its parent's library, except that an institute may hang its own
        # topics under the master syllabus.
        if parent.institute_id is not None:
            if payload.institute_id not in (None, parent.institute_id):
                raise ValidationFailed("A node must be in the same library as its parent.")
            institute_id = parent.institute_id
        else:
            institute_id = payload.institute_id
        track = parent.track
    else:
        institute_id = payload.institute_id
        if payload.track is None:
            raise ValidationFailed("A top-level node needs a track.")
        track = payload.track

    await authorize(guard, institute_id)
    check_kind(parent.kind if parent else None, payload.kind)
    code = normalise_code(payload.code or payload.name)
    path = child_path(parent.code_path if parent else None, code)
    if await db.exists(SyllabusNode, {"code_path": path, "institute_id": institute_id}):
        raise Conflict("That code is already used at this level. Choose another.")

    last = await db.find_one(
        SyllabusNode, {"parent_id": parent.id if parent else None}, sort=[("order", -1)]
    )
    node = SyllabusNode(
        institute_id=institute_id,
        track=track,
        parent_id=parent.id if parent else None,
        ancestors=[*parent.ancestors, parent.id] if parent else [],
        kind=payload.kind,
        name=payload.name,
        code=code,
        code_path=path,
        order=(last.order + 1) if last else 0,
        mediums=list(payload.mediums),
        difficulty=payload.difficulty,
        exam_tags=sorted({slugify(t, max_length=20) for t in payload.exam_tags} - {""}),
    )
    db.add(node)
    _audit(
        db,
        guard.user_id,
        meta,
        events.LIBRARY_NODE_CREATED,
        target_type="syllabus_node",
        target_id=node.id,
        institute_id=institute_id,
        extra={"path": path, "kind": node.kind},
    )
    return node


async def _node_for_write(db: Db, guard: Authorized, node_id: uuid.UUID) -> SyllabusNode:
    reader = await resolve_reader(db, guard)
    node = await _require_node(db, reader, node_id)
    await authorize(guard, node.institute_id)
    return node


async def update_node(
    db: Db, *, guard: Authorized, node_id: uuid.UUID, payload: schemas.NodeUpdate, meta: RequestMeta
) -> SyllabusNode:
    node = await _node_for_write(db, guard, node_id)
    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "exam_tags" in changed:
        changed["exam_tags"] = sorted(
            {slugify(t, max_length=20) for t in changed["exam_tags"]} - {""}
        )
    for field, value in changed.items():
        setattr(node, field, value)
    _audit(
        db,
        guard.user_id,
        meta,
        events.LIBRARY_NODE_UPDATED,
        target_type="syllabus_node",
        target_id=node.id,
        institute_id=node.institute_id,
        extra={"fields": sorted(changed)},
    )
    return node


async def archive_node(
    db: Db, *, guard: Authorized, node_id: uuid.UUID, meta: RequestMeta
) -> SyllabusNode:
    """Archive a node and everything under it — refused while any of it has live material.

    Refusing is the point: archiving a chapter that still has published notes would leave
    those notes linked to a chapter nobody can browse to, visible to no one and impossible
    to find to fix.
    """
    node = await _node_for_write(db, guard, node_id)
    subtree = await access.subtree_of(db, frozenset({node.id}))
    if await db.exists(
        ContentItem, {"node_ids": {"$in": list(subtree)}, "status": {"$ne": "archived"}}
    ):
        raise Conflict(
            "This part of the syllabus still has study material. "
            "Move or archive the material first."
        )
    node.status = "archived"
    db.update_many(SyllabusNode, {"_id": ids_in(subtree - {node.id})}, {"status": "archived"})
    _audit(
        db,
        guard.user_id,
        meta,
        events.LIBRARY_NODE_ARCHIVED,
        target_type="syllabus_node",
        target_id=node.id,
        institute_id=node.institute_id,
        extra={"path": node.code_path, "nodes": len(subtree)},
    )
    return node


async def reorder_node(
    db: Db, *, guard: Authorized, node_id: uuid.UUID, position: int, meta: RequestMeta
) -> list[SyllabusNode]:
    node = await _node_for_write(db, guard, node_id)
    siblings = await db.find(
        SyllabusNode,
        {"parent_id": node.parent_id, "institute_id": node.institute_id, "status": "active"},
        sort=[("order", 1), ("name", 1)],
    )
    ordered = [s for s in siblings if s.id != node.id]
    ordered.insert(min(position, len(ordered)), node)
    for index, sibling in enumerate(ordered):
        if sibling.order != index:
            sibling.order = index
    _audit(
        db,
        guard.user_id,
        meta,
        events.LIBRARY_NODE_UPDATED,
        target_type="syllabus_node",
        target_id=node.id,
        institute_id=node.institute_id,
        extra={"fields": ["order"], "position": position},
    )
    return ordered


# ------------------------------------------------------------------------------- import


async def import_syllabus(
    db: Db,
    *,
    guard: Authorized,
    data: bytes,
    institute_id: uuid.UUID | None,
    dry_run: bool,
    meta: RequestMeta,
) -> schemas.ImportResult:
    """Preview or apply a spreadsheet. Valid rows are applied even when others are not."""
    await authorize(guard, institute_id)
    rows = spreadsheet.read_rows(data)
    writer = TreeWriter(db, institute_id, rename=False)
    problems: list[schemas.ImportProblem] = []
    valid = 0
    for row in rows:
        if row.problems:
            problems.append(schemas.ImportProblem(row=row.number, messages=row.problems))
            continue
        await writer.load(row.track)
        # No savepoint: every node a row creates is valid on its own, so a row that fails
        # half-way keeps the levels above the failure, which a later row would need anyway.
        try:
            parent = writer.ensure(
                None,
                track=row.track,
                kind="track",
                name=spreadsheet.track_name(row.track),
                code=row.track,
            )
            last = len(row.path) - 1
            for index, (kind, name) in enumerate(row.path):
                leaf = index == last
                parent = writer.ensure(
                    parent,
                    track=row.track,
                    kind=kind,
                    name=name,
                    mediums=row.mediums if leaf else None,
                    difficulty=row.difficulty if leaf else None,
                    exam_tags=row.exam_tags if leaf and row.exam_tags else None,
                )
        except ValidationFailed as exc:
            problems.append(schemas.ImportProblem(row=row.number, messages=[exc.message]))
            continue
        valid += 1

    counts = writer.counts
    if dry_run:
        await db.rollback()
    else:
        _audit(
            db,
            guard.user_id,
            meta,
            events.LIBRARY_IMPORTED,
            target_type="syllabus_import",
            target_id=None,
            institute_id=institute_id,
            extra={"rows": len(rows), "created": counts.created, "updated": counts.updated},
        )
    return schemas.ImportResult(
        dry_run=dry_run,
        rows_total=len(rows),
        rows_valid=valid,
        problems=problems,
        created=counts.created,
        updated=counts.updated,
        unchanged=counts.unchanged,
        by_kind=counts.by_kind,
    )


# -------------------------------------------------------------------------------- items


async def _check_nodes(
    db: Db, node_ids: Sequence[uuid.UUID], institute_id: uuid.UUID | None
) -> list[uuid.UUID]:
    """Material links only to live nodes of the master library or its own institute's."""
    wanted = list(dict.fromkeys(node_ids))
    libraries = [None] if institute_id is None else [None, institute_id]
    found = await db.count(
        SyllabusNode,
        {"_id": ids_in(wanted), "status": "active", "institute_id": {"$in": libraries}},
    )
    if found != len(wanted):
        raise ValidationFailed(
            "Link the material to topics or chapters that exist in this library."
        )
    return wanted


def _link_fields(kind: str, url: str | None, body: str | None) -> dict[str, Any]:
    if kind == "video_link":
        if not url:
            raise ValidationFailed("A video needs its YouTube or Vimeo link.")
        video = parse_video_url(url)
        return {
            "url": video.url,
            "video_provider": video.provider,
            "video_id": video.video_id,
            "body": None,
        }
    if kind == "link":
        if not url:
            raise ValidationFailed("A link needs its https:// address.")
        return {
            "url": check_https_link(url),
            "video_provider": None,
            "video_id": None,
            "body": None,
        }
    if kind == "text":
        if not body or not body.strip():
            raise ValidationFailed("A text note cannot be empty.")
        return {"body": body, "url": None, "video_provider": None, "video_id": None}
    return {}


async def create_item(
    db: Db, *, guard: Authorized, payload: schemas.ItemCreate, meta: RequestMeta
) -> ContentItem:
    await authorize(guard, payload.institute_id)
    node_ids = await _check_nodes(db, payload.node_ids, payload.institute_id)
    item = ContentItem(
        institute_id=payload.institute_id,
        title=payload.title,
        kind=payload.kind,
        node_ids=node_ids,
        medium=payload.medium,
        author=payload.author,
        source=payload.source,
        created_by=guard.user_id,
        **_link_fields(payload.kind, payload.url, payload.body),
    )
    db.add(item)
    _audit_item(db, guard.user_id, meta, events.LIBRARY_ITEM_CREATED, item)
    return item


async def upload_item(
    db: Db,
    *,
    guard: Authorized,
    upload: UploadFile,
    institute_id: uuid.UUID | None,
    title: str,
    node_ids: list[uuid.UUID],
    medium: str,
    author: str | None,
    source: str | None,
    meta: RequestMeta,
) -> ContentItem:
    """A PDF or image as study material. Validated, cleaned and stored privately."""
    await authorize(guard, institute_id)
    if not 2 <= len(title.strip()) <= 200:
        raise ValidationFailed("The title must be 2 to 200 characters.")
    if medium not in ("hi", "en", "both"):
        raise ValidationFailed("Medium must be hi, en or both.")
    if not node_ids:
        raise ValidationFailed("Link the material to at least one topic or chapter.")
    linked = await _check_nodes(db, node_ids, institute_id)
    stored = await files.store_upload(
        db,
        upload=upload,
        institute_id=institute_id or MASTER_FILE_INSTITUTE,
        purpose="library",
        user_id=guard.user_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    stored.status = "attached"
    item = ContentItem(
        institute_id=institute_id,
        title=title.strip(),
        kind="pdf" if stored.content_type == "application/pdf" else "image",
        file_id=stored.id,
        node_ids=linked,
        medium=medium,  # type: ignore[arg-type]
        author=(author or "").strip()[:120] or None,
        source=(source or "").strip()[:200] or None,
        created_by=guard.user_id,
    )
    db.add(item)
    _audit_item(db, guard.user_id, meta, events.LIBRARY_ITEM_CREATED, item)
    return item


def _audit_item(
    db: Db,
    actor: uuid.UUID,
    meta: RequestMeta,
    action: str,
    item: ContentItem,
    extra: dict[str, Any] | None = None,
) -> None:
    _audit(
        db,
        actor,
        meta,
        action,
        target_type="content_item",
        target_id=item.id,
        institute_id=item.institute_id,
        extra={"kind": item.kind, "status": item.status, **(extra or {})},
    )


async def _require_item(db: Db, reader: Reader, item_id: uuid.UUID) -> ContentItem:
    item = await db.find_one(ContentItem, {"$and": [item_filter(reader), {"_id": item_id}]})
    if item is None:
        raise NotFound("That material does not exist.")
    return item


async def item_outs(db: Db, items: Sequence[ContentItem]) -> list[schemas.ItemOut]:
    stored = await files.files_by_id(db, [i.file_id for i in items if i.file_id])
    out = []
    for item in items:
        row = schemas.ItemOut.model_validate(item)
        if item.file_id and item.file_id in stored:
            row.file = schemas.FileInfo.model_validate(stored[item.file_id])
        out.append(row)
    return out


async def list_items(
    db: Db,
    *,
    guard: Authorized,
    node_id: uuid.UUID | None,
    status: str | None,
    mine: bool,
    cursor: str | None,
    limit: int,
) -> tuple[Sequence[ContentItem], str | None, int]:
    """Material on a node *and everything under it*: a chapter shows its topics' notes."""
    reader = await resolve_reader(db, guard)
    clauses: list[dict[str, Any]] = [item_filter(reader)]
    if node_id is not None:
        node = await _require_node(db, reader, node_id)
        under = await access.subtree_of(db, frozenset({node.id}))
        clauses.append({"node_ids": {"$in": list(under)}})
    if status:
        clauses.append({"status": status})
    else:
        clauses.append({"status": {"$ne": "archived"}})
    if mine:
        clauses.append({"created_by": guard.user_id})
    match = {"$and": [c for c in clauses if c]}
    return await paginate(db, ContentItem, match, cursor=cursor, limit=limit)


async def get_item(db: Db, *, guard: Authorized, item_id: uuid.UUID) -> ContentItem:
    reader = await resolve_reader(db, guard)
    return await _require_item(db, reader, item_id)


def _snapshot(db: Db, item: ContentItem, editor: uuid.UUID) -> None:
    db.add(
        ContentItemVersion(
            item_id=item.id,
            version=item.version,
            fields=item.model_dump(include=set(VERSIONED_FIELDS), mode="json"),
            edited_by=editor,
        )
    )
    item.version += 1


async def update_item(
    db: Db, *, guard: Authorized, item_id: uuid.UUID, payload: schemas.ItemUpdate, meta: RequestMeta
) -> ContentItem:
    """Contributors edit their own drafts; managers edit anything in their library."""
    reader = await resolve_reader(db, guard)
    item = await _require_item(db, reader, item_id)
    own_draft = item.created_by == guard.user_id and item.status == "draft"
    if own_draft:
        await authorize(guard, item.institute_id)
    else:
        await authorize(with_permission(db, guard, "library:manage"), item.institute_id)
    if item.status == "archived":
        raise Conflict("Archived material cannot be edited.")

    changed = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "node_ids" in changed:
        changed["node_ids"] = await _check_nodes(db, changed["node_ids"], item.institute_id)
    if "url" in changed or "body" in changed:
        if item.kind in ("pdf", "image"):
            raise ValidationFailed("A file's link or text cannot be changed; upload a new item.")
        changed.update(
            _link_fields(item.kind, changed.get("url", item.url), changed.get("body", item.body))
        )
    if not changed:
        return item
    if item.status == "published":
        _snapshot(db, item, guard.user_id)
    for field, value in changed.items():
        setattr(item, field, value)
    _audit_item(
        db, guard.user_id, meta, events.LIBRARY_ITEM_UPDATED, item, {"fields": sorted(changed)}
    )
    return item


async def _transition(
    db: Db,
    *,
    guard: Authorized,
    item_id: uuid.UUID,
    allowed_from: tuple[str, ...],
    to: str,
    action: str,
    meta: RequestMeta,
    note: str | None = None,
    creator_may: bool = False,
) -> ContentItem:
    reader = await resolve_reader(db, guard)
    item = await _require_item(db, reader, item_id)
    if creator_may and item.created_by == guard.user_id:
        await authorize(guard, item.institute_id)
    elif creator_may:
        await authorize(with_permission(db, guard, "library:manage"), item.institute_id)
    else:
        await authorize(guard, item.institute_id)
    if item.status not in allowed_from:
        raise Conflict(
            f"This material is {item.status.replace('_', ' ')} "
            f"and cannot be {to.replace('_', ' ')} now."
        )

    item.status = to  # type: ignore[assignment]
    if to == "published":
        item.reviewed_by = guard.user_id
        item.published_at = utcnow()
        item.review_note = note
    elif action == events.LIBRARY_ITEM_REJECTED:
        item.reviewed_by = guard.user_id
        item.review_note = note
    _audit_item(db, guard.user_id, meta, action, item)
    return item


async def submit_item(
    db: Db, *, guard: Authorized, item_id: uuid.UUID, meta: RequestMeta
) -> ContentItem:
    return await _transition(
        db,
        guard=guard,
        item_id=item_id,
        allowed_from=("draft",),
        to="in_review",
        action=events.LIBRARY_ITEM_SUBMITTED,
        meta=meta,
        creator_may=True,
    )


async def publish_item(
    db: Db, *, guard: Authorized, item_id: uuid.UUID, note: str | None, meta: RequestMeta
) -> ContentItem:
    return await _transition(
        db,
        guard=guard,
        item_id=item_id,
        allowed_from=("in_review",),
        to="published",
        action=events.LIBRARY_ITEM_PUBLISHED,
        meta=meta,
        note=note,
    )


async def reject_item(
    db: Db, *, guard: Authorized, item_id: uuid.UUID, note: str | None, meta: RequestMeta
) -> ContentItem:
    """Back to draft with the reviewer's note, so the author can fix and resubmit."""
    return await _transition(
        db,
        guard=guard,
        item_id=item_id,
        allowed_from=("in_review",),
        to="draft",
        action=events.LIBRARY_ITEM_REJECTED,
        meta=meta,
        note=note,
    )


async def archive_item(
    db: Db, *, guard: Authorized, item_id: uuid.UUID, meta: RequestMeta
) -> ContentItem:
    return await _transition(
        db,
        guard=guard,
        item_id=item_id,
        allowed_from=("draft", "in_review", "published"),
        to="archived",
        action=events.LIBRARY_ITEM_ARCHIVED,
        meta=meta,
    )


async def list_versions(
    db: Db, *, guard: Authorized, item_id: uuid.UUID
) -> Sequence[ContentItemVersion]:
    reader = await resolve_reader(db, guard)
    if reader.narrowed:
        raise Forbidden()
    item = await _require_item(db, reader, item_id)
    return await db.find(ContentItemVersion, {"item_id": item.id}, sort=[("version", -1)])


# ----------------------------------------------------------------------- file downloads


async def can_read_file(db: Db, context: AuthContext, stored: StoredFile) -> bool:
    """May this person download a library file? Exactly when they may see an item using it."""
    if not context.holds("library:read"):
        return False
    try:
        reader = await resolve_reader(db, Authorized(db, context, "library:read"))
    except Forbidden:
        return False
    return await db.exists(ContentItem, {"$and": [item_filter(reader), {"file_id": stored.id}]})


files.register_access("library", can_read_file)


# ------------------------------------------------------------------------------- search


async def _paths(db: Db, nodes: Sequence[SyllabusNode]) -> dict[uuid.UUID, str]:
    """ "CBSE › Class 10 › Science › Electricity" for each node, in one query."""
    ancestor_ids = {a for n in nodes for a in n.ancestors}
    names = {
        r["_id"]: r["name"]
        for r in await db.raw(SyllabusNode, {"_id": ids_in(ancestor_ids)}, {"name": 1})
    }
    return {n.id: " › ".join([*(names.get(a, "…") for a in n.ancestors), n.name]) for n in nodes}


async def _class_roots(db: Db, reader: Reader, class_id: uuid.UUID) -> frozenset[uuid.UUID]:
    found = await db.raw(Class, {"_id": class_id}, {"institute_id": 1})
    if not found or (not reader.platform and found[0]["institute_id"] not in reader.institute_ids):
        return frozenset()
    return frozenset(await db.distinct(ClassSyllabus, "node_id", {"class_id": class_id}))


async def search(
    db: Db,
    *,
    guard: Authorized,
    q: str,
    track: str | None,
    class_id: uuid.UUID | None,
    kind: str | None,
    medium: str | None,
) -> schemas.SearchResults:
    reader = await resolve_reader(db, guard)
    node_match: dict[str, Any] = {**node_filter(reader), "name": ilike(q)}
    item_clauses: list[dict[str, Any]] = [
        item_filter(reader),
        {"title": ilike(q)},
        {"status": {"$ne": "archived"}},
    ]
    if track:
        node_match["track"] = track
    if medium:
        node_match["mediums"] = {"$all": ["hi", "en"]} if medium == "both" else medium
        item_clauses.append({"medium": {"$in": [medium, "both"]}})
    if kind in ("track", "level", "subject", "unit", "chapter", "topic"):
        node_match["kind"] = kind
    elif kind:
        item_clauses.append({"kind": kind})
    if class_id is not None:
        within = await access.subtree_of(db, await _class_roots(db, reader, class_id))
        node_match["_id"] = (
            ids_in(within & (reader.subtree_ids | reader.path_ids))
            if reader.narrowed
            else ids_in(within)
        )
        item_clauses.append({"node_ids": {"$in": list(within)}})
    if track:
        track_nodes = await db.distinct(SyllabusNode, "_id", {"track": track})
        item_clauses.append({"node_ids": {"$in": track_nodes}})

    nodes = await db.find(SyllabusNode, node_match, sort=[("kind", 1), ("name", 1)], limit=25)
    items = await db.find(
        ContentItem, {"$and": [c for c in item_clauses if c]}, sort=[("title", 1)], limit=25
    )
    paths = await _paths(db, nodes)
    return schemas.SearchResults(
        query=q,
        nodes=[
            schemas.SearchNodeHit(
                id=n.id, name=n.name, kind=n.kind, track=n.track, path=paths[n.id]
            )
            for n in nodes
        ],
        items=[
            schemas.SearchItemHit(
                id=i.id,
                title=i.title,
                kind=i.kind,
                medium=i.medium,
                status=i.status,
                node_ids=i.node_ids,
            )
            for i in items
        ],
    )


# ---------------------------------------------------------------------- class syllabus


async def _linked_nodes(db: Db, node_ids: Sequence[uuid.UUID]) -> list[schemas.LinkedNode]:
    nodes = await db.find(SyllabusNode, {"_id": ids_in(node_ids)})
    paths = await _paths(db, nodes)
    by_id = {n.id: n for n in nodes}
    return [
        schemas.LinkedNode(id=n.id, name=n.name, kind=n.kind, track=n.track, path=paths[n.id])
        for n in (by_id.get(i) for i in node_ids)
        if n is not None
    ]


async def _require_class(db: Db, class_id: uuid.UUID) -> Class:
    found = await db.get(Class, class_id)
    if found is None:
        raise NotFound("That class does not exist.")
    return found


async def get_class_syllabus(
    db: Db, *, guard: Authorized, class_id: uuid.UUID
) -> schemas.ClassSyllabusOut:
    klass = await _require_class(db, class_id)
    await guard.ensure_class(class_id)
    reader = await resolve_reader(db, guard)
    if reader.narrowed:
        role_keys = {a.role_key for a in guard.context.assignments}
        if class_id not in await access.linked_class_ids(db, guard.user_id, role_keys):
            raise NotFound("That class does not exist.")
    rows = await db.find(ClassSyllabus, {"class_id": class_id}, sort=[("created_at", 1)])
    return schemas.ClassSyllabusOut(
        class_id=klass.id,
        class_name=klass.name if not klass.section else f"{klass.name} {klass.section}",
        nodes=await _linked_nodes(db, [r.node_id for r in rows]),
    )


async def set_class_syllabus(
    db: Db,
    *,
    guard: Authorized,
    class_id: uuid.UUID,
    node_ids: list[uuid.UUID],
    meta: RequestMeta,
) -> None:
    """Replace a class's links. Needs ``class:update`` on the class, and the library module."""
    klass = await _require_class(db, class_id)
    await guard.ensure_class(class_id)  # library:read here: the module must be on
    await with_permission(db, guard, "class:update").ensure_class(class_id)
    if node_ids:
        found = await db.count(
            SyllabusNode,
            {
                "_id": ids_in(node_ids),
                "status": "active",
                "institute_id": {"$in": [None, klass.institute_id]},
            },
        )
        if found != len(node_ids):
            raise ValidationFailed("Choose parts of the syllabus that exist in this library.")
    existing = {r.node_id for r in await db.find(ClassSyllabus, {"class_id": class_id})}
    wanted = set(node_ids)
    for node_id in node_ids:
        if node_id not in existing:
            db.add(
                ClassSyllabus(class_id=class_id, institute_id=klass.institute_id, node_id=node_id)
            )
    if existing - wanted:
        db.delete_many(ClassSyllabus, {"class_id": class_id, "node_id": ids_in(existing - wanted)})
    _audit(
        db,
        guard.user_id,
        meta,
        events.CLASS_SYLLABUS_UPDATED,
        target_type="class",
        target_id=class_id,
        institute_id=klass.institute_id,
        extra={"node_ids": [str(n) for n in node_ids]},
    )


async def my_syllabus(db: Db, *, guard: Authorized) -> list[schemas.MySyllabusOut]:
    """What a student, parent or teacher is linked to, class by class."""
    from app.modules.rbac import repository as rbac_repo
    from app.modules.rbac.catalog import FACULTY, PARENT, STUDENT
    from app.modules.users.models import Guardian, User

    await resolve_reader(db, guard)  # module gating
    role_keys = {a.role_key for a in guard.context.assignments}
    pairs: list[tuple[uuid.UUID, uuid.UUID | None]] = []
    if STUDENT in role_keys:
        pairs += [(c, None) for c in await rbac_repo.student_class_ids(db, guard.user_id)]
    if FACULTY in role_keys:
        pairs += [(c, None) for c in await rbac_repo.faculty_class_ids(db, guard.user_id)]
    if PARENT in role_keys:
        for child in await db.distinct(
            Guardian, "student_user_id", {"parent_user_id": guard.user_id}
        ):
            pairs += [(c, child) for c in await rbac_repo.student_class_ids(db, child)]
    if not pairs:
        return []

    classes = {c.id: c for c in await db.find(Class, {"_id": ids_in({p[0] for p in pairs})})}
    names = {
        u["_id"]: u["full_name"]
        for u in await db.raw(
            User, {"_id": ids_in({p[1] for p in pairs if p[1]})}, {"full_name": 1}
        )
    }
    links: dict[uuid.UUID, list[uuid.UUID]] = {}
    for row in await db.find(
        ClassSyllabus, {"class_id": ids_in(classes)}, sort=[("created_at", 1)]
    ):
        links.setdefault(row.class_id, []).append(row.node_id)
    out = []
    for class_id, child in dict.fromkeys(pairs):
        klass = classes.get(class_id)
        if klass is None:
            continue
        out.append(
            schemas.MySyllabusOut(
                class_id=class_id,
                class_name=klass.name if not klass.section else f"{klass.name} {klass.section}",
                student_user_id=child,
                student_name=names.get(child) if child else None,
                nodes=await _linked_nodes(db, links.get(class_id, [])),
            )
        )
    return out
