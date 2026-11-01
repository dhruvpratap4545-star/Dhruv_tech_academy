"""Pure rules for the Content Library: codes, paths and links. No database, no I/O."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qs, urlparse

from app.core.errors import ValidationFailed
from app.modules.library.models import KIND_ORDER

_NON_CODE: Final = re.compile(r"[^a-z0-9]+")
_YOUTUBE_ID: Final = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VIMEO_ID: Final = re.compile(r"^\d{6,12}$")
_YOUTUBE_HOSTS: Final = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com"}
_VIMEO_HOSTS: Final = {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}


def slugify(name: str, *, max_length: int = 80) -> str:
    """``"Light – Reflection and Refraction"`` → ``"light-reflection-and-refraction"``.

    Accents are folded first, so a Hindi-medium school typing "Électricité" still gets a
    stable code. A name with no Latin letters at all (all Devanagari) falls back to a
    hash-free placeholder the caller must replace with an explicit code.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    code = _NON_CODE.sub("-", folded.lower()).strip("-")
    return code[:max_length].strip("-")


def normalise_code(code: str) -> str:
    value = slugify(code)
    if not value:
        raise ValidationFailed("A code needs at least one letter or number (a-z, 0-9).")
    return value


def child_path(parent_path: str | None, code: str) -> str:
    return f"{parent_path}/{code}" if parent_path else code


def check_kind(parent_kind: str | None, kind: str) -> None:
    """A track is always a root; anything else sits strictly deeper than its parent."""
    if parent_kind is None:
        if kind != "track":
            raise ValidationFailed("A top-level node must be a track.")
        return
    if kind == "track":
        raise ValidationFailed("A track cannot sit inside another node.")
    if KIND_ORDER.index(kind) <= KIND_ORDER.index(parent_kind):
        raise ValidationFailed(f"A {kind} cannot sit inside a {parent_kind}.")


@dataclass(frozen=True, slots=True)
class Video:
    provider: str
    video_id: str
    url: str


def parse_video_url(raw: str) -> Video:
    """Accept only https YouTube or Vimeo links, normalised to the provider's video id.

    The id is what the 3B YouTube picker and an embed need; storing a canonical watch URL
    rather than whatever was pasted (``youtu.be``, ``&t=40s``, ``?si=…`` tracking) means two
    teachers linking the same video produce the same record.
    """
    try:
        parsed = urlparse(raw.strip())
    except ValueError as exc:
        raise ValidationFailed("That is not a valid video link.") from exc
    if parsed.scheme != "https":
        raise ValidationFailed("Video links must start with https://.")
    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]

    if host in _YOUTUBE_HOSTS or host == "youtu.be":
        candidate = None
        if host == "youtu.be" and parts:
            candidate = parts[0]
        elif parts[:1] == ["watch"]:
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        elif len(parts) >= 2 and parts[0] in ("embed", "shorts", "live", "v"):
            candidate = parts[1]
        if candidate and _YOUTUBE_ID.match(candidate):
            return Video("youtube", candidate, f"https://www.youtube.com/watch?v={candidate}")
        raise ValidationFailed("That YouTube link does not point to a video.")

    if host in _VIMEO_HOSTS:
        candidate = next((p for p in reversed(parts) if _VIMEO_ID.match(p)), None)
        if candidate:
            return Video("vimeo", candidate, f"https://vimeo.com/{candidate}")
        raise ValidationFailed("That Vimeo link does not point to a video.")

    raise ValidationFailed("Video links must be from YouTube or Vimeo.")


def check_https_link(raw: str) -> str:
    url = raw.strip()
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValidationFailed("That is not a valid link.") from exc
    if parsed.scheme != "https" or not parsed.hostname or "." not in parsed.hostname:
        raise ValidationFailed("Links must be full https:// addresses.")
    if parsed.username or parsed.password:
        raise ValidationFailed("Links must not contain a username or password.")
    return url
