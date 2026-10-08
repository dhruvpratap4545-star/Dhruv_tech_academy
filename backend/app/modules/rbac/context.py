"""The per-user authorization context and its cache.

An ``AuthContext`` answers "may this person do X here?" without touching the database. It is
built once per request from a single query (see ``repository.load_grants``) and cached for a
short TTL, because the same user hits several endpoints in quick succession and re-running
the join each time is pure waste.

Memory shape matters — one of these exists per cached user:

* ``grants`` maps a permission key to the tuple of scopes it was granted at. Tuples, not
  lists, so they are immutable and cheap to share between requests.
* Scopes are ``slots``-based frozen dataclasses (see ``scopes.py``).
* A typical user holds 1–2 roles covering ~25 permissions, so a context is a few kilobytes.

The cache is bounded and TTL'd. Without a bound it is a memory leak with extra steps: every
user who ever logs in would be retained for the lifetime of the process.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from time import monotonic

from app.core.config import settings
from app.modules.rbac.scopes import Scope


@dataclass(frozen=True, slots=True)
class Assignment:
    """One live role assignment, flattened for the UI and the no-escalation check."""

    role_key: str
    role_name: str
    rank: int
    scope: Scope


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Everything the engine needs to answer "may this person do X here?".

    ``grants`` is the union of what the user's roles allow and what has been granted to
    them personally — by the time a context exists, the two are indistinguishable, which
    is what lets every call site stay a single ``can()``.

    ``denials`` is kept separate on purpose. It is not the absence of a grant; it is a
    stronger statement that overrides every grant, and merging the two would lose that.
    """

    user_id: uuid.UUID
    grants: Mapping[str, tuple[Scope, ...]]
    assignments: tuple[Assignment, ...]
    denials: Mapping[str, tuple[Scope, ...]] = field(default_factory=dict)
    # Keys that reached ``grants`` from a personal grant rather than a role. Kept so the
    # "why can I do this?" screen can show an exception *as* an exception; the engine
    # itself never consults it, because by then the distinction does not matter.
    direct: frozenset[str] = frozenset()

    @property
    def permissions(self) -> frozenset[str]:
        """Every permission key the user can still use *somewhere*. Used by ``GET /me`` so
        the UI can decide which menus to draw — a convenience, never the decision itself.

        A key blocked everywhere is excluded, so a denied person is not shown a menu whose
        every action will be refused.
        """
        return frozenset(key for key in self.grants if self.holds(key))

    @property
    def max_rank(self) -> int:
        """Highest rank held anywhere. 0 when the user holds no role at all."""
        return max((a.rank for a in self.assignments), default=0)

    @property
    def institute_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(
            a.scope.institute_id for a in self.assignments if a.scope.institute_id is not None
        )

    @property
    def primary_institute_id(self) -> uuid.UUID | None:
        """The institute this person most belongs to, or ``None`` for platform staff.

        Used to stamp an institute onto events about a *person* rather than a record —
        signing in, being locked out. Without it those rows are institute-less, and an
        institute admin's audit log and sign-in chart are permanently empty while the
        platform-wide view looks fine: a defect that only shows up for the customer.

        Their most senior assignment wins, because that is the one that defines where they
        sit when they hold more than one.
        """
        ranked = sorted(
            (a for a in self.assignments if a.scope.institute_id is not None),
            key=lambda a: -a.rank,
        )
        return ranked[0].scope.institute_id if ranked else None

    @property
    def is_platform_staff(self) -> bool:
        return any(a.scope.level == "platform" for a in self.assignments)

    def scopes_for(self, permission: str) -> tuple[Scope, ...]:
        return self.grants.get(permission, ())

    def denials_for(self, permission: str) -> tuple[Scope, ...]:
        return self.denials.get(permission, ())

    def can(self, permission: str, target: Scope) -> bool:
        """May this person do ``permission`` against ``target``? (PRD §5.2 step 3.)

        Deny is evaluated first and is absolute — it outranks every role, a Super Admin's
        included. It matches on *overlap* rather than containment: a block on one branch
        also refuses an institute-wide request, because serving that request would reach
        into the blocked branch. Refusing the wider ask is the safe direction.
        """
        if any(blocked.intersects(target) for blocked in self.denials.get(permission, ())):
            return False
        return any(granted.contains(target) for granted in self.grants.get(permission, ()))

    def holds(self, permission: str) -> bool:
        """Holds the permission somewhere it is still usable. A pre-filter, never an answer.

        A grant survives unless a denial sits at or *above* it and wipes it out entirely.
        A denial underneath only narrows the grant, so the permission is still held.
        """
        granted = self.grants.get(permission)
        if not granted:
            return False
        blocked = self.denials.get(permission, ())
        if not blocked:
            return True
        return any(not any(b.contains(g) for b in blocked) for g in granted)

    def max_rank_within(self, target: Scope) -> int:
        """Highest rank the user holds at or above ``target``.

        This is what the no-escalation rule compares against (PRD §3.1): a Branch Admin of
        branch A must not be able to grant roles in branch B just because of their rank.
        """
        return max(
            (a.rank for a in self.assignments if a.scope.contains(target)),
            default=0,
        )


def build_context(
    user_id: uuid.UUID,
    rows: Iterable[tuple[str, str, int, uuid.UUID | None, uuid.UUID | None, str]],
    personal: Iterable[tuple[str, str, uuid.UUID | None, uuid.UUID | None]] = (),
) -> AuthContext:
    """Fold the flat join results into a context.

    ``rows`` is the (assignment x permission) join; ``personal`` is the per-user grant
    layer as ``(permission_key, effect, institute_id, branch_id)``.

    One pass each, three dicts. Scopes are deduplicated through sets because two roles
    commonly grant the same permission at the same scope, and because a permission granted
    both by a role and personally should cost one entry, not two.
    """
    grant_sets: dict[str, set[Scope]] = {}
    deny_sets: dict[str, set[Scope]] = {}
    assignments: dict[tuple[str, Scope], Assignment] = {}

    for role_key, role_name, rank, institute_id, branch_id, permission_key in rows:
        scope = Scope(institute_id=institute_id, branch_id=branch_id)
        grant_sets.setdefault(permission_key, set()).add(scope)
        assignments.setdefault(
            (role_key, scope),
            Assignment(role_key=role_key, role_name=role_name, rank=rank, scope=scope),
        )

    direct: set[str] = set()
    for permission_key, effect, institute_id, branch_id in personal:
        scope = Scope(institute_id=institute_id, branch_id=branch_id)
        if effect == "deny":
            deny_sets.setdefault(permission_key, set()).add(scope)
        else:
            grant_sets.setdefault(permission_key, set()).add(scope)
            direct.add(permission_key)

    return AuthContext(
        user_id=user_id,
        grants={key: tuple(scopes) for key, scopes in grant_sets.items()},
        assignments=tuple(assignments.values()),
        denials={key: tuple(scopes) for key, scopes in deny_sets.items()},
        direct=frozenset(direct),
    )


class ContextCache:
    """Bounded TTL cache.

    Deliberately not an LRU: entries expire on time, and when the cache is full the oldest
    inserted entries are dropped. Role changes are rare, so the eviction policy matters far
    less than the hard ceiling on memory.

    This is per-process. With more than one API instance a revoked role can linger for up to
    the TTL on the *other* instances, which PRD §7.2 explicitly accepts ("role cache <= 60 s").
    Moving to Redis is the documented step before scaling out (PRD §10.2).
    """

    __slots__ = ("_entries", "_max_entries", "_ttl")

    def __init__(self, ttl_seconds: int, max_entries: int) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[uuid.UUID, tuple[float, AuthContext]] = {}

    def get(self, user_id: uuid.UUID) -> AuthContext | None:
        entry = self._entries.get(user_id)
        if entry is None:
            return None
        expires_at, context = entry
        if expires_at <= monotonic():
            self._entries.pop(user_id, None)
            return None
        return context

    def put(self, user_id: uuid.UUID, context: AuthContext) -> None:
        if len(self._entries) >= self._max_entries:
            self._evict()
        self._entries[user_id] = (monotonic() + self._ttl, context)

    def invalidate(self, user_id: uuid.UUID) -> None:
        """Called the moment a role is assigned or revoked, so the change is instant on
        this instance rather than waiting out the TTL."""
        self._entries.pop(user_id, None)

    def clear(self) -> None:
        self._entries.clear()

    def _evict(self) -> None:
        now = monotonic()
        expired = [uid for uid, (exp, _) in self._entries.items() if exp <= now]
        for uid in expired:
            del self._entries[uid]
        # Still full even after dropping expired entries: shed the oldest insertions.
        # dict preserves insertion order, so the first keys are the oldest.
        overflow = len(self._entries) - self._max_entries + 1
        if overflow > 0:
            for uid in list(self._entries)[:overflow]:
                del self._entries[uid]


context_cache = ContextCache(
    ttl_seconds=settings.permission_cache_ttl_seconds,
    max_entries=settings.permission_cache_max_entries,
)
