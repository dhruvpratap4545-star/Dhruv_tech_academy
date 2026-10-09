"""Administrative commands that deliberately have no screen in the web app.

Appointing a Super Admin is the one action the browser cannot perform. Every role in the
application may only hand out ranks strictly below its own (PRD §3.1 as amended), Super
Admin included, so there is no sequence of clicks that produces a second platform owner.
That is on purpose: who controls the whole platform should not be decided by a session
cookie that could be stolen, and an administrator reading "you cannot give someone your
own level or above" should find it true without exceptions.

Succession still has to be possible, so it lives here instead — behind shell access to
the server, which is a different and much smaller set of people.

Run with the application's environment loaded::

    python -m app.cli grant-super-admin someone@example.com
    python -m app.cli revoke-super-admin someone@example.com
    python -m app.cli list-super-admins

A granted account is *invited*, never given a password here: a password created by a
command ends up in shell history, a deploy log or a screenshot. The person proves they
control the mailbox through the normal Forgot password flow.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.db import SessionLocal, engine
from app.core.logging import configure_logging
from app.modules.rbac import catalog
from app.modules.rbac.models import Role, UserRoleAssignment
from app.modules.users.models import User, UserPreference


async def _super_admin_role(db) -> Role:
    role = await db.scalar(select(Role).where(Role.key == catalog.SUPER_ADMIN))
    if role is None:
        raise SystemExit("The super_admin role is missing. Run `python -m app.core.seed` first.")
    return role


async def _find_user(db, email: str) -> User | None:
    return await db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


async def grant(email: str, *, create_missing: bool) -> None:
    email = email.strip().lower()
    async with SessionLocal() as db:
        role = await _super_admin_role(db)
        user = await _find_user(db, email)

        if user is None:
            if not create_missing:
                raise SystemExit(
                    f"No account exists for {email}. "
                    f"Re-run with --create to invite them as a new Super Admin."
                )
            user = User(email=email, full_name="Super Admin", status="invited", password_hash=None)
            db.add(user)
            await db.flush()
            db.add(UserPreference(user_id=user.id))
            print(f"Created {email} as an invited account with no password.")

        if user.status == "deleted":
            raise SystemExit(f"{email} has been deleted. Restore the account before granting.")

        existing = await db.scalar(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user.id,
                UserRoleAssignment.role_id == role.id,
                UserRoleAssignment.institute_id.is_(None),
                UserRoleAssignment.revoked_at.is_(None),
            )
        )
        if existing is not None:
            print(f"{email} already holds Super Admin. Nothing to do.")
            return

        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        await db.commit()

    print(f"Granted Super Admin to {email}.")
    print("They sign in with Forgot password to set one, if they have not already.")


async def revoke(email: str) -> None:
    email = email.strip().lower()
    async with SessionLocal() as db:
        role = await _super_admin_role(db)
        user = await _find_user(db, email)
        if user is None:
            raise SystemExit(f"No account exists for {email}.")

        rows = list(
            (
                await db.execute(
                    select(UserRoleAssignment).where(
                        UserRoleAssignment.role_id == role.id,
                        UserRoleAssignment.revoked_at.is_(None),
                    )
                )
            ).scalars()
        )
        mine = [r for r in rows if r.user_id == user.id]
        if not mine:
            raise SystemExit(f"{email} does not hold Super Admin.")
        if len(rows) == len(mine):
            raise SystemExit(
                "That is the only Super Admin on the platform. "
                "Grant the role to someone else first, or nobody will be able to administer it."
            )

        for row in mine:
            row.revoked_at = datetime.now(UTC)
        await db.commit()

    print(f"Removed Super Admin from {email}.")


async def listing() -> None:
    async with SessionLocal() as db:
        role = await _super_admin_role(db)
        rows = (
            await db.execute(
                select(User)
                .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
                .where(
                    UserRoleAssignment.role_id == role.id,
                    UserRoleAssignment.revoked_at.is_(None),
                )
                .order_by(User.email)
            )
        ).scalars()
        people = list(rows)

    if not people:
        print("No Super Admin exists. The platform cannot be administered.")
        return
    print(f"{len(people)} Super Admin account(s):")
    for person in people:
        ready = person.password_hash is not None and person.status == "active"
        usable = "can sign in" if ready else person.status
        print(f"  {person.email:<40} {usable}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("grant-super-admin", help="Give an account the Super Admin role.")
    g.add_argument("email")
    g.add_argument(
        "--create",
        action="store_true",
        help="Invite the address as a new account if no user has it yet.",
    )

    r = sub.add_parser("revoke-super-admin", help="Take the Super Admin role away.")
    r.add_argument("email")

    sub.add_parser("list-super-admins", help="Show who holds Super Admin.")
    return parser


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    args = build_parser().parse_args(argv)

    async def run() -> None:
        try:
            if args.command == "grant-super-admin":
                await grant(args.email, create_missing=args.create)
            elif args.command == "revoke-super-admin":
                await revoke(args.email)
            else:
                await listing()
        finally:
            await engine.dispose()

    try:
        asyncio.run(run())
    except SystemExit as exit_error:
        print(str(exit_error), file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
