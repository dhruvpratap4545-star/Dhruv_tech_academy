"""Per-institute module switches (Phase 3 shared groundwork, gap 1).

The permission engine has gated non-core modules since Milestone 1; what was missing was a
way to flip the switch. These tests cover the endpoints *and* that flipping one changes what
the engine allows on the very next request.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.core.db import Db
from app.modules.audit.models import AuditLog
from app.modules.rbac.models import InstituteModule


async def _as(client: AsyncClient, user) -> AsyncClient:
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Jacaranda!Tide4"}
    )
    assert response.status_code == 200, response.text
    return client


async def test_lists_every_optional_module_switched_off_by_default(
    client: AsyncClient, institute, make_user
) -> None:
    abc, _ = await institute("ABC College", "ABC")
    admin = await make_user("institute_admin", institute_id=abc.id)
    await _as(client, admin)

    response = await client.get(f"/api/v1/institutes/{abc.id}/modules")

    assert response.status_code == 200, response.text
    body = {m["key"]: m["enabled"] for m in response.json()}
    assert body == {"ai": False, "homework": False, "library": False}


async def test_platform_admin_enables_a_module_and_it_is_audited(
    client: AsyncClient, db: Db, institute, make_user
) -> None:
    abc, _ = await institute("ABC College", "ABC")
    await _as(client, await make_user("platform_admin"))

    response = await client.put(
        f"/api/v1/institutes/{abc.id}/modules/homework", json={"enabled": True}
    )

    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is True
    row = await db.find_one(InstituteModule, {"institute_id": abc.id, "module_key": "homework"})
    assert row is not None and row.enabled is True
    entry = await db.find_one(AuditLog, {"action": "module_enabled"})
    assert entry is not None and entry.extra == {"module_key": "homework"}


async def test_disabling_is_recorded_and_repeating_a_switch_writes_no_new_audit_row(
    client: AsyncClient, db: Db, institute, make_user
) -> None:
    abc, _ = await institute("ABC College", "ABC")
    await _as(client, await make_user("super_admin"))
    url = f"/api/v1/institutes/{abc.id}/modules/library"

    await client.put(url, json={"enabled": True})
    await client.put(url, json={"enabled": False})
    await client.put(url, json={"enabled": False})

    assert await db.count(AuditLog, {"action": "module_enabled"}) == 1
    assert await db.count(AuditLog, {"action": "module_disabled"}) == 1


async def test_an_institute_admin_cannot_switch_their_own_modules(
    client: AsyncClient, institute, make_user
) -> None:
    abc, _ = await institute("ABC College", "ABC")
    await _as(client, await make_user("institute_admin", institute_id=abc.id))

    response = await client.put(f"/api/v1/institutes/{abc.id}/modules/ai", json={"enabled": True})

    assert response.status_code == 403


async def test_core_cannot_be_switched_and_unknown_modules_are_404(
    client: AsyncClient, institute, make_user
) -> None:
    abc, _ = await institute("ABC College", "ABC")
    await _as(client, await make_user("super_admin"))

    core = await client.put(f"/api/v1/institutes/{abc.id}/modules/core", json={"enabled": False})
    unknown = await client.put(
        f"/api/v1/institutes/{abc.id}/modules/wallet", json={"enabled": True}
    )

    assert core.status_code == 422
    assert unknown.status_code == 404


async def test_another_institutes_modules_are_not_visible(
    client: AsyncClient, institute, make_user
) -> None:
    abc, _ = await institute("ABC College", "ABC")
    xyz, _ = await institute("XYZ College", "XYZ")
    await _as(client, await make_user("institute_admin", institute_id=abc.id))

    response = await client.get(f"/api/v1/institutes/{xyz.id}/modules")

    assert response.status_code == 404


async def test_the_engine_honours_the_switch_on_the_next_request(
    client: AsyncClient, institute, make_user
) -> None:
    """A disabled module's permission is refused even though the role holds it."""
    abc, _ = await institute("ABC College", "ABC")
    platform = await make_user("platform_admin")
    admin = await make_user("institute_admin", institute_id=abc.id)

    await _as(client, admin)
    before = await client.get(f"/api/v1/homework?institute_id={abc.id}")

    await _as(client, platform)
    await client.put(f"/api/v1/institutes/{abc.id}/modules/homework", json={"enabled": True})

    await _as(client, admin)
    after = await client.get(f"/api/v1/homework?institute_id={abc.id}")

    assert before.status_code == 403
    assert after.status_code == 200, after.text
