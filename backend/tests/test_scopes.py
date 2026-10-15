"""Scope containment is the single rule that keeps tenants apart (PRD §5.2).

If any of these pass when they should fail, an admin of one institute can act in another.
"""

from __future__ import annotations

import uuid

import pytest

from app.modules.rbac.scopes import (
    PLATFORM_SCOPE,
    Scope,
    branch_scope,
    institute_scope,
    organisation_scope,
)

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


# --------------------------------------------------------------- the organisation level

ORG_X = uuid.uuid4()
ORG_Y = uuid.uuid4()
# INST_A and INST_B belong to ORG_X; INST_C belongs to ORG_Y; INST_LONE belongs to nobody.
INST_C = uuid.uuid4()
INST_LONE = uuid.uuid4()
BRANCH_C1 = uuid.uuid4()


def in_x(institute: uuid.UUID, branch: uuid.UUID | None = None) -> Scope:
    """A scope inside organisation X, with its whole path — as a resolved target has."""
    return Scope(organisation_id=ORG_X, institute_id=institute, branch_id=branch)


def in_y(institute: uuid.UUID, branch: uuid.UUID | None = None) -> Scope:
    return Scope(organisation_id=ORG_Y, institute_id=institute, branch_id=branch)


def test_an_organisation_grant_reaches_every_institute_inside_it() -> None:
    scope = organisation_scope(ORG_X)
    assert scope.contains(organisation_scope(ORG_X))
    assert scope.contains(in_x(INST_A))
    assert scope.contains(in_x(INST_B))
    assert scope.contains(in_x(INST_A, BRANCH_A1))


def test_an_organisation_grant_never_reaches_a_sibling_organisation() -> None:
    """The whole point of the level. JSPM's administrator is not MIT's."""
    scope = organisation_scope(ORG_X)
    assert not scope.contains(organisation_scope(ORG_Y))
    assert not scope.contains(in_y(INST_C))
    assert not scope.contains(in_y(INST_C, BRANCH_C1))


def test_an_organisation_grant_never_reaches_a_standalone_institute() -> None:
    """An institute with no organisation is nobody's to administer but its own."""
    assert not organisation_scope(ORG_X).contains(institute_scope(INST_LONE))
    assert not organisation_scope(ORG_X).contains(branch_scope(INST_LONE, BRANCH_A1))


def test_an_unresolved_target_is_refused_rather_than_allowed() -> None:
    """The failure mode this design has to get right.

    A target built without its organisation id looks standalone. An organisation grant
    must then *refuse* it — the request is declined and somebody investigates — rather
    than matching on the institute id alone, which would hand one organisation's
    administrator every institute in the product.
    """
    unresolved = institute_scope(INST_A)  # INST_A really is inside ORG_X
    assert not organisation_scope(ORG_X).contains(unresolved)


def test_an_institute_grant_does_not_widen_to_its_organisation() -> None:
    """Containment only ever runs downwards. Running one college of JSPM is not running
    JSPM."""
    assert not in_x(INST_A).contains(organisation_scope(ORG_X))
    assert not in_x(INST_A).contains(in_x(INST_B))
    assert not in_x(INST_A, BRANCH_A1).contains(in_x(INST_A))


def test_platform_still_contains_everything_including_organisations() -> None:
    assert PLATFORM_SCOPE.contains(organisation_scope(ORG_X))
    assert PLATFORM_SCOPE.contains(in_x(INST_A, BRANCH_A1))
    assert not organisation_scope(ORG_X).contains(PLATFORM_SCOPE)


def test_level_reads_the_innermost_id_not_the_outermost() -> None:
    """An institute inside an organisation names both ids and is still an institute."""
    assert PLATFORM_SCOPE.level == "platform"
    assert organisation_scope(ORG_X).level == "organisation"
    assert in_x(INST_A).level == "institute"
    assert in_x(INST_A, BRANCH_A1).level == "branch"
    # And an institute outside any organisation is still an institute.
    assert institute_scope(INST_LONE).level == "institute"


def test_a_deny_anywhere_inside_an_organisation_overlaps_the_whole_grant() -> None:
    """`intersects`, not `contains`, is what a denial is matched with.

    A block on one branch has to refuse an organisation-wide action too, because that
    action would otherwise reach the blocked branch.
    """
    org = organisation_scope(ORG_X)
    assert org.intersects(in_x(INST_A, BRANCH_A1))
    assert in_x(INST_A, BRANCH_A1).intersects(org)
    # ...but a block inside a different organisation does not narrow this one.
    assert not org.intersects(in_y(INST_C))


def test_the_whole_containment_matrix() -> None:
    """Every level against every level, in one place.

    Written as a table because the interesting cases are the ones nobody thinks to write
    individually — and a new level added later has to be added to this grid, which makes
    the omission obvious.
    """
    platform = PLATFORM_SCOPE
    org_x = organisation_scope(ORG_X)
    inst_a = in_x(INST_A)
    branch_a1 = in_x(INST_A, BRANCH_A1)

    expected = {
        # (grant, target): does the grant authorise the target?
        ("platform", "platform"): True,
        ("platform", "org"): True,
        ("platform", "institute"): True,
        ("platform", "branch"): True,
        ("org", "platform"): False,
        ("org", "org"): True,
        ("org", "institute"): True,
        ("org", "branch"): True,
        ("institute", "platform"): False,
        ("institute", "org"): False,
        ("institute", "institute"): True,
        ("institute", "branch"): True,
        ("branch", "platform"): False,
        ("branch", "org"): False,
        ("branch", "institute"): False,
        ("branch", "branch"): True,
    }
    scopes = {"platform": platform, "org": org_x, "institute": inst_a, "branch": branch_a1}

    for (grant_name, target_name), allowed in expected.items():
        actual = scopes[grant_name].contains(scopes[target_name])
        assert actual is allowed, (
            f"a {grant_name} grant acting on a {target_name} target: "
            f"expected {allowed}, got {actual}"
        )
