"""Writing paths into the syllabus tree, idempotently.

Shared by the seed command and the spreadsheet import, which are the same operation with
different input: "make sure this path exists, with these names". A node is matched on its
``code_path`` within one library, or failing that on its name (case-insensitive) among its
parent's children — the seed uses hand-picked codes (``gs-1``, ``evs``) a spreadsheet row
cannot spell. A miss is created, and nothing is ever deleted — so running either twice
changes nothing the second time. The seed updates a match's name; an import never renames.

An institute importing its own topics may hang them under the master syllabus: an existing
master node at a path is reused as the parent rather than copied into the institute's
library. Master nodes are never renamed by an institute's import.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.core.db import Db
from app.modules.library.models import SyllabusNode
from app.modules.library.rules import check_kind, child_path, slugify


def _name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


@dataclass(slots=True)
class WriteCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "by_kind": dict(sorted(self.by_kind.items())),
        }


class TreeWriter:
    """Holds every node of the tracks it has touched, so a 5,000-row import costs one read
    per track rather than one per row."""

    def __init__(self, db: Db, institute_id: uuid.UUID | None, *, rename: bool = True) -> None:
        self.db = db
        self.institute_id = institute_id
        self.rename = rename
        self.counts = WriteCounts()
        self._own: dict[str, SyllabusNode] = {}
        self._master: dict[str, SyllabusNode] = {}
        self._names: dict[tuple[uuid.UUID | None, str], SyllabusNode] = {}
        self._next_order: dict[uuid.UUID | None, int] = {}
        self._loaded: set[str] = set()
        self._seen: set[uuid.UUID] = set()

    async def load(self, track: str) -> None:
        if track in self._loaded:
            return
        libraries = [None] if self.institute_id is None else [None, self.institute_id]
        for node in await self.db.find(
            SyllabusNode, {"track": track, "institute_id": {"$in": libraries}}
        ):
            target = self._own if node.institute_id == self.institute_id else self._master
            target[node.code_path] = node
            key = (node.parent_id, _name_key(node.name))
            if key not in self._names or node.institute_id == self.institute_id:
                self._names[key] = node
            self._next_order[node.parent_id] = max(
                self._next_order.get(node.parent_id, 0), node.order + 1
            )
        self._loaded.add(track)

    def find(self, path: str) -> SyllabusNode | None:
        return self._own.get(path) or self._master.get(path)

    def ensure(
        self,
        parent: SyllabusNode | None,
        *,
        track: str,
        kind: str,
        name: str,
        code: str | None = None,
        mediums: list[str] | None = None,
        difficulty: str | None = None,
        exam_tags: list[str] | None = None,
    ) -> SyllabusNode:
        """The node at this path, created or renamed as needed. ``load(track)`` first."""
        code = code or slugify(name) or "node"
        path = child_path(parent.code_path if parent else None, code)
        parent_id = parent.id if parent else None
        existing = self.find(path) or self._names.get((parent_id, _name_key(name)))

        if existing is not None:
            mine = existing.institute_id == self.institute_id
            if existing.id in self._seen or not mine:
                return existing
            self._seen.add(existing.id)
            changed = False
            for attr, value in (
                ("name", name if self.rename else None),
                ("mediums", mediums),
                ("difficulty", difficulty),
                ("exam_tags", exam_tags),
            ):
                if value is not None and getattr(existing, attr) != value:
                    setattr(existing, attr, value)
                    changed = True
            if existing.status == "archived":
                existing.status = "active"
                changed = True
            if changed:
                self.counts.updated += 1
            else:
                self.counts.unchanged += 1
            return existing

        check_kind(parent.kind if parent else None, kind)
        node = SyllabusNode(
            institute_id=self.institute_id,
            track=track,  # type: ignore[arg-type]
            parent_id=parent_id,
            ancestors=[*parent.ancestors, parent.id] if parent else [],
            kind=kind,  # type: ignore[arg-type]
            name=name,
            code=code,
            code_path=path,
            order=self._next_order.get(parent_id, 0),
            mediums=mediums if mediums is not None else ["hi", "en"],
            difficulty=difficulty,  # type: ignore[arg-type]
            exam_tags=exam_tags or [],
        )
        self._next_order[parent_id] = node.order + 1
        self.db.add(node)
        self._own[path] = node
        self._names[(parent_id, _name_key(name))] = node
        self._seen.add(node.id)
        self.counts.created += 1
        self.counts.by_kind[kind] = self.counts.by_kind.get(kind, 0) + 1
        return node
