"""MongoDB connection, the shared document bases, and the per-request unit of work.

The services were written against a session that stages writes and commits them at the end
of a use case, and that rolls everything back when the use case raises. ``Db`` keeps that
contract on MongoDB:

* ``add()``, ``delete()``, ``update_many()`` and ``delete_many()`` only *queue* a write.
  Nothing reaches the database until ``commit()``, which applies the queue in order. A use
  case that raises half-way has written nothing — the same guarantee a rollback gave — so a
  refused invitation never leaves an orphaned account behind.
* Documents read through ``get``/``find_one``/``find`` are tracked. At commit, any whose
  fields changed are saved with ``$set`` of *just those fields*, never a whole-document
  replace: a sign-in recording ``last_login_at`` must not overwrite a suspension an
  administrator wrote a moment earlier.
* Reads do not see queued writes, exactly as with ``autoflush=False`` before. ``get()`` is
  the exception: it returns a document added earlier in the same unit of work, because ids
  are generated in the application and a caller holding one expects to find it.

Ids are UUIDs, generated here rather than by the server, so ``flush()`` has nothing left to
do and is kept only so the services read the same as before.

What this cannot give is atomicity across documents *within* ``commit()``: if the third of
five writes fails, the first two stay. Every use case commits once, at the end, after all its
checks have passed, so the window is a database error mid-commit — not a refused request.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from beanie import Document, Replace, Save, SaveChanges, before_event, init_beanie
from pydantic import Field
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class UuidDocument(Document):
    """A document keyed by a UUID generated in the application, never by the server.

    UUIDs rather than ObjectIds because access tokens, audit rows and every API response
    already carry UUIDs. Every model's ``Settings`` turns on ``use_state_management``
    itself (Beanie does not inherit ``Settings``): that is what lets the unit of work
    save only the fields a service changed.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)


class TimestampedDocument(UuidDocument):
    """``created_at`` / ``updated_at`` on every collection.

    ``updated_at`` is refreshed whenever a document is saved; bulk ``update_many`` writes
    bypass Beanie's hooks, so the unit of work stamps it on those itself.
    """

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @before_event(Replace, Save, SaveChanges)
    def _touch(self) -> None:
        self.updated_at = utcnow()


def document_models() -> list[type[Document]]:
    """Every collection Beanie manages. Imported lazily to keep module imports acyclic."""
    from app.modules.audit.models import AuditLog
    from app.modules.auth.models import PasswordOtp, RefreshToken
    from app.modules.org.models import (
        AcademicSession,
        Branch,
        Class,
        ClassEnrollment,
        ClassFaculty,
        Institute,
        Organisation,
    )
    from app.modules.rbac.models import (
        InstituteModule,
        InstituteRolePermission,
        Module,
        Permission,
        Role,
        RolePermission,
        UserPermissionGrant,
        UserRoleAssignment,
    )
    from app.modules.users.models import Guardian, User, UserPreference

    return [
        User,
        UserPreference,
        Guardian,
        RefreshToken,
        PasswordOtp,
        Organisation,
        Institute,
        Branch,
        AcademicSession,
        Class,
        ClassFaculty,
        ClassEnrollment,
        Module,
        Permission,
        Role,
        RolePermission,
        InstituteRolePermission,
        UserRoleAssignment,
        UserPermissionGrant,
        InstituteModule,
        AuditLog,
    ]


# ------------------------------------------------------------------------- connection

_client: AsyncMongoClient | None = None
_database: AsyncDatabase | None = None


def build_client(url: str) -> AsyncMongoClient:
    """``uuidRepresentation='standard'`` stores UUIDs as BSON subtype 4, readable by every
    driver; ``tz_aware`` returns UTC-aware datetimes, matching ``datetime.now(UTC)``.

    **The pool is bounded, and the bound matters more than it looks.** The driver's own
    default is a hundred connections *per process*. On a platform that starts a new
    container whenever traffic rises, that is a hundred per container, multiplied by
    however many are running — and a shared Atlas cluster allows a few hundred in total.
    The failure arrives exactly when the product is going well: enough traffic to start a
    third container, and requests begin failing because the cluster will not accept
    another connection.

    The arithmetic to hold to, when either number changes::

        max_instances × MONGODB_MAX_POOL_SIZE  ≤  0.8 × the cluster's connection limit

    Twenty is deliberately generous for one container — each request holds a connection
    only while a query is in flight — and leaves room for ten containers against a free
    tier's five hundred.
    """
    return AsyncMongoClient(
        url,
        uuidRepresentation="standard",
        tz_aware=True,
        maxPoolSize=settings.mongodb_max_pool_size,
        serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
        appname=settings.app_name,
    )


async def init_db(url: str | None = None, db_name: str | None = None) -> AsyncDatabase:
    """Connect, register every document model and create their indexes. Idempotent."""
    global _client, _database
    if _database is not None and url is None and db_name is None:
        return _database
    if url is None:
        if settings.mongodb_url is None:
            raise RuntimeError("MONGODB_URL is not set; see backend/.env.example.")
        url = settings.mongodb_url.get_secret_value()
    client = build_client(url)
    database = client[db_name or settings.mongodb_db_name]
    models = document_models()
    await _drop_redefined_indexes(database, models)
    # `allow_index_dropping`: indexes are owned by the code. One removed from a model is
    # removed from the database, rather than lingering and slowing every write.
    await init_beanie(database=database, document_models=models, allow_index_dropping=True)
    _client, _database = client, database
    return database


async def _drop_redefined_indexes(database: AsyncDatabase, models: list[type[Document]]) -> None:
    """Drop any index whose name is reused for a different definition.

    MongoDB refuses to create an index under a name that already exists with other keys or
    options, so changing an index in a model without renaming it would fail every deploy
    after the first. This is the schema migration MongoDB otherwise does not have: the old
    definition is dropped here and Beanie builds the new one straight after.
    """
    existing_collections = set(await database.list_collection_names())
    for model in models:
        name = model.Settings.name
        if name not in existing_collections:
            continue
        collection = database[name]
        existing = await collection.index_information()
        for index in getattr(model.Settings, "indexes", []):
            wanted = index.document
            current = existing.get(wanted["name"])
            if current is None:
                continue
            same = list(current["key"]) == list(wanted["key"].items()) and bool(
                current.get("unique")
            ) == bool(wanted.get("unique"))
            if not same:
                await collection.drop_index(wanted["name"])


async def close_db() -> None:
    global _client, _database
    if _client is not None:
        await _client.close()
    _client, _database = None, None


async def ping() -> None:
    if _client is None:
        raise RuntimeError("The database is not initialised.")
    await _client.admin.command("ping")


# ----------------------------------------------------------------------- unit of work

D = TypeVar("D", bound=Document)

Filter = Mapping[str, Any]
Sort = Sequence[tuple[str, int]]


@dataclass(slots=True)
class _Insert:
    doc: Document


@dataclass(slots=True)
class _Delete:
    doc: Document


@dataclass(slots=True)
class _UpdateMany:
    model: type[Document]
    match: dict[str, Any]
    values: dict[str, Any]


@dataclass(slots=True)
class _DeleteMany:
    model: type[Document]
    match: dict[str, Any]


class Db:
    """One unit of work per request. See the module docstring for the contract."""

    __slots__ = ("_identity", "_queue")

    def __init__(self) -> None:
        self._identity: dict[tuple[type[Document], Any], Document] = {}
        self._queue: list[_Insert | _Delete | _UpdateMany | _DeleteMany] = []

    # --------------------------------------------------------------------- tracking

    def track(self, doc: D) -> D:
        """Keep one in-memory instance per document, so two reads of the same row in one
        request see each other's edits — the identity map a session gave for free."""
        key = (type(doc), doc.id)
        existing = self._identity.get(key)
        if existing is not None:
            return existing  # type: ignore[return-value]
        self._identity[key] = doc
        return doc

    # ------------------------------------------------------------------------ reads

    async def get(self, model: type[D], doc_id: Any) -> D | None:
        if doc_id is None:
            return None
        found = self._identity.get((model, doc_id))
        if found is not None:
            return found  # type: ignore[return-value]
        doc = await model.get(doc_id)
        return self.track(doc) if doc is not None else None

    async def find_one(
        self, model: type[D], match: Filter, *, sort: Sort | None = None
    ) -> D | None:
        query = model.find(dict(match))
        if sort:
            query = query.sort(list(sort))
        doc = await query.first_or_none()
        return self.track(doc) if doc is not None else None

    async def find(
        self,
        model: type[D],
        match: Filter,
        *,
        sort: Sort | None = None,
        limit: int | None = None,
        skip: int | None = None,
    ) -> list[D]:
        query = model.find(dict(match))
        if sort:
            query = query.sort(list(sort))
        if skip:
            query = query.skip(skip)
        if limit is not None:
            query = query.limit(limit)
        return [self.track(doc) for doc in await query.to_list()]

    async def count(self, model: type[Document], match: Filter) -> int:
        return await model.get_pymongo_collection().count_documents(dict(match))

    async def exists(self, model: type[Document], match: Filter) -> bool:
        found = await model.get_pymongo_collection().find_one(dict(match), {"_id": 1})
        return found is not None

    async def distinct(self, model: type[Document], field: str, match: Filter) -> list[Any]:
        return await model.get_pymongo_collection().distinct(field, dict(match))

    async def aggregate(self, model: type[Document], pipeline: list[dict]) -> list[dict]:
        cursor = await model.get_pymongo_collection().aggregate(pipeline)
        return await cursor.to_list()

    async def raw(
        self,
        model: type[Document],
        match: Filter,
        projection: Mapping[str, Any],
        *,
        sort: Sort | None = None,
    ) -> list[dict[str, Any]]:
        """Selected fields only, as plain dicts — for joins and lookups where loading and
        validating whole documents would be waste."""
        cursor = model.get_pymongo_collection().find(dict(match), dict(projection))
        if sort:
            cursor = cursor.sort(list(sort))
        return await cursor.to_list()

    # ----------------------------------------------------------------------- writes

    def add(self, doc: Document) -> None:
        self._identity[(type(doc), doc.id)] = doc
        self._queue.append(_Insert(doc))

    def add_all(self, docs: Iterable[Document]) -> None:
        for doc in docs:
            self.add(doc)

    async def delete(self, doc: Document) -> None:
        self._identity.pop((type(doc), doc.id), None)
        self._queue.append(_Delete(doc))

    def update_many(self, model: type[Document], match: Filter, values: Mapping[str, Any]) -> None:
        """Queue ``$set`` on every matching document (``UPDATE … WHERE``)."""
        stamped = dict(values)
        if issubclass(model, TimestampedDocument):
            stamped.setdefault("updated_at", utcnow())
        self._queue.append(_UpdateMany(model, dict(match), stamped))

    def delete_many(self, model: type[Document], match: Filter) -> None:
        self._queue.append(_DeleteMany(model, dict(match)))

    async def flush(self) -> None:
        """Nothing to do: ids are generated client-side, and writes wait for ``commit``."""

    async def commit(self) -> None:
        queue, self._queue = self._queue, []
        inserted: set[int] = set()
        pending: list[Document] = []

        async def insert_pending() -> None:
            # Consecutive inserts into one collection go as a single insert_many: the seed
            # writes about a hundred documents, and one round trip each to Atlas is most of
            # a minute. Order across collections is preserved because any other kind of
            # write ends the batch first.
            if not pending:
                return
            if len(pending) == 1:
                await pending[0].insert()
            else:
                await type(pending[0]).insert_many(pending)
                for doc in pending:
                    doc._save_state()  # what insert() does, so later edits are detected
            inserted.update(id(doc) for doc in pending)
            pending.clear()

        for op in queue:
            if isinstance(op, _Insert):
                if pending and type(pending[0]) is not type(op.doc):
                    await insert_pending()
                pending.append(op.doc)
                continue
            await insert_pending()
            if isinstance(op, _Delete):
                await op.doc.delete()
            elif isinstance(op, _UpdateMany):
                await op.model.get_pymongo_collection().update_many(op.match, {"$set": op.values})
            else:
                await op.model.get_pymongo_collection().delete_many(op.match)
        await insert_pending()

        # Then every tracked document a service edited in place.
        for doc in list(self._identity.values()):
            if id(doc) in inserted:
                continue
            if doc.is_changed:
                await doc.save_changes()

    async def rollback(self) -> None:
        """Forget everything queued and every unsaved edit. Nothing was written yet."""
        self._queue.clear()
        self._identity.clear()

    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        """Undo this block's writes if it raises; keep them if it does not.

        The bulk import needs it: five hundred learners, and a duplicate address on line
        212 must roll back line 212 and nothing else. Without that, one bad row at the end
        discards four hundred good ones and the school has no way to tell which to remove
        before trying again.

        PostgreSQL gave this for free as a SAVEPOINT. MongoDB has no savepoints, and its
        transactions need a replica set — but none of that is needed here, because nothing
        in this unit of work has reached the database yet. The queue *is* the transaction,
        so undoing a block is truncating the queue back to where it started.

        What it does not undo is an edit made in place to a document that was already
        tracked before the block began. Documents created inside the block are untracked
        again on failure; a field changed on a pre-existing one is not. No caller does
        that today, and the alternative — snapshotting every tracked document — would cost
        more on every row than it saves on the rare one that fails.
        """
        queued = len(self._queue)
        tracked = set(self._identity)
        try:
            yield
        except Exception:
            del self._queue[queued:]
            for key in set(self._identity) - tracked:
                self._identity.pop(key, None)
            raise


async def get_db() -> AsyncGenerator[Db]:
    """One unit of work per request. Anything not committed is simply discarded."""
    db = Db()
    try:
        yield db
    except Exception:
        await db.rollback()
        raise


def ids_in(values: Iterable[Any]) -> dict[str, list[Any]]:
    """``{"$in": [...]}`` from any iterable — sets and frozensets included."""
    return {"$in": list(values)}


def ilike(term: str) -> dict[str, str]:
    """A case-insensitive *contains* match on exactly the characters somebody typed.

    ``re.escape`` so a search for ``.*`` or ``a+b`` matches those characters literally
    rather than every row — the regex equivalent of escaping ``%`` and ``_`` in LIKE.
    """
    import re

    return {"$regex": re.escape(term.strip()), "$options": "i"}


def iexact(term: str) -> dict[str, str]:
    """Case-insensitive equality, for codes and names compared ignoring case."""
    import re

    return {"$regex": f"^{re.escape(term.strip())}$", "$options": "i"}
