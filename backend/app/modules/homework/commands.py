"""Command-line entry points for the Homework Board, wired into ``app/cli.py``."""

from __future__ import annotations

from app.core.db import Db, close_db, init_db


async def homework_digest_command() -> None:
    """``python -m app.cli homework-digest`` — the weekly parent digest."""
    from app.modules.homework.digest import send_digests

    await init_db()
    try:
        count = await send_digests(Db())
        print(f"Sent the homework digest to {count} parent(s).")
    finally:
        await close_db()
