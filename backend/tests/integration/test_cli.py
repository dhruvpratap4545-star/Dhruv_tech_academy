"""The administrative commands that have no screen in the web app.

Appointing a Super Admin is deliberately impossible through the API — every role stops one
rank below its own, Super Admin included. That makes `app.cli` the only remaining route to
a second platform owner, so it has to be tested as carefully as any endpoint: an escape
hatch nobody exercises is an escape hatch that has quietly rusted shut by the time it is
needed.

The commands open their own session through `app.cli.SessionLocal`, which points at the
real `DATABASE_URL`. Each test substitutes the fixture's transaction-bound session, so the
command writes into the same rolled-back transaction as everything else.
"""

from __future__ import annotations

import contextlib

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.modules.rbac.catalog import SUPER_ADMIN
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.users.models import User

pytestmark = pytest.mark.asyncio


@pytest.fixture
def run_command(db: AsyncSession, seeded: AsyncSession, monkeypatch):
    """Point the command's session factory at the test transaction.

    `commit()` is neutralised rather than redirected: the command commits on purpose, and
    a real commit here would end the fixture's transaction and leak every row into the
    database for the next test to trip over. Flushing keeps the writes visible to the
    assertions that follow without making them permanent.
    """

    @contextlib.asynccontextmanager
    async def _session():
        yield db

    async def _flush_only() -> None:
        await db.flush()

    monkeypatch.setattr(cli, "SessionLocal", _session)
    monkeypatch.setattr(db, "commit", _flush_only)
    return None


async def _holders(db: AsyncSession) -> set[str]:
    role = await db.scalar(select(Role).where(Role.key == SUPER_ADMIN))
    rows = (
        await db.execute(
            select(User.email)
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .where(
                UserRoleAssignment.role_id == role.id,
                UserRoleAssignment.revoked_at.is_(None),
            )
        )
    ).scalars()
    return set(rows)


async def test_an_existing_account_can_be_promoted_to_super_admin(db, run_command, make_user):
    """The succession path the web app no longer offers."""
    successor = await make_user("institute_admin")

    await cli.grant(successor.email, create_missing=False)

    assert successor.email in await _holders(db)


async def test_a_brand_new_address_needs_create(db, run_command):
    """A typo in an email must not silently mint a platform owner nobody expected."""
    with pytest.raises(SystemExit, match="Re-run with --create"):
        await cli.grant("nobody@example.com", create_missing=False)

    assert "nobody@example.com" not in await _holders(db)


async def test_create_invites_without_setting_a_password(db, run_command):
    """No password is generated here: one produced by a command ends up in shell history
    or a deploy log, and an account created that way is owned by whoever reads it."""
    await cli.grant("founder@example.com", create_missing=True)

    person = await db.scalar(select(User).where(User.email == "founder@example.com"))
    assert person is not None
    assert person.password_hash is None
    assert person.status == "invited"
    assert "founder@example.com" in await _holders(db)


async def test_granting_twice_changes_nothing(db, run_command, make_user):
    """Deploy scripts get re-run. A second grant must not create a duplicate assignment."""
    successor = await make_user("institute_admin")
    await cli.grant(successor.email, create_missing=False)
    await cli.grant(successor.email, create_missing=False)

    role = await db.scalar(select(Role).where(Role.key == SUPER_ADMIN))
    rows = (
        await db.execute(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == successor.id,
                UserRoleAssignment.role_id == role.id,
                UserRoleAssignment.revoked_at.is_(None),
            )
        )
    ).scalars()
    assert len(list(rows)) == 1


async def test_a_deleted_account_cannot_be_granted(db, run_command, make_user):
    successor = await make_user("institute_admin")
    successor.status = "deleted"
    await db.flush()

    with pytest.raises(SystemExit, match="deleted"):
        await cli.grant(successor.email, create_missing=False)


async def test_the_only_super_admin_cannot_be_removed(db, run_command, make_user):
    """The same rule the API enforces. A command run at 2am must not be the thing that
    leaves the platform with nobody able to administer it."""
    owner = await make_user("super_admin")
    assert await _holders(db) == {owner.email}

    with pytest.raises(SystemExit, match="only Super Admin"):
        await cli.revoke(owner.email)

    assert owner.email in await _holders(db)


async def test_one_of_two_super_admins_can_be_removed(db, run_command, make_user):
    owner = await make_user("super_admin")
    successor = await make_user("institute_admin")
    await cli.grant(successor.email, create_missing=False)

    await cli.revoke(owner.email)

    assert await _holders(db) == {successor.email}


async def test_revoking_from_someone_who_does_not_hold_it_is_an_error(db, run_command, make_user):
    ordinary = await make_user("institute_admin")
    with pytest.raises(SystemExit, match="does not hold"):
        await cli.revoke(ordinary.email)


async def test_email_matching_ignores_case_and_padding(db, run_command, make_user):
    """Addresses get pasted out of emails with capitals and a trailing space attached."""
    successor = await make_user("institute_admin")
    await cli.grant(f"  {successor.email.upper()}  ", create_missing=False)
    assert successor.email in await _holders(db)
