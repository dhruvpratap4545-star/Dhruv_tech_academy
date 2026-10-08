"""Smoke tests for the application shell: health check, error shape, security headers."""

from httpx import AsyncClient

from app.core.security import CSRF_HEADER


async def test_healthz_reports_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_response_carries_request_id_and_security_headers(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_unknown_route_uses_the_standard_error_shape(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_unsafe_request_without_csrf_header_is_blocked(client: AsyncClient) -> None:
    response = await client.post("/api/v1/does-not-exist", headers={CSRF_HEADER: ""})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_HEADER_MISSING"
