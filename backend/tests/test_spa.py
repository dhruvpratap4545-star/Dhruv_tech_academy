"""The API serving the built web app on the same URL (single-service deploy)."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import CSRF_HEADER, CSRF_HEADER_VALUE
from app.core.spa import SinglePageApp, build_csp
from app.main import create_app

THEME_SCRIPT = b"document.documentElement.classList.add('dark');"
INDEX_HTML = b"<!doctype html><html><head><script>" + THEME_SCRIPT + b"</script></head></html>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_bytes(INDEX_HTML)
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app');")
    (tmp_path / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    (tmp_path.parent / "secret.txt").write_text("outside dist")
    return tmp_path


@pytest.fixture
async def web(dist: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient]:
    monkeypatch.setattr(settings, "frontend_dist_dir", str(dist))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
        headers={CSRF_HEADER: CSRF_HEADER_VALUE},
    ) as ac:
        yield ac


async def test_root_serves_the_app_shell_uncached_with_csp(web: AsyncClient) -> None:
    response = await web.get("/")
    assert response.status_code == 200
    assert response.content == INDEX_HTML
    assert response.headers["Cache-Control"] == "no-cache"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_client_side_route_falls_back_to_index(web: AsyncClient) -> None:
    response = await web.get("/dashboard/users/42")
    assert response.status_code == 200
    assert response.content == INDEX_HTML


async def test_fingerprinted_asset_is_cached_forever(web: AsyncClient) -> None:
    response = await web.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["Cache-Control"]


async def test_top_level_public_file_is_served(web: AsyncClient) -> None:
    response = await web.get("/favicon.ico")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=3600"


async def test_missing_asset_is_404_not_html(web: AsyncClient) -> None:
    response = await web.get("/assets/index-gone.js")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_unknown_api_route_keeps_the_json_404(web: AsyncClient) -> None:
    for path in ("/api/v1/does-not-exist", "/healthz/nope"):
        response = await web.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_api_and_health_routes_still_win(web: AsyncClient) -> None:
    response = await web.get("/healthz")
    assert response.json()["status"] == "ok"


async def test_non_get_to_web_path_is_404(web: AsyncClient) -> None:
    response = await web.post("/dashboard")
    assert response.status_code == 404


async def test_path_traversal_is_not_served(web: AsyncClient) -> None:
    response = await web.get("/%2e%2e/secret.txt")
    assert b"outside dist" not in response.content


def test_csp_allows_exactly_the_inline_script() -> None:
    digest = base64.b64encode(hashlib.sha256(THEME_SCRIPT).digest()).decode()
    csp = build_csp(INDEX_HTML)
    assert f"script-src 'self' 'sha256-{digest}'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]


def test_csp_covers_the_real_index_html() -> None:
    """The shipped page against the CSP it will be served with.

    A blocked font or script fails silently in production only, so check here that every
    external origin index.html loads from is allowed. Line endings are normalised to LF,
    as Render checks the file out, so a Windows working copy hashes the deployed bytes.
    """
    index = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
    html = index.read_bytes().replace(b"\r\n", b"\n")
    csp = build_csp(html)
    for origin in set(re.findall(rb"https://[a-z0-9.-]+", html)):
        assert origin.decode() in csp, f"index.html loads from {origin!r}; the CSP must allow it"
    assert csp.count("'sha256-") == 1, "index.html should carry exactly one inline script"
    for directive in ("frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'"):
        assert directive in csp


def test_missing_build_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="does not exist"):
        SinglePageApp(tmp_path, ("/api/v1",))
