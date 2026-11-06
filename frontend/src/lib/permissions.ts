/**
 * Permission helpers for the UI.
 *
 * **These decide what to *show*, never what is *allowed*.** The backend re-checks every
 * request against the target's scope (PRD §5.2), and it is the only real answer. Hiding a
 * button is a courtesy — it stops people clicking things that would fail — not a control.
 *
 * `/me` returns the flat set of permission keys the user holds *somewhere*. It carries no
 * scope, so it can tell you "this person invites users" but never "in which branch".
 * Anything scope-sensitive has to come from the server.
 */

import type { CurrentUser } from "@/features/auth/types";

export type Permission =
  | "organisation:create"
  | "organisation:read"
  | "organisation:update"
  | "organisation:archive"
  | "institute:create"
  | "institute:read"
  | "institute:update"
  | "institute:archive"
  | "branch:create"
  | "branch:read"
  | "branch:update"
  | "branch:archive"
  | "module:enable"
  | "session:create"
  | "session:read"
  | "session:update"
  | "class:create"
  | "class:read"
  | "class:update"
  | "class:archive"
  | "user:invite"
  | "user:read"
  | "user:update_status"
  | "role:assign"
  | "role:revoke"
  | "role:read"
  | "role:manage"
  | "permission:grant"
  | "enrollment:manage"
  | "class_faculty:manage"
  | "audit:read"
  | "profile:read"
  | "profile:update"
  | "platform_admin:manage"
  // Phase 3, Milestone 1
  | "ai:manage"
  | "ai:usage_read"
  | "library:read"
  | "library:contribute"
  | "library:manage"
  | "library:publish"
  | "homework:manage"
  | "homework:read"
  | "homework:submit"
  | "homework:report";

export function can(user: CurrentUser | null | undefined, permission: Permission): boolean {
  return Boolean(user?.permissions.includes(permission));
}

export function canAny(user: CurrentUser | null | undefined, permissions: Permission[]): boolean {
  return permissions.some((permission) => can(user, permission));
}

/**
 * Ranks for the six built-ins, for labelling only — never to authorise.
 *
 * A custom role's key is not in here by definition, so anything that needs a rank reads
 * `role.rank` from the server instead. This table survives only for the places that start
 * from a key and have no assignment to hand, such as the invite form's role list.
 */
export const ROLE_RANK: Record<string, number> = {
  super_admin: 100,
  platform_admin: 90,
  org_admin: 80,
  institute_admin: 70,
  branch_admin: 50,
  faculty: 30,
  parent: 20,
  student: 10,
};

export const ROLE_LABEL: Record<string, string> = {
  super_admin: "Super Admin",
  platform_admin: "Platform Admin",
  org_admin: "Organisation Admin",
  institute_admin: "Institute Admin",
  branch_admin: "Branch Admin",
  faculty: "Faculty",
  parent: "Parent",
  student: "Student",
};

/**
 * What a role needs before it can be granted (PRD §3.1), so the invite form can ask for
 * the right fields and explain itself.
 *
 * The backend enforces all of this; this table only shapes the form.
 */
export const ROLE_REQUIREMENTS: Record<
  string,
  { institute: boolean; branch: boolean; classes: "none" | "optional" | "required" }
> = {
  super_admin: { institute: false, branch: false, classes: "none" },
  platform_admin: { institute: false, branch: false, classes: "none" },
  org_admin: { institute: false, branch: false, classes: "none" },
  institute_admin: { institute: true, branch: false, classes: "none" },
  branch_admin: { institute: true, branch: true, classes: "none" },
  faculty: { institute: true, branch: true, classes: "optional" },
  parent: { institute: true, branch: false, classes: "none" },
  student: { institute: true, branch: false, classes: "optional" },
};

/** The highest rank the user holds anywhere. Used to explain *why* a role is unavailable. */
export function highestRank(user: CurrentUser | null | undefined): number {
  if (!user || user.roles.length === 0) return 0;
  // `role.rank` comes from the server. Looking it up from the key here would score every
  // custom role zero and quietly get "who outranks whom" wrong.
  return Math.max(...user.roles.map((role) => role.rank));
}

/**
 * True when the user holds a platform-scoped role — they see every institute.
 *
 * A platform role names neither an institute nor an organisation. Testing only for "no
 * institute" also matched organisation-wide roles, which name no institute either, and
 * handed an Organisation Admin the platform-only choices.
 */
export function isPlatformStaff(user: CurrentUser | null | undefined): boolean {
  return Boolean(
    user?.roles.some((role) => role.institute_id === null && role.organisation_id === null),
  );
}

/** True when the user holds a role across a whole organisation (and so several institutes). */
export function isOrganisationAdmin(user: CurrentUser | null | undefined): boolean {
  return Boolean(user?.roles.some((role) => role.institute_id === null && role.organisation_id));
}

/** The organisations the user holds an organisation-wide role in. */
export function organisationIds(user: CurrentUser | null | undefined): string[] {
  return [
    ...new Set(
      (user?.roles ?? [])
        .filter((role) => role.institute_id === null && role.organisation_id)
        .map((role) => role.organisation_id!),
    ),
  ];
}

/**
 * Should the user pick an institute rather than have it filled in?
 *
 * Platform staff and organisation admins see several institutes through a role that names
 * none of them, and an administrator may hold roles in more than one. Only somebody pinned
 * to exactly one institute can have it filled in for them.
 */
export function picksInstitute(user: CurrentUser | null | undefined): boolean {
  return (
    isPlatformStaff(user) || isOrganisationAdmin(user) || (user?.institute_ids.length ?? 0) > 1
  );
}

/**
 * Is every role this person holds a learner's or a parent's?
 *
 * They have read access to bits of the structure (their own class, their child's), but the
 * people and hierarchy screens are administration, and offering them only shows a page of
 * things they cannot change.
 */
export function isLearnerOrParentOnly(user: CurrentUser | null | undefined): boolean {
  if (!user || user.roles.length === 0) return false;
  return user.roles.every((role) => role.role_key === "student" || role.role_key === "parent");
}

/**
 * Is this person only a teacher?
 *
 * Matters for the invite form: a faculty-level inviter must name at least one of their
 * own classes, because their authority is the classes they teach, not the branch they sit
 * in. The backend returns 422 otherwise, so the form asks for it up front.
 */
export function isFacultyOnly(user: CurrentUser | null | undefined): boolean {
  if (!user || user.roles.length === 0) return false;
  return highestRank(user) <= (ROLE_RANK.faculty ?? 30);
}

/**
 * Where a role applies, in words: "ABC College · MCA", "Platform".
 *
 * The names come from the API alongside the ids, so this never needs a lookup request.
 */
export function roleScopeLabel(role: {
  organisation_id?: string | null;
  institute_id: string | null;
  branch_id: string | null;
  organisation_name?: string | null;
  institute_name?: string | null;
  branch_name?: string | null;
}): string {
  // Innermost first, because that is what the role actually is. An organisation-wide role
  // names no institute, which is not the same as naming no scope at all — reading it as
  // "Platform" would tell somebody running four colleges that they run the product.
  if (role.institute_id) {
    const institute = role.institute_name ?? "Institute";
    return role.branch_name ? `${institute} · ${role.branch_name}` : institute;
  }
  if (role.organisation_id) return role.organisation_name ?? "Organisation";
  return "Platform";
}

/**
 * A stable React key for one role assignment. The same role can be held in two
 * organisations, which name no institute or branch, so the organisation is part of it.
 */
export function roleAssignmentKey(role: {
  role_key: string;
  organisation_id?: string | null;
  institute_id: string | null;
  branch_id: string | null;
}): string {
  return `${role.role_key}-${role.branch_id ?? role.institute_id ?? role.organisation_id ?? "platform"}`;
}

/** The caller's own scope, for the sidebar. Their most senior role wins. */
export function scopeLabel(user: CurrentUser): string {
  if (user.roles.length === 0) return "No access yet";
  const senior = [...user.roles].sort((a, b) => b.rank - a.rank)[0]!;
  return roleScopeLabel(senior);
}
