"""Shapes for the global search box."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class SearchHit(BaseModel):
    id: uuid.UUID
    title: str
    subtitle: str | None = None
    # Where clicking this goes. Built server-side so the frontend never has to know which
    # kinds of result are routable and which are not.
    href: str


class SearchGroup(BaseModel):
    kind: str
    label: str
    items: list[SearchHit]


class SearchResults(BaseModel):
    query: str
    groups: list[SearchGroup]
