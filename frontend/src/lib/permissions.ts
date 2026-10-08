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
  | "platform_admin:manage";

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
  institute_admin: 70,
  branch_admin: 50,
  faculty: 30,
  parent: 20,
  student: 10,
};

export const ROLE_LABEL: Record<string, string> = {
  super_admin: "Super Admin",
  platform_admin: "Platform Admin",
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

/** True when the user holds a platform-scoped role — they see every institute. */
export function isPlatformStaff(user: CurrentUser | null | undefined): boolean {
  return Boolean(user?.roles.some((role) => role.institute_id === null));
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
  institute_id: string | null;
  branch_id: string | null;
  institute_name?: string | null;
  branch_name?: string | null;
}): string {
  if (!role.institute_id) return "Platform";
  const institute = role.institute_name ?? "Institute";
  return role.branch_name ? `${institute} · ${role.branch_name}` : institute;
}

/** The caller's own scope, for the sidebar. Their most senior role wins. */
export function scopeLabel(user: CurrentUser): string {
  if (user.roles.length === 0) return "No access yet";
  const senior = [...user.roles].sort((a, b) => b.rank - a.rank)[0]!;
  return roleScopeLabel(senior);
}
