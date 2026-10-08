"""The permission context and its cache (PRD §5.2, §7.2)."""

from __future__ import annotations

import uuid

from app.modules.rbac.context import ContextCache, build_context
from app.modules.rbac.scopes import Scope, branch_scope, institute_scope

USER = uuid.uuid4()
INST_A = uuid.uuid4()
INST_B = uuid.uuid4()
BRANCH_A1 = uuid.uuid4()
BRANCH_A2 = uuid.uuid4()


def rows(*entries):
    """(role_key, role_name, rank, institute_id, branch_id, permission_key)."""
    return list(entries)


def test_grants_are_grouped_by_permission() -> None:
    ctx = build_context(
        USER,
        rows(
            ("branch_admin", "Branch Admin", 50, INST_A, BRANCH_A1, "user:read"),
            ("branch_admin", "Branch Admin", 50, INST_A, BRANCH_A1, "user:invite"),
        ),
    )
    assert ctx.permissions == {"user:read", "user:invite"}
    assert ctx.scopes_for("user:read") == (branch_scope(INST_A, BRANCH_A1),)


def test_the_same_permission_from_two_roles_is_deduplicated() -> None:
    ctx = build_context(
        USER,
        rows(
            ("institute_admin", "Institute Admin", 70, INST_A, None, "user:read"),
            ("faculty", "Faculty", 30, INST_A, None, "user:read"),
        ),
    )
    assert ctx.scopes_for("user:read") == (institute_scope(INST_A),)


def test_one_role_at_two_scopes_produces_two_assignments() -> None:
    ctx = build_context(
        USER,
        rows(
            ("branch_admin", "Branch Admin", 50, INST_A, BRANCH_A1, "class:read"),
            ("branch_admin", "Branch Admin", 50, INST_A, BRANCH_A2, "class:read"),
        ),
    )
    assert len(ctx.assignments) == 2
    assert set(ctx.scopes_for("class:read")) == {
        branch_scope(INST_A, BRANCH_A1),
        branch_scope(INST_A, BRANCH_A2),
    }


def test_can_respects_scope_containment() -> None:
    ctx = build_context(
        USER, rows(("branch_admin", "Branch Admin", 50, INST_A, BRANCH_A1, "user:invite"))
    )
    assert ctx.can("user:invite", branch_scope(INST_A, BRANCH_A1))
    assert not ctx.can("user:invite", branch_scope(INST_A, BRANCH_A2))
    assert not ctx.can("user:invite", institute_scope(INST_A))
    assert not ctx.can("user:invite", institute_scope(INST_B))


def test_holds_is_scope_blind_and_can_is_not() -> None:
    """``holds`` is the cheap pre-filter; it must never be mistaken for authorization."""
    ctx = build_context(
        USER, rows(("branch_admin", "Branch Admin", 50, INST_A, BRANCH_A1, "user:invite"))
    )
    assert ctx.holds("user:invite")
    assert not ctx.can("user:invite", institute_scope(INST_B))


def test_max_rank_within_is_scoped_not_global() -> None:
    """The no-escalation check must not let a Branch Admin of A act senior in B."""
    ctx = build_context(
        USER,
        rows(
            ("branch_admin", "Branch Admin", 50, INST_A, BRANCH_A1, "role:assign"),
            ("student", "Student", 10, INST_B, None, "profile:read"),
        ),
    )
    assert ctx.max_rank == 50
    assert ctx.max_rank_within(branch_scope(INST_A, BRANCH_A1)) == 50
    assert ctx.max_rank_within(branch_scope(INST_A, BRANCH_A2)) == 0
    assert ctx.max_rank_within(institute_scope(INST_B)) == 10


def test_platform_staff_detected_from_a_platform_scoped_assignment() -> None:
    staff = build_context(USER, rows(("super_admin", "Super Admin", 100, None, None, "user:read")))
    tenant = build_context(
        USER, rows(("institute_admin", "Institute Admin", 70, INST_A, None, "user:read"))
    )
    assert staff.is_platform_staff
    assert not tenant.is_platform_staff


def test_a_user_with_no_roles_can_do_nothing() -> None:
    ctx = build_context(USER, [])
    assert ctx.permissions == frozenset()
    assert ctx.max_rank == 0
    assert not ctx.can("user:read", Scope())


def test_institute_ids_excludes_platform_assignments() -> None:
    ctx = build_context(
        USER,
        rows(
            ("super_admin", "Super Admin", 100, None, None, "user:read"),
            ("faculty", "Faculty", 30, INST_A, BRANCH_A1, "class:read"),
        ),
    )
    assert ctx.institute_ids == frozenset({INST_A})


# ----------------------------------------------------------------------------- cache


def _ctx() -> object:
    return build_context(USER, rows(("student", "Student", 10, INST_A, None, "profile:read")))


def test_cache_returns_what_was_stored() -> None:
    cache = ContextCache(ttl_seconds=60, max_entries=10)
    stored = _ctx()
    cache.put(USER, stored)
    assert cache.get(USER) is stored


def test_cache_misses_for_an_unknown_user() -> None:
    assert ContextCache(ttl_seconds=60, max_entries=10).get(uuid.uuid4()) is None


def test_expired_entries_are_not_returned() -> None:
    cache = ContextCache(ttl_seconds=0, max_entries=10)
    cache.put(USER, _ctx())
    assert cache.get(USER) is None


def test_invalidate_takes_effect_immediately() -> None:
    """A revoked role must not survive in cache until the TTL runs out."""
    cache = ContextCache(ttl_seconds=600, max_entries=10)
    cache.put(USER, _ctx())
    cache.invalidate(USER)
    assert cache.get(USER) is None


def test_cache_never_grows_past_its_ceiling() -> None:
    """Unbounded caching of every user who ever logs in is a memory leak."""
    cache = ContextCache(ttl_seconds=600, max_entries=5)
    for _ in range(50):
        cache.put(uuid.uuid4(), _ctx())
    assert len(cache._entries) <= 5


def test_eviction_prefers_dropping_expired_entries() -> None:
    cache = ContextCache(ttl_seconds=0, max_entries=2)
    for _ in range(3):
        cache.put(uuid.uuid4(), _ctx())
    assert len(cache._entries) <= 2


# --------------------------------------------------- explicit deny truth table


def _ctx(grants=(), personal=()):
    """Build a context from role rows and personal grant rows."""
    from app.modules.rbac.context import build_context

    rows = [("institute_admin", "Institute Admin", 70, i, b, p) for p, i, b in grants]
    return build_context(uuid.uuid4(), rows, personal)


def test_a_deny_at_the_target_scope_refuses():
    inst, branch = uuid.uuid4(), uuid.uuid4()
    ctx = _ctx(
        grants=[("user:read", inst, None)],
        personal=[("user:read", "deny", inst, branch)],
    )
    assert ctx.can("user:read", Scope(inst, branch)) is False


def test_a_deny_on_one_branch_leaves_a_sibling_alone():
    inst, mca, bca = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ctx = _ctx(
        grants=[("user:read", inst, None)],
        personal=[("user:read", "deny", inst, mca)],
    )
    assert ctx.can("user:read", Scope(inst, bca)) is True


def test_a_branch_deny_also_refuses_the_institute_wide_request():
    """Overlap, not containment. The wider request would otherwise reach the blocked
    branch, so refusing it is the only safe answer."""
    inst, mca = uuid.uuid4(), uuid.uuid4()
    ctx = _ctx(
        grants=[("user:read", inst, None)],
        personal=[("user:read", "deny", inst, mca)],
    )
    assert ctx.can("user:read", Scope(inst)) is False


def test_a_deny_beats_a_platform_wide_grant():
    """The property the whole feature rests on: no role out-votes a block."""
    inst = uuid.uuid4()
    ctx = _ctx(grants=[("user:read", None, None)], personal=[("user:read", "deny", inst, None)])
    assert ctx.can("user:read", Scope(inst)) is False
    assert ctx.can("user:read", Scope(uuid.uuid4())) is True


def test_a_personal_allow_works_where_no_role_grants_it():
    inst, branch = uuid.uuid4(), uuid.uuid4()
    ctx = _ctx(personal=[("audit:read", "allow", inst, None)])
    assert ctx.can("audit:read", Scope(inst, branch)) is True
    assert ctx.can("audit:read", Scope()) is False, "a grant never widens upwards"
    assert "audit:read" in ctx.direct


def test_holds_survives_a_narrower_deny_but_not_a_wider_one():
    inst, branch = uuid.uuid4(), uuid.uuid4()
    narrowed = _ctx(
        grants=[("user:read", inst, None)], personal=[("user:read", "deny", inst, branch)]
    )
    assert narrowed.holds("user:read") is True

    wiped = _ctx(grants=[("user:read", inst, None)], personal=[("user:read", "deny", None, None)])
    assert wiped.holds("user:read") is False
    assert "user:read" not in wiped.permissions
