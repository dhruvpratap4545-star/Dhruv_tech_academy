"""The global search endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.modules.rbac.deps import AuthContextDep, DbSession
from app.modules.search import schemas
from app.modules.search import service as search

router = APIRouter()


@router.get(
    "",
    response_model=schemas.SearchResults,
    summary="Search people, institutes, branches and classes",
    description="Returns only what the caller is already entitled to see. Groups the "
    "caller has no permission for are absent rather than empty — an empty group would "
    "itself be a statement about what exists.",
)
async def global_search(
    db: DbSession,
    context: AuthContextDep,
    q: Annotated[str, Query(min_length=1, max_length=120, description="What to look for.")],
) -> schemas.SearchResults:
    return await search.search(db, context=context, term=q)
