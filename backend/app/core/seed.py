"""Idempotent seed, run as the Render pre-deploy command after ``alembic upgrade head``.

It must be safe to run on **every** deploy: insert what is missing, update what changed,
delete nothing. A seed that is only safe the first time is a seed that will one day wipe
production.

What it writes:

* the module, permission and role catalogue from ``app.modules.rbac.catalog`` (PRD §5.3)
* the built-in "Direct" institute that holds self-registered learners (PRD §2)
* the first Super Admin, from ``SEED_SUPERADMIN_EMAIL``

Run locally: ``python -m app.core.seed``
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.core.logging import configure_logging
from app.modules.org.models import Institute
from app.modules.rbac import catalog
from app.modules.rbac.models import (
    InstituteModule,
    Module,
    Permission,
    Role,
    RolePermission,
    UserRoleAssignment,
)
from app.modules.users.models import User, UserPreference

logger = logging.getLogger(__name__)


async def _seed_modules(db: AsyncSession) -> None:
    existing = {m.key: m for m in (await db.execute(select(Module))).scalars()}
    if catalog.CORE_MODULE not in existing:
        db.add(
            Module(
                key=catalog.CORE_MODULE,
                name="Core platform",
                description="Authentication, organisation, users and permissions.",
                is_core=True,
            )
        )


async def _seed_permissions(db: AsyncSession) -> dict[str, Permission]:
    existing = {p.key: p for p in (await db.execute(select(Permission))).scalars()}
    for definition in catalog.PERMISSIONS:
        current = existing.get(definition.key)
        if current is None:
            created = Permission(
                key=definition.key,
                module_key=definition.module_key,
                description=definition.description,
            )
            db.add(created)
            existing[definition.key] = created
        else:
            # Descriptions are allowed to improve between releases.
            current.description = definition.description
            current.module_key = definition.module_key
    await db.flush()
    return existing


async def _seed_roles(db: AsyncSession) -> dict[str, Role]:
    existing = {r.key: r for r in (await db.execute(select(Role))).scalars()}
    for definition in catalog.ROLES:
        current = existing.get(definition.key)
        if current is None:
            created = Role(
                key=definition.key,
                name=definition.name,
                scope_level=definition.scope_level,
                rank=definition.rank,
                is_system=definition.is_system,
                is_active=definition.is_active,
            )
            db.add(created)
            existing[definition.key] = created
        else:
            current.name = definition.name
            current.scope_level = definition.scope_level
            current.rank = definition.rank
            current.is_active = definition.is_active
    await db.flush()
    return existing


async def _seed_role_permissions(
    db: AsyncSession, roles: dict[str, Role], permissions: dict[str, Permission]
) -> None:
    """Reconcile the **built-in** roles to exactly what the catalogue says.

    Rows are added *and removed*: when a permission is taken away from a role in the
    catalogue, leaving the old mapping behind would silently keep granting it.

    Custom roles are deliberately excluded from the reconciliation. They are not
    in the catalogue, so a blanket reconcile would class every one of their permission rows
    as stale and delete them — on every single deploy, silently, taking an institute's own
    roles down to nothing.
    """
    # ``roles`` is every role in the database, so filter on the flag rather than on
    # membership: a custom role is exactly the one whose rows must survive this.
    system_role_ids = {role.id for role in roles.values() if role.is_system}
    current_rows = {
        (row.role_id, row.permission_id)
        for row in (await db.execute(select(RolePermission))).scalars()
        if row.role_id in system_role_ids
    }
    wanted: set[tuple] = set()

    for role_key, permission_keys in catalog.ROLE_PERMISSIONS.items():
        role = roles.get(role_key)
        if role is None:
            continue
        for permission_key in permission_keys:
            permission = permissions.get(permission_key)
            if permission is None:
                logger.warning(
                    "catalogue names an unknown permission", extra={"key": permission_key}
                )
                continue
            wanted.add((role.id, permission.id))

    for role_id, permission_id in wanted - current_rows:
        db.add(RolePermission(role_id=role_id, permission_id=permission_id))

    stale = current_rows - wanted
    if stale:
        from sqlalchemy import and_, delete, or_

        await db.execute(
            delete(RolePermission).where(
                or_(
                    *[
                        and_(
                            RolePermission.role_id == role_id,
                            RolePermission.permission_id == permission_id,
                        )
                        for role_id, permission_id in stale
                    ]
                )
            )
        )
        logger.info("removed stale role permissions", extra={"count": len(stale)})


async def _seed_direct_institute(db: AsyncSession) -> Institute:
    institute = await db.scalar(
        select(Institute).where(Institute.code == catalog.DIRECT_INSTITUTE_CODE)
    )
    if institute is None:
        institute = Institute(
            name=catalog.DIRECT_INSTITUTE_NAME,
            code=catalog.DIRECT_INSTITUTE_CODE,
            type="academy",
            status="active",
            is_system=True,
        )
        db.add(institute)
        await db.flush()

    enabled = await db.get(InstituteModule, (institute.id, catalog.CORE_MODULE))
    if enabled is None:
        db.add(
            InstituteModule(institute_id=institute.id, module_key=catalog.CORE_MODULE, enabled=True)
        )
    return institute


async def _seed_super_admin(db: AsyncSession, roles: dict[str, Role]) -> None:
    """Create the first Super Admin as an *invited* user with no password.

    No password is ever generated here: a seeded password would end up in a log, a terminal
    history or a deploy output. The real person completes setup through the normal
    forgot-password flow, which proves they control the mailbox.
    """
    email = (settings.seed_superadmin_email or "").strip().lower()
    if not email:
        logger.warning("SEED_SUPERADMIN_EMAIL is not set; no Super Admin was created")
        return

    role = roles.get(catalog.SUPER_ADMIN)
    if role is None:
        logger.error("super_admin role missing; cannot seed the first administrator")
        return

    from sqlalchemy import func

    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        user = User(email=email, full_name="Super Admin", status="invited", password_hash=None)
        db.add(user)
        await db.flush()
        db.add(UserPreference(user_id=user.id))
        logger.info(
            "super admin created; they must set a password via Forgot password",
            extra={"user_id": str(user.id), "email": email},
        )

    existing = await db.scalar(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.role_id == role.id,
            UserRoleAssignment.institute_id.is_(None),
            UserRoleAssignment.revoked_at.is_(None),
        )
    )
    if existing is None:
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        logger.info("super admin role granted")


async def seed() -> None:
    async with SessionLocal() as db:
        await _seed_modules(db)
        await db.flush()
        permissions = await _seed_permissions(db)
        roles = await _seed_roles(db)
        await _seed_role_permissions(db, roles, permissions)
        await _seed_direct_institute(db)
        await _seed_super_admin(db, roles)
        await db.commit()

    logger.info(
        "seed complete",
        extra={"roles": len(catalog.ROLES), "permissions": len(catalog.PERMISSIONS)},
    )


def main() -> None:
    configure_logging()
    asyncio.run(_run())


async def _run() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    main()
