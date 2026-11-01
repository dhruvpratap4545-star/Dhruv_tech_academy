"""Storing uploads and deciding who may download them.

**The owning module decides access.** A file is only ever reachable through the thing that
references it — a homework, a submission, a library item — so whether someone may download
it is exactly whether they may see that thing. Each owning module registers an access
check for its purposes with ``register_access``; ``can_read`` asks the right one. The files
module itself knows nothing about homework or syllabi.

Files are never public. A download is a 302 to a five-minute signed URL (GCS) or, on local
disk, the bytes streamed by the API.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable

from fastapi import UploadFile

from app.core.config import settings
from app.core.db import Db, ids_in
from app.core.errors import NotFound, ValidationFailed
from app.core.storage import get_storage
from app.modules.audit import events
from app.modules.audit import service as audit
from app.modules.files.models import StoredFile
from app.modules.files.validation import max_bytes, validate_upload
from app.modules.rbac.context import AuthContext

logger = logging.getLogger(__name__)

AccessCheck = Callable[[Db, AuthContext, StoredFile], Awaitable[bool]]
_access_checks: dict[str, AccessCheck] = {}


def register_access(purpose: str, check: AccessCheck) -> None:
    """Called once by each owning module at import time."""
    _access_checks[purpose] = check


async def read_limited(upload: UploadFile) -> bytes:
    """At most one byte more than the limit, so an oversized file is refused cheaply."""
    return await upload.read(max_bytes() + 1)


async def store_upload(
    db: Db,
    *,
    upload: UploadFile,
    institute_id: uuid.UUID,
    purpose: str,
    user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
) -> StoredFile:
    """Validate, clean and store one upload, and stage its record.

    The bytes reach storage *before* the unit of work commits. If the request then fails,
    an object is left in the bucket with no document pointing at it — unreachable, because
    every download starts from the document, and cleaned up by the bucket's lifecycle rule.
    The other order would be worse: a document pointing at bytes that were never written.
    """
    data = await read_limited(upload)
    clean = validate_upload(data, declared_type=upload.content_type, filename=upload.filename)
    key = f"{institute_id}/{purpose}/{uuid.uuid4()}"
    await get_storage().put(key, clean.data, clean.content_type)

    stored = StoredFile(
        institute_id=institute_id,
        uploaded_by=user_id,
        purpose=purpose,  # type: ignore[arg-type]
        content_type=clean.content_type,
        size=len(clean.data),
        sha256=clean.sha256,
        storage_key=key,
        original_name=clean.original_name,
    )
    db.add(stored)
    audit.record(
        db,
        action=events.FILE_UPLOADED,
        actor_user_id=user_id,
        target_type="file",
        target_id=stored.id,
        institute_id=institute_id,
        ip=ip,
        user_agent=user_agent,
        extra={"purpose": purpose, "size": stored.size, "content_type": stored.content_type},
    )
    return stored


async def claim(
    db: Db,
    file_ids: Iterable[uuid.UUID],
    *,
    institute_id: uuid.UUID,
    purpose: str,
    uploaded_by: uuid.UUID | None = None,
) -> list[StoredFile]:
    """Check that files may be attached to something, and mark them attached.

    Every id must be a file of this institute and purpose — and, when ``uploaded_by`` is
    given, one this person uploaded. Without that, a student could attach another student's
    photo to their own submission just by knowing its id.
    """
    wanted = list(dict.fromkeys(file_ids))
    if not wanted:
        return []
    match: dict = {"_id": ids_in(wanted), "institute_id": institute_id, "purpose": purpose}
    if uploaded_by is not None:
        match["uploaded_by"] = uploaded_by
    found = await db.find(StoredFile, match)
    if len(found) != len(wanted):
        raise ValidationFailed("One of those files is not available. Please upload it again.")
    for stored in found:
        stored.status = "attached"
    by_id = {f.id: f for f in found}
    return [by_id[i] for i in wanted]


async def files_by_id(db: Db, file_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, StoredFile]:
    ids = list(file_ids)
    if not ids:
        return {}
    return {f.id: f for f in await db.find(StoredFile, {"_id": ids_in(ids)})}


async def can_read(db: Db, context: AuthContext, stored: StoredFile) -> bool:
    if stored.uploaded_by == context.user_id:
        return True
    check = _access_checks.get(stored.purpose)
    if check is None:
        logger.warning("no access check registered", extra={"purpose": stored.purpose})
        return False
    return await check(db, context, stored)


async def require_readable(db: Db, context: AuthContext, file_id: uuid.UUID) -> StoredFile:
    """404 both when the file does not exist and when it is not the caller's to see."""
    stored = await db.get(StoredFile, file_id)
    if stored is None or not await can_read(db, context, stored):
        raise NotFound("That file does not exist.")
    return stored


async def download_url(stored: StoredFile) -> str | None:
    return await get_storage().signed_url(
        stored.storage_key,
        ttl_seconds=settings.signed_url_ttl_seconds,
        filename=stored.original_name,
    )
