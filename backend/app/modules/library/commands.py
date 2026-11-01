"""``python -m app.cli seed-syllabus [--track cbse]`` — wired into ``app/cli.py``.

Safe to run on every deploy, like the main seed: it adds what is missing and renames what
changed, and never deletes.
"""

from __future__ import annotations

from app.core.db import Db, close_db, init_db
from app.modules.library.seed import seed_syllabus


async def seed_syllabus_command(track: str | None) -> None:
    await init_db()
    try:
        results = await seed_syllabus(Db(), track)
    finally:
        await close_db()
    for name, counts in results.items():
        print(
            f"{name}: {counts['created']} created, {counts['updated']} updated, "
            f"{counts['unchanged']} unchanged (source: {counts['source']}, as of {counts['as_of']})"
        )
