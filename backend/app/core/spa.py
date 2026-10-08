"""Serves the built React app from the API process, so the platform runs on one URL.

Same origin is what makes the auth design work on any host: the SameSite=Lax cookies always
travel, and there is no CORS to configure. On Render's default ``*.onrender.com`` URLs two
separate services would count as different *sites* (``onrender.com`` is a public suffix), and
the browser would silently drop the cookies.

Mounted last, so every API and health route wins. Whatever is left is either a file from
``dist/`` or a client-side route, which gets ``index.html``. Unmatched ``/api`` and
``/healthz`` paths still answer with the standard JSON 404 rather than a page of HTML.
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.types import Receive, Scope, Send

# Inline classic scripts only — `<script type="module" src=…>` is covered by 'self'.
_INLINE_SCRIPT = re.compile(rb"<script>(.*?)</script>", re.DOTALL)

# Vite fingerprints everything under assets/, so a changed file always gets a new name.
_IMMUTABLE = "public, max-age=31536000, immutable"
_SHORT = "public, max-age=3600"
# The shell must never be cached, or a deploy would leave browsers asking for old bundles.
_NO_CACHE = "no-cache"


def build_csp(index_html: bytes) -> str:
    """CSP for the app shell, allowing exactly the inline scripts the shipped page contains.

    Hashing at startup rather than hard-coding means editing the theme script in
    ``index.html`` cannot quietly break it in production.
    """
    hashes = " ".join(
        f"'sha256-{base64.b64encode(hashlib.sha256(body).digest()).decode()}'"
        for body in _INLINE_SCRIPT.findall(index_html)
    )
    script_src = f"script-src 'self' {hashes}".strip()
    return "; ".join(
        [
            "default-src 'self'",
            "connect-src 'self'",
            "img-src 'self' data:",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            script_src,
            "object-src 'none'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    )


class SinglePageApp:
    """ASGI app: static files from ``dist`` with an ``index.html`` fallback."""

    def __init__(self, dist_dir: str | Path, reserved_prefixes: tuple[str, ...]) -> None:
        self.root = Path(dist_dir).resolve()
        index = self.root / "index.html"
        if not index.is_file():
            # Fail the deploy rather than serve an API with no front door.
            raise RuntimeError(f"FRONTEND_DIST_DIR is set but {index} does not exist.")
        self.index = index
        self.csp = build_csp(index.read_bytes())
        self.reserved = reserved_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = self._respond(Request(scope))
        await response(scope, receive, send)

    def _is_reserved(self, path: str) -> bool:
        return any(path == p or path.startswith(f"{p}/") for p in self.reserved)

    def _respond(self, request: Request) -> Response:
        path = request.url.path
        if request.method not in ("GET", "HEAD") or self._is_reserved(path):
            raise StarletteHTTPException(status_code=404)

        relative = path.lstrip("/")
        if relative:
            candidate = (self.root / relative).resolve()
            # resolve() collapses `..`, so this also rejects path traversal.
            if candidate.is_relative_to(self.root) and candidate.is_file():
                cache = _IMMUTABLE if relative.startswith("assets/") else _SHORT
                return FileResponse(candidate, headers={"Cache-Control": cache})
            # A missing bundle must be a 404, not HTML the browser tries to run as JS.
            if relative.startswith("assets/"):
                raise StarletteHTTPException(status_code=404)

        return FileResponse(
            self.index,
            media_type="text/html",
            headers={"Cache-Control": _NO_CACHE, "Content-Security-Policy": self.csp},
        )
