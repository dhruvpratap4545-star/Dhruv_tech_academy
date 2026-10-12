"""Every collection has the indexes its rules depend on, and the seed is safe to re-run."""

from __future__ import annotations

from pymongo.errors import DuplicateKeyError

from app.core.db import Db, document_models
from app.modules.org.models import Institute
from app.modules.rbac import catalog
from app.modules.rbac.models import Permission, Role, RolePermission


async def test_every_model_has_its_collection_and_indexes(db: Db, seeded) -> None:
    """Catches the classic drift: a model whose uniqueness rule never reached the database.

    MongoDB has no schema to migrate, so the unique indexes *are* the schema's guarantees
    — and Beanie creates them at startup only for models it was told about.
    """
    for model in document_models():
        declared = {index.name for index in model.get_settings().indexes or []}
        present = set(await model.get_pymongo_collection().index_information())
        missing = declared - present
        assert not missing, f"{model.__name__} is missing indexes: {sorted(missing)}"


async def test_email_uniqueness_is_case_insensitive(db: Db, seeded) -> None:
    from app.modules.users.models import User

    db.add(User(email="asha@example.com", full_name="Asha", status="active"))
    await db.commit()

    db.add(User(email="ASHA@example.com", full_name="Impostor", status="active"))
    try:
        await db.commit()
        raise AssertionError("a duplicate email in different case was accepted")
    except DuplicateKeyError:
        await db.rollback()


async def test_seed_writes_the_whole_catalogue(db: Db, seeded) -> None:
    roles = await db.find(Role, {})
    permissions = await db.find(Permission, {})
    assert {r.key for r in roles} == {r.key for r in catalog.ROLES}
    assert {p.key for p in permissions} == {p.key for p in catalog.PERMISSIONS}


async def test_seed_creates_the_direct_institute(db: Db, seeded) -> None:
    direct = await db.find_one(Institute, {"code": catalog.DIRECT_INSTITUTE_CODE})
    assert direct is not None
    assert direct.is_system is True


async def test_parent_role_is_seeded_but_inactive(db: Db, seeded) -> None:
    """PRD §3: designed in M1, not granted until Kids Zone."""
    parent = await db.find_one(Role, {"key": catalog.PARENT})
    assert parent is not None
    assert parent.is_active is False


async def test_seed_is_idempotent(db: Db, seeded) -> None:
    """It runs on every deploy, so a second run must change nothing."""
    from app.core import seed as seed_module

    before = len(await db.find(RolePermission, {}))

    await seed_module._seed_modules(db)
    await db.flush()
    permissions = await seed_module._seed_permissions(db)
    roles = await seed_module._seed_roles(db)
    await db.flush()
    await seed_module._seed_role_permissions(db, roles, permissions)
    await seed_module._seed_direct_institute(db)
    await db.commit()

    after = len(await db.find(RolePermission, {}))
    assert before == after

    institutes = await db.find(Institute, {"code": catalog.DIRECT_INSTITUTE_CODE})
    assert len(institutes) == 1


async def test_super_admin_holds_every_permission(db: Db, seeded) -> None:
    role = await db.find_one(Role, {"key": catalog.SUPER_ADMIN})
    links = await db.find(RolePermission, {"role_id": role.id})
    permissions = await db.find(
        Permission, {"_id": {"$in": [link.permission_id for link in links]}}
    )
    assert {p.key for p in permissions} == {p.key for p in catalog.PERMISSIONS}


async def test_an_audit_row_with_a_real_ip_serialises(db: Db, seeded) -> None:
    """The API test client has no client address, so every audit entry written during
    tests has no ip and this path was never exercised — it once failed only when a real
    browser hit a real server. Writing the address explicitly closes that gap.
    """
    from app.modules.audit.models import AuditLog
    from app.modules.audit.schemas import AuditLogOut

    entry = AuditLog(action="login_success", ip="203.0.113.42")
    db.add(entry)
    await db.commit()

    reloaded = await db.get(AuditLog, entry.id)
    assert reloaded is not None
    rendered = AuditLogOut.model_validate(reloaded)
    assert rendered.ip == "203.0.113.42"


async def test_an_audit_row_without_an_ip_serialises(db: Db, seeded) -> None:
    from app.modules.audit.models import AuditLog
    from app.modules.audit.schemas import AuditLogOut

    entry = AuditLog(action="login_failure")
    db.add(entry)
    await db.commit()
    assert AuditLogOut.model_validate(entry).ip is None
