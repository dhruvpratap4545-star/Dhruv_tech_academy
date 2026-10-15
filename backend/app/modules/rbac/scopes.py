"""Scope arithmetic for the authorization engine (PRD §5.2).

A scope is a position in the hierarchy. There are exactly four shapes:

    Scope(None, None, None)            platform      — the whole product
    Scope(org, None, None)             organisation  — every institute under one organisation
    Scope(org?, institute, None)       institute     — everything inside one institute
    Scope(org?, institute, branch)     branch        — one branch of one institute

An assignment at a scope covers that scope and everything below it, so a permission granted
at institute level applies to every branch and class inside that institute. ``contains`` is
the single place that rule is expressed; nothing else compares ids by hand.

**A scope carries its whole path, not just its own level.** An institute belonging to the
JSPM organisation is ``Scope(jspm, college, None)`` — the organisation id travels with it
even though the grant is at institute level. That is what keeps ``contains`` pure
arithmetic: asking whether an organisation grant reaches an institute is then a comparison,
not a database query. The price is that a target scope has to be *resolved* before it is
compared, which is what ``Authorized.scope_for`` is for. Getting that wrong fails closed —
the organisation id is missing, the organisation grant does not match, and the request is
refused — which is the safe direction to be wrong in.

Organisations are optional. A standalone coaching institute has no organisation, and its
scopes carry ``organisation_id=None`` exactly as they did before this level existed.

Classes do not get their own scope level. A class belongs to a branch, so a class-level
target resolves to ``Scope(org?, institute, branch)`` and faculty/student membership is
checked separately against ``class_faculty`` / ``class_enrollments`` (PRD §5.2 step 4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

PLATFORM: Final = "platform"
ORGANISATION: Final = "organisation"
INSTITUTE: Final = "institute"
BRANCH: Final = "branch"

#: Every level, outermost first. The order *is* the hierarchy; rank comparisons and the
#: "which level is wider" question both read it rather than hard-coding a sequence.
LEVELS: Final = (PLATFORM, ORGANISATION, INSTITUTE, BRANCH)


@dataclass(frozen=True, slots=True, kw_only=True)
class Scope:
    """``slots=True`` and immutability matter here: scopes are created on every request and
    held in the permission cache, so they must be small and safely shareable.

    ``kw_only=True`` is a guard rather than a style choice. Adding ``organisation_id`` put
    a new field at the *front* of the signature, so every existing ``Scope(inst, branch)``
    silently became ``Scope(organisation_id=inst, institute_id=branch)`` — a permission
    check comparing the wrong two ids, which is the worst kind of bug this file could
    produce. Keyword-only makes that a ``TypeError`` instead of a wrong answer, now and
    whenever a level is added again.
    """

    organisation_id: uuid.UUID | None = None
    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.branch_id is not None and self.institute_id is None:
            raise ValueError("A branch scope must also name its institute.")

    @property
    def level(self) -> str:
        """Which level this scope sits at.

        Read off the *innermost* id that is set, because the outer ids are the path to it:
        an institute inside an organisation names both, and it is still an institute scope.
        """
        if self.branch_id is not None:
            return BRANCH
        if self.institute_id is not None:
            return INSTITUTE
        if self.organisation_id is not None:
            return ORGANISATION
        return PLATFORM

    def contains(self, target: Scope) -> bool:
        """True when a grant at ``self`` authorises an action against ``target``.

        Containment only ever widens downwards — a branch grant never reaches a sibling
        branch, an institute grant never reaches another institute, and an organisation
        grant never reaches an institute outside it.

        The organisation case is the one to read carefully: it matches on the target's
        organisation id, so a target built without one will not match. That is deliberate.
        An unresolved target refuses an organisation-wide grant rather than satisfying it.
        """
        if self.level == PLATFORM:
            return True

        if self.institute_id is None:
            # An organisation grant. Reaches anything whose path runs through it.
            return self.organisation_id is not None and self.organisation_id == (
                target.organisation_id
            )

        if self.institute_id != target.institute_id:
            return False
        if self.branch_id is None:
            return True
        return self.branch_id == target.branch_id

    def intersects(self, other: Scope) -> bool:
        """True when the two scopes overlap at all — either contains the other.

        Scopes are nested cones, never partial overlaps, so "they share ground" reduces to
        "one is inside the other". This is what an explicit *deny* is matched with
        — a block on one branch also refuses an institute-wide action, because
        that action would otherwise reach the blocked branch. Over-refusing a wider request
        is the safe direction; quietly serving the blocked rows inside it is not.
        """
        return self.contains(other) or other.contains(self)


PLATFORM_SCOPE: Final = Scope()


def organisation_scope(organisation_id: uuid.UUID) -> Scope:
    return Scope(organisation_id=organisation_id)


def institute_scope(institute_id: uuid.UUID, *, organisation_id: uuid.UUID | None = None) -> Scope:
    """An institute, with the organisation it belongs to when it has one.

    Pass ``organisation_id`` whenever it is known. Leaving it out is only correct for a
    standalone institute; for one inside an organisation it produces a scope that an
    organisation-wide grant will not match.
    """
    return Scope(organisation_id=organisation_id, institute_id=institute_id)


def branch_scope(
    institute_id: uuid.UUID,
    branch_id: uuid.UUID,
    *,
    organisation_id: uuid.UUID | None = None,
) -> Scope:
    return Scope(organisation_id=organisation_id, institute_id=institute_id, branch_id=branch_id)
