"""The administrative commands that have no screen in the web app.

Appointing a Super Admin is deliberately impossible through the API — every role stops one
rank below its own, Super Admin included. That makes `app.cli` the only remaining route to
a second platform owner, so it has to be tested as carefully as any endpoint: an escape
hatch nobody exercises is an escape hatch that has quietly rusted shut by the time it is
needed.

The commands open their own unit of work on the database `init_db` already connected —
in tests, the throwaway test database — so they write exactly where the assertions read.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app import cli
from app.core.db import Db
from app.modules.rbac.catalog import SUPER_ADMIN
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.users.models import User

pytestmark = pytest.mark.asyncio


@pytest.fixture
def run_command(db: Db, seeded: Db):
    """The catalogue the commands depend on. Nothing to redirect: `init_db()` inside the
    command reuses the connection the test session opened."""
    return None


async def _holders(db: Db) -> set[str]:
    role = await db.find_one(Role, {"key": SUPER_ADMIN})
    holders = await db.distinct(
        UserRoleAssignment, "user_id", {"role_id": role.id, "revoked_at": None}
    )
    return {u.email for u in await db.find(User, {"_id": {"$in": holders}})}


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

    person = await db.find_one(User, {"email": "founder@example.com"})
    assert person is not None
    assert person.password_hash is None
    assert person.status == "invited"
    assert "founder@example.com" in await _holders(db)


async def test_granting_twice_changes_nothing(db, run_command, make_user):
    """Deploy scripts get re-run. A second grant must not create a duplicate assignment."""
    successor = await make_user("institute_admin")
    await cli.grant(successor.email, create_missing=False)
    await cli.grant(successor.email, create_missing=False)

    role = await db.find_one(Role, {"key": SUPER_ADMIN})
    rows = await db.find(
        UserRoleAssignment, {"user_id": successor.id, "role_id": role.id, "revoked_at": None}
    )
    assert len(rows) == 1


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


async def test_an_invited_super_admin_does_not_count_as_a_survivor(db, run_command, make_user):
    """The gap this command could otherwise create for itself.

    Granting the role to an account with no password and then removing it from the only
    working administrator would leave the platform with one Super Admin who cannot sign
    in, cannot use Forgot password, and cannot be re-activated — recoverable only with
    direct SQL. The guard counts holders who can actually sign in, exactly as the API does.
    """
    owner = await make_user("super_admin")
    await cli.grant("ghost@example.com", create_missing=True)
    assert "ghost@example.com" in await _holders(db)

    with pytest.raises(SystemExit, match="only Super Admin who can sign in"):
        await cli.revoke(owner.email)

    assert owner.email in await _holders(db)


async def test_a_suspended_account_cannot_be_given_the_role(db, run_command, make_user):
    """Same gap, approached from the other side: a suspended account cannot sign in or
    reset its password, so counting it as a holder would be counting nobody."""
    target = await make_user("institute_admin")
    target.status = "suspended"
    await db.flush()

    with pytest.raises(SystemExit, match="suspended"):
        await cli.grant(target.email, create_missing=False)


async def test_granting_writes_an_audit_entry(db, run_command, make_user):
    """The web app cannot appoint a Super Admin at all any more, so this is the only route
    — which would make it the only authorization change in the system with no record."""
    from app.modules.audit.models import AuditLog

    successor = await make_user("institute_admin")
    await cli.grant(successor.email, create_missing=False)

    entry = await db.find_one(AuditLog, {"target_id": successor.id, "action": "role_assigned"})
    assert entry is not None, "no audit entry for the most privileged action in the system"
    assert entry.actor_user_id is None, "a shell has no session, so there is no actor"
    assert entry.extra["via"] == "cli"
    assert entry.extra["role_key"] == "super_admin"


async def test_revoking_ends_their_sessions_and_is_recorded(db, run_command, make_user):
    """Revoking a role that the token already carries is only half the job: without ending
    the sessions, the removed account keeps working until its access token expires."""
    from app.modules.audit.models import AuditLog
    from app.modules.auth.models import RefreshToken

    owner = await make_user("super_admin")
    second = await make_user("institute_admin")
    await cli.grant(second.email, create_missing=False)

    db.add(
        RefreshToken(
            user_id=second.id,
            token_hash="a" * 64,
            family_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await db.flush()

    await cli.revoke(second.email)

    live = await db.find(RefreshToken, {"user_id": second.id, "revoked_at": None})
    assert not live, "the removed account still has a live session"

    recorded = await db.find_one(AuditLog, {"target_id": second.id, "action": "role_revoked"})
    assert recorded is not None
    assert owner.email in await _holders(db)


async def test_set_password_lets_an_invited_admin_sign_in(db, run_command, make_user, monkeypatch):
    """The way in when email cannot deliver a code yet.

    The first Super Admin is seeded `invited` with no password, and the only route to one
    is a mailed OTP. Until the mail provider works that route is closed, and the platform
    has nobody who can administer it.
    """
    from app.core.security import verify_password

    person = await make_user("super_admin", status="invited")
    assert person.password_hash is None, "an invited account starts with no password"

    monkeypatch.setenv("ADMIN_PASSWORD", "Chandni#Bridge47")
    await cli.set_password(person.email)

    fresh = await db.find_one(User, {"_id": person.id})
    assert fresh.status == "active", "an invited account cannot log in, password or not"
    assert verify_password("Chandni#Bridge47", fresh.password_hash)
    assert fresh.password_changed_at is not None


async def test_set_password_refuses_a_password_given_as_an_argument(
    db, run_command, make_user, monkeypatch
):
    """Arguments are recorded; a Cloud Run job's execution history keeps them readable."""
    person = await make_user("super_admin")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    with pytest.raises(SystemExit, match="ADMIN_PASSWORD"):
        await cli.set_password(person.email)


async def test_set_password_applies_the_same_strength_rules_as_the_web_app(
    db, run_command, make_user, monkeypatch
):
    """A shell is not a reason to accept a password the sign-up form would reject."""
    person = await make_user("super_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "short")

    with pytest.raises(SystemExit, match="Password needs"):
        await cli.set_password(person.email)

    unchanged = await db.find_one(User, {"_id": person.id})
    assert unchanged.password_hash == person.password_hash


async def test_set_password_ends_existing_sessions(db, run_command, make_user, monkeypatch):
    """This is also the way back in after a compromise. Leaving the attacker's session
    alive while changing the password makes the recovery pointless."""
    from app.modules.auth.models import RefreshToken

    person = await make_user("super_admin")
    db.add(
        RefreshToken(
            user_id=person.id,
            token_hash="b" * 64,
            family_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await db.flush()

    monkeypatch.setenv("ADMIN_PASSWORD", "Chandni#Bridge47")
    await cli.set_password(person.email)

    live = await db.find(RefreshToken, {"user_id": person.id, "revoked_at": None})
    assert not live


async def test_set_password_refuses_an_unknown_address(db, run_command, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Chandni#Bridge47")
    with pytest.raises(SystemExit, match="No account exists"):
        await cli.set_password("nobody@example.com")
