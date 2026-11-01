"""One uploaded file (Phase 3 shared groundwork).

The bytes live in object storage; this document is what the platform knows about them.
A file belongs to an institute and has a *purpose*, which names the module that owns it —
and therefore the module that decides who may download it.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.core.db import TimestampedDocument

FilePurpose = Literal["homework_attachment", "submission", "library"]
FILE_PURPOSES: tuple[str, ...] = ("homework_attachment", "submission", "library")


class StoredFile(TimestampedDocument):
    institute_id: uuid.UUID
    uploaded_by: uuid.UUID
    purpose: FilePurpose
    content_type: str = Field(max_length=60)
    size: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    #: `{institute_id}/{purpose}/{uuid}` — never derived from the user's file name.
    storage_key: str = Field(max_length=200)
    #: Shown back to people and used as the download name. Sanitised on the way in.
    original_name: str = Field(max_length=200)
    #: `uploaded` until a homework, submission or library item references it.
    status: Literal["uploaded", "attached"] = "uploaded"

    class Settings:
        name = "stored_files"
        use_state_management = True
        validate_on_save = True
        indexes = [  # noqa: RUF012
            IndexModel([("storage_key", ASCENDING)], unique=True, name="uq_stored_files_key"),
            IndexModel(
                [("institute_id", ASCENDING), ("purpose", ASCENDING)],
                name="ix_stored_files_institute_purpose",
            ),
            IndexModel([("uploaded_by", ASCENDING)], name="ix_stored_files_uploader"),
        ]
