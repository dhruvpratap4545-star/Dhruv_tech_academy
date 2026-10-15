"""The seed catalogue must stay consistent with PRD §3 and §5.3."""

from app.modules.rbac import catalog


def test_every_role_permission_key_exists() -> None:
    known = {p.key for p in catalog.PERMISSIONS}
    for role_key, keys in catalog.ROLE_PERMISSIONS.items():
        unknown = set(keys) - known
        assert not unknown, f"{role_key} references unknown permissions: {sorted(unknown)}"


def test_every_role_has_a_permission_set() -> None:
    assert {r.key for r in catalog.ROLES} == set(catalog.ROLE_PERMISSIONS)


def test_ranks_are_unique_and_ordered_super_admin_highest() -> None:
    ranks = [r.rank for r in catalog.ROLES]
    assert len(ranks) == len(set(ranks))
    assert catalog.ROLES_BY_KEY[catalog.SUPER_ADMIN].rank == max(ranks)


def test_only_super_admin_manages_platform_admins() -> None:
    holders = [
        key for key, perms in catalog.ROLE_PERMISSIONS.items() if "platform_admin:manage" in perms
    ]
    assert holders == [catalog.SUPER_ADMIN]


def test_students_cannot_invite_or_change_status() -> None:
    student = set(catalog.ROLE_PERMISSIONS[catalog.STUDENT])
    assert not student & {"user:invite", "user:update_status", "role:assign", "audit:read"}


def test_faculty_cannot_manage_branches_sessions_or_audit() -> None:
    faculty = set(catalog.ROLE_PERMISSIONS[catalog.FACULTY])
    assert not faculty & {
        "branch:create",
        "session:create",
        "class:create",
        "class_faculty:manage",
        "audit:read",
        "user:update_status",
    }
