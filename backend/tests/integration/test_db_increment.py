"""`Db.increment`: atomic counters inside the unit of work (Phase 3 gap 4)."""

from __future__ import annotations

import asyncio

from app.core.db import Db
from app.modules.rbac.models import Module


async def _module(db: Db) -> Module:
    row = Module(key="counter_test", name="Counter")
    db.add(row)
    await db.commit()
    return row


async def test_increment_waits_for_commit(db: Db, seeded) -> None:
    row = await _module(db)
    uow = Db()
    uow.increment(Module, {"_id": row.id}, {"hits": 3})

    raw = await Module.get_pymongo_collection().find_one({"_id": row.id})
    assert "hits" not in raw

    await uow.commit()
    raw = await Module.get_pymongo_collection().find_one({"_id": row.id})
    assert raw["hits"] == 3


async def test_a_rolled_back_unit_of_work_increments_nothing(db: Db, seeded) -> None:
    row = await _module(db)
    uow = Db()
    uow.increment(Module, {"_id": row.id}, {"hits": 3})
    await uow.rollback()
    await uow.commit()

    raw = await Module.get_pymongo_collection().find_one({"_id": row.id})
    assert "hits" not in raw


async def test_concurrent_increments_all_land(db: Db, seeded) -> None:
    """The point of `$inc`: twenty requests at once lose nothing."""
    row = await _module(db)

    async def bump() -> None:
        uow = Db()
        uow.increment(Module, {"_id": row.id}, {"hits": 1, "paise": 25})
        await uow.commit()

    await asyncio.gather(*(bump() for _ in range(20)))

    raw = await Module.get_pymongo_collection().find_one({"_id": row.id})
    assert raw["hits"] == 20
    assert raw["paise"] == 500


async def test_set_values_ride_along_with_the_increment(db: Db, seeded) -> None:
    row = await _module(db)
    uow = Db()
    uow.increment(Module, {"_id": row.id}, {"hits": 1}, set_values={"description": "bumped"})
    await uow.commit()

    raw = await Module.get_pymongo_collection().find_one({"_id": row.id})
    assert raw["hits"] == 1
    assert raw["description"] == "bumped"
    assert raw["updated_at"] is not None
