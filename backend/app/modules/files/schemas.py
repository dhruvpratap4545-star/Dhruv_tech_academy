"""File metadata as the API returns it. Never the storage key."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_name: str
    content_type: str
    size: int
    created_at: datetime
