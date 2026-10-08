"""FastAPI application factory.

Middleware order is deliberate and runs outermost first:

    CORS  →  request id / logging  →  security headers  →  CSRF header  →  rate limit

CORS is outermost so *every* response carries its headers, including errors — otherwise a
500 reaches the browser as an unexplained CORS failure. Logging sits just inside it, so a
failure is traced and answered rather than escaping to Starlette's own error middleware.
CORS also has to answer preflight ``OPTIONS`` before the CSRF check would reject it. Rate
limiting is innermost, where the authenticated user is known and can be used as the key.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.core.config import settings
from app.core.errors import (
    AppError,
    app_error_handler,
    error_body,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import REQUEST_ID_HEADER, RequestContextMiddleware, configure_logging
from app.core.middleware import CsrfHeaderMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import limiter
from app.core.security import CSRF_HEADER
from app.core.spa import SinglePageApp

logger = logging.getLogger(__name__)


def _verify_signing_keys() -> None:
    """Prove the ES256 key pair works before accepting traffic.

    A malformed or mismatched key otherwise stays invisible until the first login, which
    means a bad deploy looks healthy — `/healthz` passes, and only real users find the 500.
    Signing and verifying one throwaway token at boot turns that into a failed deploy,
    which is what Render's health check is for.
    """
    if settings.environment == "test":
        return
    import uuid as _uuid

    from app.modules.auth.tokens import create_access_token, decode_access_token

    if not settings.jwt_private_key.get_secret_value() or not settings.jwt_public_key:
        raise RuntimeError(
            "JWT_PRIVATE_KEY and JWT_PUBLIC_KEY must be set. Generate an ES256 pair as "
            "described in backend/.env.example."
        )
    probe_user, probe_session = _uuid.uuid4(), _uuid.uuid4()
    claims = decode_access_token(create_access_token(probe_user, probe_session))
    if claims.user_id != probe_user or claims.session_id != probe_session:
        raise RuntimeError("The JWT key pair does not round-trip; check that they match.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    _verify_signing_keys()
    _init_monitoring()
    logger.info(
        "api starting",
        extra={"environment": settings.environment, "rate_limits": settings.rate_limits_enabled},
    )
    yield
    # Close pooled database connections so a rolling deploy does not leave sockets behind.
    from app.core.db import engine

    await engine.dispose()
    logger.info("api stopping")


def _init_monitoring() -> None:
    """Sentry is optional: absent DSN means it is simply not installed."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            # Personal data must not leave the platform (PRD §11).
            send_default_pii=False,
            traces_sample_rate=0.1,
        )
        logger.info("sentry enabled")
    except Exception:
        logger.exception("sentry init failed")


async def rate_limit_handler(_: Request, exc: Exception):
    from fastapi.responses import JSONResponse

    assert isinstance(exc, RateLimitExceeded)
    return JSONResponse(
        status_code=429,
        content=error_body("RATE_LIMITED", "Too many requests. Please try again shortly."),
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        # The schema is public in local and staging only; production keeps the surface quiet.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # `add_middleware` prepends, so the LAST one added is the outermost. CORS goes last
    # on purpose: a response that never reaches it — an error, a rate-limit rejection —
    # arrives at the browser as an opaque CORS failure rather than its real status.
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(CsrfHeaderMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", CSRF_HEADER, REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/healthz", tags=["ops"], summary="Health check used by Render")
    async def healthz() -> dict[str, str]:
        # Deliberately does not touch the database: a slow query must not take the service
        # out of rotation and trigger a restart loop. Use /healthz/db for a deep check.
        return {"status": "ok", "environment": settings.environment, "version": app.version}

    @app.get(
        "/healthz/db",
        tags=["ops"],
        summary="Deep health check",
        description="Verifies the database is reachable. Not used as Render's health check.",
    )
    async def healthz_db() -> dict[str, str]:
        from sqlalchemy import text

        from app.core.db import SessionLocal

        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}

    # Last, so every route above wins and only what is left falls through to the web app.
    if settings.frontend_dist_dir:
        app.mount(
            "/",
            SinglePageApp(settings.frontend_dist_dir, (settings.api_v1_prefix, "/healthz")),
            name="web",
        )

    return app


app = create_app()
