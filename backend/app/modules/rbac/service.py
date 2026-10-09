"""The authorization engine (PRD §5.2).

Everything that decides "allowed or not" lives here. Routers call ``Authorized.ensure(...)``;
nothing anywhere else compares role names or institute ids by hand.

The check, in order:

1. the user holds the permission at the target scope or above it  (``AuthContext.can``)
2. for class-level targets, the Faculty/Student membership link exists
3. the permission's module is enabled for that institute
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, NotFound
from app.modules.rbac import repository
from app.modules.rbac.catalog import FACULTY, STUDENT, grantable_ceiling
from app.modules.rbac.context import AuthContext, build_context, context_cache
from app.modules.rbac.scopes import Scope

logger = logging.getLogger(__name__)

# permission key -> module key. Seeded data, effectively static for the process lifetime;
# refreshed lazily if a permission is ever seen that predates the cache.
_permission_modules: dict[str, str] = {}
_core_modules: frozenset[str] = frozenset()


async def get_context(db: AsyncSession, user_id: uuid.UUID) -> AuthContext:
    """Cached authorization context for a user.

    Two queries, not one: role grants and the per-user allow/deny layer. They
    could be a UNION, but keeping them apart means the far more common case — a user with
    no personal grants at all — costs one index-only scan that returns nothing.
    """
    cached = context_cache.get(user_id)
    if cached is not None:
        return cached
    rows = await repository.load_grants(db, user_id)
    personal = await repository.load_personal_grants(db, user_id)
    context = build_context(user_id, rows, personal)
    context_cache.put(user_id, context)
    return context


def invalidate_context(user_id: uuid.UUID) -> None:
    """Call after any role assignment, revocation or status change."""
    context_cache.invalidate(user_id)


async def _module_for(db: AsyncSession, permission: str) -> str | None:
    global _permission_modules, _core_modules
    if permission not in _permission_modules:
        _permission_modules = await repository.load_permission_modules(db)
        _core_modules = await repository.load_core_modules(db)
    return _permission_modules.get(permission)


async def _module_allows(db: AsyncSession, permission: str, scope: Scope) -> bool:
    """PRD §5.2 step 5. Core is always on, and platform-scoped actions have no institute
    to check against, so both short-circuit before touching the database."""
    module_key = await _module_for(db, permission)
    if module_key is None or module_key in _core_modules:
        return True
    if scope.institute_id is None:
        return True
    return await repository.is_module_enabled(db, scope.institute_id, module_key)


async def can(
    db: AsyncSession,
    context: AuthContext,
    permission: str,
    scope: Scope,
    *,
    class_id: uuid.UUID | None = None,
) -> bool:
    if not context.can(permission, scope):
        return False
    if class_id is not None and not await _class_membership_ok(db, context, class_id):
        return False
    return await _module_allows(db, permission, scope)


async def _class_membership_ok(db: AsyncSession, context: AuthContext, class_id: uuid.UUID) -> bool:
    """PRD §5.2 step 4.

    Only Faculty and Student are membership-gated. An admin holding the permission at
    branch level or above already passed step 3 and needs no link — otherwise an Institute
    Admin could not manage a class they do not personally teach.
    """
    role_keys = {a.role_key for a in context.assignments}
    is_only_faculty_or_student = role_keys and role_keys <= {FACULTY, STUDENT}
    if not is_only_faculty_or_student:
        return True
    if FACULTY in role_keys and await repository.faculty_teaches_class(
        db, context.user_id, class_id
    ):
        return True
    return STUDENT in role_keys and await repository.student_enrolled_in_class(
        db, context.user_id, class_id
    )


async def resolve_class_scope(db: AsyncSession, class_id: uuid.UUID) -> Scope:
    found = await repository.class_scope(db, class_id)
    if found is None:
        raise NotFound("That class does not exist.")
    institute_id, branch_id = found
    return Scope(institute_id=institute_id, branch_id=branch_id)


class Authorized:
    """What a protected route receives from ``require_permission``.

    The dependency has already confirmed the caller is authenticated, active, and holds the
    permission *somewhere*. The precise scope is only known once the route has resolved its
    target, so the route calls ``ensure`` with it. Two steps, deliberately: the cheap check
    rejects obvious cases before any work, the precise check is where the target is known.
    """

    __slots__ = ("_db", "context", "permission")

    def __init__(self, db: AsyncSession, context: AuthContext, permission: str) -> None:
        self._db = db
        self.context = context
        self.permission = permission

    @property
    def user_id(self) -> uuid.UUID:
        return self.context.user_id

    async def ensure(self, scope: Scope, *, class_id: uuid.UUID | None = None) -> None:
        """Raise ``Forbidden`` unless the caller may act at ``scope``."""
        if await can(self._db, self.context, self.permission, scope, class_id=class_id):
            return
        # Logged with ids only — never the target's contents.
        logger.info(
            "authorization denied",
            extra={
                "user_id": str(self.context.user_id),
                "permission": self.permission,
                "institute_id": str(scope.institute_id) if scope.institute_id else None,
                "branch_id": str(scope.branch_id) if scope.branch_id else None,
            },
        )
        raise Forbidden()

    def usable_scopes(self) -> tuple[Scope, ...]:
        """Every scope this permission is held at that an explicit deny has not overlapped.

        List endpoints must build their filters from *this*, never from the raw grants:
        a deny that the permission check honours but the list query ignores shows the
        blocked rows anyway, which is the whole of the protection gone.
        """
        blocked = self.context.denials_for(self.permission)
        granted = self.context.scopes_for(self.permission)
        if not blocked:
            return granted
        return tuple(s for s in granted if not any(b.intersects(s) for b in blocked))

    def visible_institute_ids(self) -> frozenset[uuid.UUID] | None:
        """Institutes this permission still reaches, or ``None`` for platform-wide reach."""
        scopes = self.usable_scopes()
        if any(s.institute_id is None for s in scopes):
            return None
        return frozenset(s.institute_id for s in scopes if s.institute_id)

    def scopes_within(self, institute_id: uuid.UUID) -> tuple[Scope, ...]:
        """The caller's usable grants for this permission that reach into ``institute_id``.

        A platform grant reaches every institute; an institute or branch grant reaches only
        its own. A grant that an explicit deny overlaps is dropped entirely rather than
        narrowed: subtracting one branch out of an institute-wide grant would
        mean every list query carrying an exclusion list, and a single missed one leaks
        exactly the rows somebody went to the trouble of blocking. Dropping the wide grant
        is the safe direction — the person can still be given the narrower grants they
        should have had.
        """
        blocked = self.context.denials_for(self.permission)
        return tuple(
            scope
            for scope in self.context.scopes_for(self.permission)
            if (scope.institute_id is None or scope.institute_id == institute_id)
            and not any(block.intersects(scope) for block in blocked)
        )

    async def ensure_within(self, institute_id: uuid.UUID) -> tuple[Scope, ...]:
        """Authorise *reading a collection* inside an institute.

        Listing is not the same as acting. A Branch Admin holds `class:read` only at their
        own branch, but asking for "the classes of my institute" is a legitimate request —
        the answer is simply narrowed to their branch. Requiring institute-level authority
        here would 403 every branch-scoped user out of lists they are entitled to a slice of.

        Returns the grants that apply, so the caller can narrow the query with them.
        """
        scopes = self.scopes_within(institute_id)
        if not scopes:
            raise Forbidden()
        if not await _module_allows(self._db, self.permission, Scope(institute_id=institute_id)):
            raise Forbidden()
        return scopes

    @staticmethod
    def covers_whole_institute(scopes: tuple[Scope, ...], institute_id: uuid.UUID) -> bool:
        """True when the grants are institute-wide, so no branch filter is needed."""
        return any(
            scope.institute_id is None
            or (scope.institute_id == institute_id and scope.branch_id is None)
            for scope in scopes
        )

    async def ensure_class(self, class_id: uuid.UUID) -> Scope:
        """Resolve a class to its scope and authorise against it in one step."""
        scope = await resolve_class_scope(self._db, class_id)
        await self.ensure(scope, class_id=class_id)
        return scope

    def ensure_can_grant(self, target_role_rank: int, scope: Scope) -> None:
        """No-escalation rule (PRD §3.1).

        Rank is compared against what the caller holds *at this scope*, not their highest
        rank anywhere — otherwise a Branch Admin of one branch could grant roles in another.

        There is no exception. Super Admin cannot appoint another Super Admin either; that
        happens through `python -m app.cli grant-super-admin`, run on the server. See
        `grantable_ceiling` for why succession was moved out of the web app.
        """
        holder_rank = self.context.max_rank_within(scope)
        if target_role_rank > grantable_ceiling(holder_rank):
            raise Forbidden("You cannot give someone a role at or above your own level.")

    def ensure_can_restrain(self, target_rank: int, scope: Scope) -> None:
        """May the caller take something *away* from somebody of this rank?

        Deliberately one rank more permissive than `ensure_can_grant`, and the difference
        matters more than it looks.

        Granting is escalation: handing out your own level creates a peer who can undo
        everything you do, so it is refused outright and a successor is appointed on the
        server instead. Taking away is the opposite — suspending an account, or removing a
        role — and it never gives the caller anything they did not already have.

        Holding the two to the same rule was a mistake that only showed up in the case that
        matters most. If a Super Admin's password is stolen, the other Super Admins are the
        people who have to shut that account down, and under the grant rule every one of
        them was refused: no suspension, no revocation, nothing short of shell access to
        the server while the intruder stayed signed in. An account nobody can contain is
        worse than a peer who can be appointed.

        Equal rank, not above. A Branch Admin still cannot suspend the principal, and
        `_guard_last_super_admin` still stops the final working administrator from being
        removed.
        """
        holder_rank = self.context.max_rank_within(scope)
        if target_rank > holder_rank:
            raise Forbidden("You cannot act on someone above your own level.")
