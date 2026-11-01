"""``GET /files/{id}`` — the one way any uploaded file is downloaded."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse

from app.core.storage import get_storage
from app.modules.files import service
from app.modules.rbac.deps import AuthContextDep, DbSession

router = APIRouter()


@router.get(
    "/{file_id}",
    summary="Download a file you are allowed to see",
    description="Redirects to a short-lived signed link in production; streams the file "
    "in development. 404 when the file does not exist or is not yours to see.",
    responses={302: {"description": "Signed download link"}},
)
async def download(file_id: uuid.UUID, db: DbSession, context: AuthContextDep) -> Response:
    stored = await service.require_readable(db, context, file_id)
    url = await service.download_url(stored)
    if url is not None:
        return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    data = await get_storage().open(stored.storage_key)
    return Response(
        content=data,
        media_type=stored.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{stored.original_name}"',
            "Cache-Control": "private, no-store",
            # A PDF opened inline on our own origin must not be able to run script there.
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
