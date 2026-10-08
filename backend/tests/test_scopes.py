"""Scope containment is the single rule that keeps tenants apart (PRD §5.2).

If any of these pass when they should fail, an admin of one institute can act in another.
"""

from __future__ import annotations

import uuid

import pytest

from app.modules.rbac.scopes import PLATFORM_SCOPE, Scope, branch_scope, institute_scope

INST_A = uuid.uuid4()
INST_B = uuid.uuid4()
BRANCH_A1 = uuid.uuid4()
BRANCH_A2 = uuid.uuid4()
BRANCH_B1 = uuid.uuid4()


def test_platform_scope_contains_everything() -> None:
    assert PLATFORM_SCOPE.contains(PLATFORM_SCOPE)
    assert PLATFORM_SCOPE.contains(institute_scope(INST_A))
    assert PLATFORM_SCOPE.contains(branch_scope(INST_B, BRANCH_B1))


def test_institute_scope_contains_its_own_branches() -> None:
    scope = institute_scope(INST_A)
    assert scope.contains(institute_scope(INST_A))
    assert scope.contains(branch_scope(INST_A, BRANCH_A1))
    assert scope.contains(branch_scope(INST_A, BRANCH_A2))


def test_institute_scope_does_not_reach_another_institute() -> None:
    scope = institute_scope(INST_A)
    assert not scope.contains(institute_scope(INST_B))
    assert not scope.contains(branch_scope(INST_B, BRANCH_B1))


def test_institute_scope_does_not_reach_the_platform() -> None:
    assert not institute_scope(INST_A).contains(PLATFORM_SCOPE)


def test_branch_scope_reaches_only_its_own_branch() -> None:
    scope = branch_scope(INST_A, BRANCH_A1)
    assert scope.contains(branch_scope(INST_A, BRANCH_A1))
    assert not scope.contains(branch_scope(INST_A, BRANCH_A2))
    assert not scope.contains(branch_scope(INST_B, BRANCH_B1))


def test_branch_scope_does_not_widen_to_its_institute() -> None:
    """A Branch Admin must not act institute-wide just by omitting the branch id."""
    assert not branch_scope(INST_A, BRANCH_A1).contains(institute_scope(INST_A))


def test_levels_are_reported_correctly() -> None:
    assert PLATFORM_SCOPE.level == "platform"
    assert institute_scope(INST_A).level == "institute"
    assert branch_scope(INST_A, BRANCH_A1).level == "branch"


def test_a_branch_without_an_institute_is_rejected() -> None:
    """An unanchored branch scope would compare equal against any institute."""
    with pytest.raises(ValueError, match="must also name its institute"):
        Scope(institute_id=None, branch_id=BRANCH_A1)


def test_scopes_are_hashable_and_comparable() -> None:
    """The permission context stores scopes in sets, so value equality must hold."""
    assert institute_scope(INST_A) == institute_scope(INST_A)
    assert len({institute_scope(INST_A), institute_scope(INST_A)}) == 1
    assert len({institute_scope(INST_A), institute_scope(INST_B)}) == 2
