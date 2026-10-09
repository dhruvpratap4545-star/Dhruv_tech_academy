"""Domain errors and their HTTP representation.

Services raise these; ``app.main`` installs handlers that render them as
``{"error": {"code": ..., "message": ...}}`` (PRD §8). Messages are safe to show
to a user: never put SQL, stack traces or another tenant's data in them.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"
    default_message = "Something went wrong."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"
    default_message = "Some of the details you entered are not valid."


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    default_message = "Please log in to continue."


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"
    default_message = "You do not have permission to do this."


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"
    default_message = "We could not find what you asked for."


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"
    default_message = "This conflicts with something that already exists."


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    default_message = "Too many attempts. Please try again later."


def error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))


async def http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = {
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "RATE_LIMITED",
    }.get(exc.status_code, "BAD_REQUEST")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(exc.detail)),
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Pydantic errors, flattened to field names only — request bodies are never echoed back."""
    assert isinstance(exc, RequestValidationError)
    errors = exc.errors()

    # A validator that wrote a real sentence gets to keep it.
    #
    # Pydantic wraps a `ValueError` raised in a field validator as `value_error`, and the
    # default response here replaces it with "Please check these fields: password." — which
    # throws away "Password needs one special character." and leaves the person guessing.
    # Only `value_error` messages are passed through: those are ours, written for a reader.
    # Type and shape errors stay hidden, because they describe the request body and echoing
    # it back is how a validation message becomes a reflection vector.
    authored = [
        str(e.get("msg", "")).removeprefix("Value error, ")
        for e in errors
        if e.get("type") == "value_error" and e.get("msg")
    ]
    if authored:
        return JSONResponse(status_code=422, content=error_body("VALIDATION_FAILED", authored[0]))

    fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in errors})
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_FAILED",
            f"Please check these fields: {', '.join(fields)}.",
        ),
    )


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Last resort: the exception is logged with the request id.

    The client never sees anything internal.
    """
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "Something went wrong. Please try again."),
    )
