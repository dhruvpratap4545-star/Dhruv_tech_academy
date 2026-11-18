"""Moving syllabus data written before the four fixed levels onto Track › Level › Subject › Topic.

Earlier, a syllabus could be up to six levels deep (… › Subject › Unit › Chapter › Topic).
This rewrites any such tree in place:

* a **unit** is archived, and its chapters move up to sit directly under the subject;
* a **chapter** becomes a **topic** under its subject;
* anything **below** a topic (the finer points a chapter listed) is archived, and material
  or class links that pointed at it are moved to the topic above it, so nothing a learner
  could see before disappears.

Nothing is deleted. It runs before every syllabus seed and from ``python -m app.cli
flatten-syllabus``; on data that already has four levels it finds nothing to do.

Paths are rewritten in two passes — every moving node first gets a temporary unique path,
then its final one — because ``code_path`` is unique per library and a chapter's new path can
be another node's old one until that node has moved too.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Any

from pymongo import UpdateOne

from app.core.db import Db, utcnow
from app.modules.library.models import ClassSyllabus, ContentItem, SyllabusNode
from app.modules.library.rules import child_path, next_kind

logger = logging.getLogger(__name__)

_LEGACY = ("unit", "chapter")


async def needs_flattening() -> bool:
    """Archived nodes are history and stay as they were; only the live tree is checked."""
    nodes = SyllabusNode.get_pymongo_collection()
    live = {"status": "active"}
    if await nodes.find_one({**live, "kind": {"$in": list(_LEGACY)}}, {"_id": 1}):
        return True
    # A topic more than three levels down sits under another topic.
    deep = {**live, "kind": "topic", "ancestors.3": {"$exists": True}}
    return bool(await nodes.find_one(deep, {"_id": 1}))


async def flatten_to_four_levels(db: Db | None = None) -> dict[str, int]:
    """Convert every library's syllabus to four levels. Returns what changed."""
    if not await needs_flattening():
        return {"moved": 0, "archived": 0, "items_relinked": 0, "class_links_moved": 0}

    collection = SyllabusNode.get_pymongo_collection()
    nodes: list[dict[str, Any]] = await collection.find({"status": "active"}).to_list()
    by_id = {n["_id"]: n for n in nodes}
    children: dict[uuid.UUID | None, list[dict[str, Any]]] = defaultdict(list)
    for node in sorted(nodes, key=lambda n: (n.get("order", 0), n["name"])):
        children[node.get("parent_id")].append(node)

    kept_kind: dict[uuid.UUID, str] = {}
    kept_parent: dict[uuid.UUID, uuid.UUID | None] = {}
    archived: set[uuid.UUID] = set()
    #: An archived node → the kept node its material and class links now belong to.
    redirect: dict[uuid.UUID, uuid.UUID] = {}

    def keep(node: dict[str, Any], kind: str, parent: uuid.UUID | None) -> None:
        kept_kind[node["_id"]] = kind
        kept_parent[node["_id"]] = parent

    def drop(node: dict[str, Any], into: uuid.UUID | None) -> None:
        archived.add(node["_id"])
        if into is not None:
            redirect[node["_id"]] = into

    def visit(node: dict[str, Any], parent: uuid.UUID | None) -> None:
        parent_kind = kept_kind.get(parent) if parent else None
        expected = next_kind(parent_kind)
        kind = node["kind"]
        if kind == "unit":
            # No level of its own: its chapters attach to the subject above it.
            drop(node, parent)
            for child in children[node["_id"]]:
                visit(child, parent)
            return
        if kind == "chapter":
            kind = "topic"
        if kind == expected:
            keep(node, kind, parent)
            for child in children[node["_id"]]:
                visit(child, node["_id"])
            return
        # Does not fit at this depth (a point inside a chapter, or a stray level).
        drop(node, parent)
        for child in children[node["_id"]]:
            visit(child, parent)

    for root in children[None]:
        visit(root, None)
    # A node whose parent no longer exists is left exactly as it is.

    # Final ancestors, order and paths, top-down so a parent is always settled first.
    final: dict[uuid.UUID, dict[str, Any]] = {}
    # Paths already held by archived nodes are taken too: the unique index covers them.
    used: set[tuple[uuid.UUID | None, str]] = {
        (n.get("institute_id"), n["code_path"])
        async for n in collection.find(
            {"status": {"$ne": "active"}}, {"institute_id": 1, "code_path": 1}
        )
    }
    # A node that keeps its parent keeps its place; one that moved up goes after them.
    next_order: dict[uuid.UUID | None, int] = defaultdict(int)
    for node_id, parent in kept_parent.items():
        if by_id[node_id].get("parent_id") == parent:
            order = by_id[node_id].get("order", 0)
            next_order[parent] = max(next_order[parent], order + 1)

    def settle(node_id: uuid.UUID) -> None:
        node = by_id[node_id]
        parent = kept_parent[node_id]
        parent_final = final[parent] if parent else None
        library = node.get("institute_id")
        code = node["code"]
        path = child_path(parent_final["code_path"] if parent_final else None, code)
        suffix = 2
        while (library, path) in used:
            code = f"{node['code']}-{suffix}"
            path = child_path(parent_final["code_path"] if parent_final else None, code)
            suffix += 1
        used.add((library, path))
        final[node_id] = {
            "kind": kept_kind[node_id],
            "parent_id": parent,
            "ancestors": [*parent_final["ancestors"], parent] if parent_final else [],
            "code": code,
            "code_path": path,
            "order": node.get("order", 0),
        }
        if node.get("parent_id") != parent:
            final[node_id]["order"] = next_order[parent]
            next_order[parent] += 1

    def settle_tree(parent: uuid.UUID | None) -> None:
        for node_id in [i for i, p in kept_parent.items() if p == parent]:
            settle(node_id)
            settle_tree(node_id)

    # Children in their original reading order, which the dict preserves from `visit`.
    settle_tree(None)

    now = utcnow()
    moving = [
        node_id
        for node_id, f in final.items()
        if any(by_id[node_id].get(k) != v for k, v in f.items())
    ]
    temporary = [
        UpdateOne({"_id": node_id}, {"$set": {"code_path": f"__flatten__/{node_id}"}})
        for node_id in [*moving, *archived]
    ]
    if temporary:
        await collection.bulk_write(temporary, ordered=False)
    updates = [
        UpdateOne({"_id": node_id}, {"$set": {**final[node_id], "updated_at": now}})
        for node_id in moving
    ] + [
        UpdateOne(
            {"_id": node_id},
            {
                "$set": {
                    "status": "archived",
                    # Kept unique and readable; an archived node is never matched by path.
                    "code_path": f"{by_id[node_id]['code_path']}~{node_id.hex[:8]}",
                    "updated_at": now,
                }
            },
        )
        for node_id in archived
    ]
    if updates:
        await collection.bulk_write(updates, ordered=False)

    def resolve(node_id: uuid.UUID) -> uuid.UUID:
        while node_id in redirect:
            node_id = redirect[node_id]
        return node_id

    items_relinked = 0
    items = ContentItem.get_pymongo_collection()
    if archived:
        for item in await items.find({"node_ids": {"$in": list(archived)}}).to_list():
            relinked = list(dict.fromkeys(resolve(n) for n in item["node_ids"]))
            await items.update_one(
                {"_id": item["_id"]}, {"$set": {"node_ids": relinked, "updated_at": now}}
            )
            items_relinked += 1

    class_links_moved = 0
    links = ClassSyllabus.get_pymongo_collection()
    if archived:
        for link in await links.find({"node_id": {"$in": list(archived)}}).to_list():
            target = resolve(link["node_id"])
            if await links.find_one({"class_id": link["class_id"], "node_id": target}):
                await links.delete_one({"_id": link["_id"]})
            else:
                await links.update_one(
                    {"_id": link["_id"]}, {"$set": {"node_id": target, "updated_at": now}}
                )
            class_links_moved += 1

    counts = {
        "moved": len(moving),
        "archived": len(archived),
        "items_relinked": items_relinked,
        "class_links_moved": class_links_moved,
    }
    logger.info("syllabus flattened to four levels", extra=counts)
    return counts
