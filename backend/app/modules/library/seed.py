"""Loading the master syllabus from ``seed_data/*.json``.

Each file is one track, written as a nested outline so a subject expert can read and correct
it directly. A node is ``{"kind", "name", "code"?, "exam_tags"?, "children"?}``; to keep the
files short, a node may instead list its children under the plural of their kind —
``"subjects"``, ``"units"``, ``"chapters"``, ``"topics"`` — as plain names or nested nodes.

``exam_tags`` is inherited downwards: tagging Class 11 Physics ``["cbse", "jee", "neet"]``
tags every chapter and topic in it, which is how one chapter serves three exams without
the material being copied three times.

Idempotent through ``TreeWriter``: matched on code path, names updated, missing nodes added,
nothing deleted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.db import Db
from app.core.errors import ValidationFailed
from app.modules.library.models import TRACKS, SyllabusNode
from app.modules.library.tree import TreeWriter

SEED_DIR = Path(__file__).parent / "seed_data"
SEEDED_TRACKS: tuple[str, ...] = ("cbse", "neet", "jee", "upsc")
_PLURALS = {
    "levels": "level",
    "subjects": "subject",
    "units": "unit",
    "chapters": "chapter",
    "topics": "topic",
}


def load_file(track: str) -> dict[str, Any]:
    return json.loads((SEED_DIR / f"{track}.json").read_text(encoding="utf-8"))


def children_of(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the shorthand keys into a flat list of child nodes, in file order."""
    out: list[dict[str, Any]] = list(spec.get("children", []))
    for plural, kind in _PLURALS.items():
        for child in spec.get(plural, []):
            out.append(
                {"kind": kind, "name": child} if isinstance(child, str) else {"kind": kind, **child}
            )
    return out


def _walk(
    writer: TreeWriter,
    parent: SyllabusNode,
    spec: dict[str, Any],
    track: str,
    tags: list[str],
) -> None:
    for child in children_of(spec):
        child_tags = child.get("exam_tags", tags)
        node = writer.ensure(
            parent,
            track=track,
            kind=child["kind"],
            name=child["name"],
            code=child.get("code"),
            exam_tags=child_tags,
        )
        _walk(writer, node, child, track, child_tags)


async def seed_syllabus(db: Db, track: str | None = None) -> dict[str, Any]:
    """Load one track (or all four) into the master library and commit. Returns counts."""
    if track is not None and track not in SEEDED_TRACKS:
        raise ValidationFailed(f"Unknown track {track!r}. Choose from {', '.join(SEEDED_TRACKS)}.")
    results: dict[str, Any] = {}
    for name in [track] if track else list(SEEDED_TRACKS):
        assert name in TRACKS
        data = load_file(name)
        writer = TreeWriter(db, None)
        await writer.load(name)
        root_tags = data.get("exam_tags", [name])
        root = writer.ensure(
            None, track=name, kind="track", name=data["name"], code=name, exam_tags=root_tags
        )
        _walk(writer, root, data, name, root_tags)
        await db.commit()
        results[name] = {
            "source": data.get("source"),
            "as_of": data.get("as_of"),
            **writer.counts.as_dict(),
        }
    return results
