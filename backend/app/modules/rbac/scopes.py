"""Scope arithmetic for the authorization engine (PRD §5.2).

A scope is a position in the hierarchy. There are exactly three shapes:

    Scope(None, None)             platform      — the whole product
    Scope(institute, None)        institute     — everything inside one institute
    Scope(institute, branch)      branch        — one branch of one institute

An assignment at a scope covers that scope and everything below it, so a permission granted
at institute level applies to every branch and class inside that institute. ``contains`` is
the single place that rule is expressed; nothing else compares ids by hand.

Classes do not get their own scope level. A class belongs to a branch, so a class-level
target resolves to ``Scope(institute, branch)`` and faculty/student membership is checked
separately against ``class_faculty`` / ``class_enrollments`` (PRD §5.2 step 4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

PLATFORM: Final = "platform"
INSTITUTE: Final = "institute"
BRANCH: Final = "branch"


@dataclass(frozen=True, slots=True)
class Scope:
    """``slots=True`` and immutability matter here: scopes are created on every request and
    held in the permission cache, so they must be small and safely shareable."""

    institute_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.branch_id is not None and self.institute_id is None:
            raise ValueError("A branch scope must also name its institute.")

    @property
    def level(self) -> str:
        if self.institute_id is None:
            return PLATFORM
        return BRANCH if self.branch_id is not None else INSTITUTE

    def contains(self, target: Scope) -> bool:
        """True when a grant at ``self`` authorises an action against ``target``.

        Containment only ever widens downwards — a branch grant never reaches a sibling
        branch, and an institute grant never reaches another institute.
        """
        if self.institute_id is None:
            return True
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


def institute_scope(institute_id: uuid.UUID) -> Scope:
    return Scope(institute_id=institute_id)


def branch_scope(institute_id: uuid.UUID, branch_id: uuid.UUID) -> Scope:
    return Scope(institute_id=institute_id, branch_id=branch_id)
