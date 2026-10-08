"""Cross-cutting HTTP middleware that is not logging or CORS."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.errors import error_body
from app.core.security import CSRF_HEADER, CSRF_HEADER_VALUE, UNSAFE_METHODS


class CsrfHeaderMiddleware(BaseHTTPMiddleware):
    """SameSite=Lax plus a required custom header (PRD §7.5).

    A cross-site form post cannot set ``X-Requested-With``, so requiring it on
    state-changing requests blocks CSRF without a token round-trip.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        needs_check = request.method in UNSAFE_METHODS and not request.url.path.startswith(
            "/healthz"
        )
        if needs_check and request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
            return JSONResponse(
                status_code=403,
                content=error_body("CSRF_HEADER_MISSING", "Request blocked. Please reload."),
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline response headers (PRD §7.5). The CSP lives on the frontend."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
