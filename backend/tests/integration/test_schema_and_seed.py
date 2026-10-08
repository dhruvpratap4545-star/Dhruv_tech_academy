"""The migration builds the schema the models expect, and the seed is safe to re-run."""

from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base
from app.modules.org.models import Institute
from app.modules.rbac import catalog
from app.modules.rbac.models import Permission, Role, RolePermission


async def test_migration_creates_every_model_table(db_connection) -> None:
    """Catches the classic drift: a model added without a migration."""
    tables = await db_connection.run_sync(lambda c: set(inspect(c).get_table_names()))
    missing = set(Base.metadata.tables) - tables
    assert not missing, f"tables missing from the migration: {sorted(missing)}"


async def test_uuid_generation_works_server_side(db_connection) -> None:
    value = (await db_connection.execute(text("SELECT gen_random_uuid()"))).scalar()
    assert value is not None


async def test_email_uniqueness_is_case_insensitive(db: AsyncSession, seeded) -> None:
    from sqlalchemy.exc import IntegrityError

    from app.modules.users.models import User

    db.add(User(email="asha@example.com", full_name="Asha", status="active"))
    await db.commit()

    db.add(User(email="ASHA@example.com", full_name="Impostor", status="active"))
    try:
        await db.commit()
        raise AssertionError("a duplicate email in different case was accepted")
    except IntegrityError:
        await db.rollback()


async def test_seed_writes_the_whole_catalogue(db: AsyncSession, seeded) -> None:
    roles = (await db.execute(select(Role))).scalars().all()
    permissions = (await db.execute(select(Permission))).scalars().all()
    assert {r.key for r in roles} == {r.key for r in catalog.ROLES}
    assert {p.key for p in permissions} == {p.key for p in catalog.PERMISSIONS}


async def test_seed_creates_the_direct_institute(db: AsyncSession, seeded) -> None:
    direct = await db.scalar(
        select(Institute).where(Institute.code == catalog.DIRECT_INSTITUTE_CODE)
    )
    assert direct is not None
    assert direct.is_system is True


async def test_parent_role_is_seeded_but_inactive(db: AsyncSession, seeded) -> None:
    """PRD §3: designed in M1, not granted until Kids Zone."""
    parent = await db.scalar(select(Role).where(Role.key == catalog.PARENT))
    assert parent is not None
    assert parent.is_active is False


async def test_seed_is_idempotent(db: AsyncSession, seeded) -> None:
    """It runs on every deploy, so a second run must change nothing."""
    from app.core import seed as seed_module

    before = len((await db.execute(select(RolePermission))).scalars().all())

    await seed_module._seed_modules(db)
    await db.flush()
    permissions = await seed_module._seed_permissions(db)
    roles = await seed_module._seed_roles(db)
    await seed_module._seed_role_permissions(db, roles, permissions)
    await seed_module._seed_direct_institute(db)
    await db.commit()

    after = len((await db.execute(select(RolePermission))).scalars().all())
    assert before == after

    institutes = (
        (await db.execute(select(Institute).where(Institute.code == catalog.DIRECT_INSTITUTE_CODE)))
        .scalars()
        .all()
    )
    assert len(institutes) == 1


async def test_super_admin_holds_every_permission(db: AsyncSession, seeded) -> None:
    rows = await db.execute(
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.key == catalog.SUPER_ADMIN)
    )
    assert set(rows.scalars()) == {p.key for p in catalog.PERMISSIONS}


async def test_an_audit_row_with_a_real_ip_serialises(db: AsyncSession, seeded) -> None:
    """PostgreSQL INET returns an IPv4Address object, which Pydantic will not coerce.

    The API test client has no client address, so every audit row written during tests has
    ip = NULL and this path was never exercised — it only failed once a real browser hit a
    real server. Writing the address explicitly closes that gap.
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


async def test_an_audit_row_without_an_ip_serialises(db: AsyncSession, seeded) -> None:
    from app.modules.audit.models import AuditLog
    from app.modules.audit.schemas import AuditLogOut

    entry = AuditLog(action="login_failure")
    db.add(entry)
    await db.commit()
    assert AuditLogOut.model_validate(entry).ip is None
