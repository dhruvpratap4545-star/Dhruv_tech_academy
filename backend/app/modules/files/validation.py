"""What an upload has to be before it is stored.

Three checks, because each catches what the others miss:

1. **Size.** Read at most one byte past the limit, so a 2 GB upload costs 10 MB of memory
   to refuse rather than 2 GB.
2. **Type, from the bytes.** The browser's declared ``Content-Type`` is whatever the client
   says it is. The first bytes of the file (its *magic number*) are what it actually is, and
   both must agree on one of PDF, JPEG or PNG. An ``.exe`` renamed ``homework.jpg`` fails here.
3. **Images are re-encoded.** Decoding and re-saving with Pillow drops everything that is
   not pixels: EXIF — which on a phone photo includes the GPS position of the child's home —
   and anything appended to the file after the image data. Large photos are scaled to at
   most 2000 px on the long edge, which keeps handwriting legible and storage sane.

PDFs are stored as they are: rewriting them safely needs a heavyweight library, and they are
served as downloads from a separate origin (a signed bucket URL), never rendered on ours.

Nothing here touches the database. Bytes in, bytes out, or ``ValidationFailed``.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Final

from app.core.config import settings
from app.core.errors import ValidationFailed

PDF: Final = "application/pdf"
JPEG: Final = "image/jpeg"
PNG: Final = "image/png"
ALLOWED_TYPES: Final = (PDF, JPEG, PNG)

#: Longest edge after re-encoding.
MAX_IMAGE_EDGE: Final = 2000
#: Pillow's decompression-bomb guard, stated explicitly: a 40-megapixel phone photo is
#: fine, a crafted 1-kilobyte PNG that decodes to fifty gigapixels is not.
MAX_IMAGE_PIXELS: Final = 60_000_000

_EXTENSIONS: Final = {PDF: ".pdf", JPEG: ".jpg", PNG: ".png"}
#: Browsers send a few spellings for the same thing.
_DECLARED_ALIASES: Final = {"image/jpg": JPEG, "image/pjpeg": JPEG, "image/x-png": PNG}


@dataclass(slots=True)
class CleanFile:
    data: bytes
    content_type: str
    sha256: str
    original_name: str


def max_bytes() -> int:
    return settings.max_upload_mb * 1024 * 1024


def sniff(data: bytes) -> str | None:
    """The real type of the file from its first bytes, or ``None`` if it is none of ours."""
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    return None


def safe_name(name: str | None, content_type: str) -> str:
    """A display name with nothing in it that could be a path or a header injection.

    Only used for showing the file back and as the suggested download name — never as a
    storage key.
    """
    base = (name or "file").replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^\w.\- ()]+", "_", base, flags=re.UNICODE).strip(" ._") or "file"
    stem = base.rsplit(".", 1)[0][:120] or "file"
    return f"{stem}{_EXTENSIONS[content_type]}"


def _reencode(data: bytes, content_type: str) -> bytes:
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            # Apply the camera's rotation *before* the EXIF that records it is discarded,
            # or every portrait photo of a notebook arrives sideways.
            image = ImageOps.exif_transpose(image)
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
            out = io.BytesIO()
            if content_type == JPEG:
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image.save(out, format="JPEG", quality=85, optimize=True)
            else:
                image.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationFailed("That image could not be read. Please try another photo.") from exc


def validate_upload(data: bytes, *, declared_type: str | None, filename: str | None) -> CleanFile:
    """Check, clean and hash one upload. ``data`` may be at most one byte over the limit."""
    if not data:
        raise ValidationFailed("That file is empty.")
    if len(data) > max_bytes():
        raise ValidationFailed(f"Files can be at most {settings.max_upload_mb} MB.")

    actual = sniff(data)
    if actual is None:
        raise ValidationFailed("Only PDF, JPG and PNG files can be uploaded.")
    declared = (declared_type or "").split(";", 1)[0].strip().lower()
    declared = _DECLARED_ALIASES.get(declared, declared)
    # An empty or generic declared type is common from mobile browsers; the bytes decide.
    if declared not in ("", "application/octet-stream") and declared != actual:
        raise ValidationFailed("That file's contents do not match its type.")

    cleaned = data if actual == PDF else _reencode(data, actual)
    return CleanFile(
        data=cleaned,
        content_type=actual,
        sha256=hashlib.sha256(cleaned).hexdigest(),
        original_name=safe_name(filename, actual),
    )
