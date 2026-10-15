"""The role and permission catalogue for Milestone 1 — straight from PRD §3 and §5.3.

These are *seed data*, not logic: ``app.core.seed`` writes them into the ``roles``,
``permissions`` and ``role_permissions`` tables, and the authorization engine reads
them back from the database. Adding a module later means adding rows here (and a
migration-free seed run), never editing the engine — see PRD §5.4.

Rank implements the no-escalation rule (PRD §3.1): a user can only grant a role whose
rank is strictly lower than the highest rank they hold in that scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ScopeLevel = Literal["platform", "institute", "branch"]

SUPER_ADMIN = "super_admin"
PLATFORM_ADMIN = "platform_admin"
ORG_ADMIN = "org_admin"
INSTITUTE_ADMIN = "institute_admin"
BRANCH_ADMIN = "branch_admin"
FACULTY = "faculty"
STUDENT = "student"
PARENT = "parent"

CORE_MODULE = "core"


@dataclass(frozen=True)
class RoleDef:
    key: str
    name: str
    scope_level: ScopeLevel
    rank: int
    is_system: bool = True
    is_active: bool = True


@dataclass(frozen=True)
class PermissionDef:
    """One thing a person can be allowed to do.

    ``group`` exists for the UI only: a flat list of thirty keys is unreadable, and the
    grouping someone needs when *reviewing* access ("what can they do to people?") is not
    the module boundary the engine cares about.
    """

    key: str
    module_key: str
    description: str
    group: str = "Other"

    @property
    def resource(self) -> str:
        return self.key.split(":", 1)[0]

    @property
    def action(self) -> str:
        return self.key.split(":", 1)[1]


ROLES: tuple[RoleDef, ...] = (
    RoleDef(SUPER_ADMIN, "Super Admin", "platform", 100),
    RoleDef(PLATFORM_ADMIN, "Platform Admin", "platform", 90),
    # Between Platform Admin and Institute Admin: everything an Institute Admin can do,
    # across every institute in one organisation, and nothing outside it.
    RoleDef(ORG_ADMIN, "Organisation Admin", "organisation", 80),
    RoleDef(INSTITUTE_ADMIN, "Institute Admin", "institute", 70),
    RoleDef(BRANCH_ADMIN, "Branch Admin", "branch", 50),
    RoleDef(FACULTY, "Faculty", "branch", 30),
    RoleDef(STUDENT, "Student", "institute", 10),
    RoleDef(PARENT, "Parent / Guardian", "institute", 20),
)

# The heading these permissions appear under in the matrix. Called "Structure" rather
# than "Organisation" because Organisation is now a level in the hierarchy, and one word
# meaning two things in the same screen is how an administrator ticks the wrong box.
STRUCTURE = "Structure"
PEOPLE = "People"
ACCESS = "Access control"
AUDIT = "Audit"
ACCOUNT = "Your account"

PERMISSIONS: tuple[PermissionDef, ...] = (
    PermissionDef("organisation:create", CORE_MODULE, "Create an organisation", STRUCTURE),
    PermissionDef(
        "organisation:read", CORE_MODULE, "View an organisation and its institutes", STRUCTURE
    ),
    PermissionDef("organisation:update", CORE_MODULE, "Edit an organisation", STRUCTURE),
    PermissionDef("organisation:archive", CORE_MODULE, "Archive an organisation", STRUCTURE),
    PermissionDef("institute:create", CORE_MODULE, "Create an institute", STRUCTURE),
    PermissionDef("institute:read", CORE_MODULE, "View institute profile", STRUCTURE),
    PermissionDef("institute:update", CORE_MODULE, "Edit institute profile", STRUCTURE),
    PermissionDef("institute:archive", CORE_MODULE, "Archive an institute", STRUCTURE),
    PermissionDef(
        "module:enable", CORE_MODULE, "Enable or disable a module for an institute", STRUCTURE
    ),
    PermissionDef("branch:create", CORE_MODULE, "Create a branch", STRUCTURE),
    PermissionDef("branch:read", CORE_MODULE, "View branches", STRUCTURE),
    PermissionDef("branch:update", CORE_MODULE, "Edit a branch", STRUCTURE),
    PermissionDef("branch:archive", CORE_MODULE, "Archive a branch", STRUCTURE),
    PermissionDef("session:create", CORE_MODULE, "Create an academic session", STRUCTURE),
    PermissionDef("session:read", CORE_MODULE, "View academic sessions", STRUCTURE),
    PermissionDef("session:update", CORE_MODULE, "Edit an academic session", STRUCTURE),
    PermissionDef("class:create", CORE_MODULE, "Create a class or batch", STRUCTURE),
    PermissionDef("class:read", CORE_MODULE, "View classes", STRUCTURE),
    PermissionDef("class:update", CORE_MODULE, "Edit a class", STRUCTURE),
    PermissionDef("class:archive", CORE_MODULE, "Archive a class", STRUCTURE),
    PermissionDef("user:invite", CORE_MODULE, "Invite a user", PEOPLE),
    PermissionDef("user:read", CORE_MODULE, "View users in scope", PEOPLE),
    PermissionDef("user:update_status", CORE_MODULE, "Suspend or re-activate a user", PEOPLE),
    PermissionDef("enrollment:manage", CORE_MODULE, "Enrol or remove students in a class", PEOPLE),
    PermissionDef(
        "class_faculty:manage", CORE_MODULE, "Assign or remove faculty on a class", PEOPLE
    ),
    PermissionDef("role:assign", CORE_MODULE, "Assign a role at a scope", ACCESS),
    PermissionDef("role:revoke", CORE_MODULE, "Revoke a role assignment", ACCESS),
    PermissionDef("role:read", CORE_MODULE, "View roles and what they allow", ACCESS),
    PermissionDef("role:manage", CORE_MODULE, "Create, edit and archive custom roles", ACCESS),
    PermissionDef(
        "permission:grant",
        CORE_MODULE,
        "Give one person an extra permission, or block one for them",
        ACCESS,
    ),
    PermissionDef("platform_admin:manage", CORE_MODULE, "Create or remove Platform Admins", ACCESS),
    PermissionDef("audit:read", CORE_MODULE, "Read the audit log for a scope", AUDIT),
    PermissionDef("profile:read", CORE_MODULE, "Read own profile", ACCOUNT),
    PermissionDef("profile:update", CORE_MODULE, "Update own profile and preferences", ACCOUNT),
)

PERMISSIONS_BY_KEY = {p.key: p for p in PERMISSIONS}

_ALL = tuple(p.key for p in PERMISSIONS)

# Which permission keys each role holds. *Where* a role may use a permission comes from
# the scope of its assignment plus the membership checks in PRD §5.2 steps 3–4 — the
# "Own inst. / Own br. / Assigned" columns of the PRD matrix are scope, not separate keys.
ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    SUPER_ADMIN: _ALL,
    PLATFORM_ADMIN: tuple(k for k in _ALL if k != "platform_admin:manage"),
    # Everything an Institute Admin may do, plus the organisation itself and the right to
    # add an institute to it. Derived from INSTITUTE_ADMIN below rather than retyped, so a
    # permission given to an Institute Admin in a later release is not silently withheld
    # from the person who runs four of them.
    #
    # `organisation:create` is deliberately absent: creating a *new* organisation is a
    # platform decision, not something one organisation's administrator does.
    ORG_ADMIN: (),  # filled in below, once INSTITUTE_ADMIN exists
    INSTITUTE_ADMIN: (
        "institute:read",
        "institute:update",
        "branch:create",
        "branch:read",
        "branch:update",
        "branch:archive",
        "session:create",
        "session:read",
        "session:update",
        "class:create",
        "class:read",
        "class:update",
        "class:archive",
        "user:invite",
        "user:read",
        "user:update_status",
        "role:assign",
        "role:revoke",
        "role:read",
        "role:manage",
        "permission:grant",
        "enrollment:manage",
        "class_faculty:manage",
        "audit:read",
        "profile:read",
        "profile:update",
    ),
    BRANCH_ADMIN: (
        "institute:read",
        "branch:read",
        "session:create",
        "session:read",
        "session:update",
        "class:create",
        "class:read",
        "class:update",
        "class:archive",
        "user:invite",
        "user:read",
        "user:update_status",
        "role:assign",
        "role:revoke",
        "role:read",
        "enrollment:manage",
        "class_faculty:manage",
        # `audit:read` is deliberately not here. An audit entry records the institute it
        # happened in and nothing finer, so there is no way to show a Branch Admin their
        # own branch's history without also showing them the principal's actions and every
        # other branch's. Granting a permission that can only be honoured too widely is
        # worse than withholding it.
        #
        # It is not gone, only not assumed: a college that wants its branch heads to read
        # the log can switch it on for themselves in Roles & permissions, which applies to
        # that college alone.
        "profile:read",
        "profile:update",
    ),
    FACULTY: (
        "institute:read",
        "branch:read",
        "class:read",
        "user:invite",
        "user:read",
        "role:assign",
        "enrollment:manage",
        "profile:read",
        "profile:update",
    ),
    STUDENT: (
        "institute:read",
        "class:read",
        "user:read",
        "profile:read",
        "profile:update",
    ),
    PARENT: (
        # Deliberately narrow. A parent reads their own children and nothing else, and the
        # narrowing is not done by this list — `user:read` here would otherwise mean every
        # student in the institute. The guardian link is what confines it, exactly as the
        # class link confines a faculty member (PRD §5.2 step 4).
        "user:read",
        "institute:read",
        "class:read",
        "profile:read",
        "profile:update",
    ),
}

ROLES_BY_KEY = {role.key: role for role in ROLES}

# Built-in institute that holds self-registered learners (PRD §2).
DIRECT_INSTITUTE_CODE = "DIRECT"
DIRECT_INSTITUTE_NAME = "Dhruv Online Academy – Direct"


# Resolved here rather than inline, because a dict literal cannot read its own entries.
ROLE_PERMISSIONS[ORG_ADMIN] = (
    "organisation:read",
    "organisation:update",
    # Adding a fifth college to JSPM is the organisation administrator's job, not the
    # platform's. The scope check confines it to their own organisation.
    "institute:create",
    *ROLE_PERMISSIONS[INSTITUTE_ADMIN],
)


def max_grantable_rank(holder_rank: int) -> int:
    """Highest role rank a holder may grant: strictly below their own (PRD §3.1)."""
    return holder_rank - 1


def grantable_ceiling(holder_rank: int) -> int:
    """Highest rank anyone may hand out: strictly below their own, with no exceptions.

    Super Admin used to be exempt, so one Super Admin could appoint another. That is gone.
    Every role now obeys the same sentence — you cannot give away your own level or
    anything above it — which is the rule administrators already believe is in force, and
    the only one that reads the same whichever role you happen to hold.

    Appointing a Super Admin has not become impossible, it has moved off the web app
    entirely: `python -m app.cli grant-super-admin <email>`, run by whoever has access to
    the server. A second owner is a decision about who controls the platform, not a task
    for a screen that a stolen session could reach.

    This lives in one place on purpose. The authorization check and the "roles you may
    give" list must agree exactly: a list narrower than the check hides a legitimate
    action, and one that is wider offers a choice the server will refuse.
    """
    return max_grantable_rank(holder_rank)
