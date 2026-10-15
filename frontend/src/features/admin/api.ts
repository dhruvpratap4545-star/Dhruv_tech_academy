import type {
  AuditEntry,
  Branch,
  ClassRow,
  Grant,
  Institute,
  MyAccess,
  Organisation,
  PermissionInfo,
  Role,
  RoleKey,
  Session,
  SearchResults,
  SigninStats,
  UserSummary,
} from "@/features/auth/types";
import type { Page } from "@/lib/api";
import { apiDownload, apiFetch, query } from "@/lib/api";

export type UserFilters = {
  search?: string;
  status?: string;
  role_key?: string;
  institute_id?: string;
  cursor?: string;
  limit?: number;
};

export const userKeys = {
  all: ["users"] as const,
  list: (filters: UserFilters) => ["users", "list", filters] as const,
  detail: (userId: string) => ["users", "detail", userId] as const,
};

export function fetchUsers(filters: UserFilters, signal?: AbortSignal) {
  return apiFetch<Page<UserSummary>>(`/users${query(filters)}`, { signal });
}

/**
 * One user, with their roles as the server currently has them.
 *
 * The list page already holds a copy, but a dialog that edits someone's roles cannot read
 * them from a row it was handed when it opened: take a role away and the row is stale,
 * so the role the person just removed is still sitting there on screen. Reading the user
 * back by id gives the dialog something that changes when it changes things.
 */
export function fetchUser(userId: string, signal?: AbortSignal) {
  return apiFetch<UserSummary>(`/users/${userId}`, { signal });
}

export type InvitePayload = {
  full_name: string;
  email: string;
  role_key: RoleKey;
  institute_id?: string;
  branch_id?: string;
  phone?: string;
  class_ids?: string[];
};

export function inviteUser(body: InvitePayload) {
  return apiFetch<{ user: UserSummary; invitation_sent: boolean }>("/users/invite", {
    method: "POST",
    body,
  });
}

export function resendInvite(userId: string) {
  return apiFetch<{ user: UserSummary }>(`/users/${userId}/resend-invite`, { method: "POST" });
}

export type RoleChange = {
  organisation_id?: string;
  role_key: RoleKey;
  institute_id?: string;
  branch_id?: string;
};

export function assignRole(userId: string, body: RoleChange) {
  return apiFetch<UserSummary>(`/users/${userId}/roles`, { method: "POST", body });
}

export function revokeRole(userId: string, body: RoleChange) {
  return apiFetch<void>(`/users/${userId}/roles`, { method: "DELETE", body });
}

export type BulkStatusResult = {
  user_id: string;
  outcome: "succeeded" | "skipped";
  reason: string | null;
  email: string | null;
};

export type BulkStatusResponse = {
  results: BulkStatusResult[];
  succeeded: number;
  skipped: number;
};

/**
 * Suspend or re-activate several people at once.
 *
 * The server checks each person separately and skips the ones the caller may not touch,
 * so a 200 does not mean everything applied — read `succeeded` and `skipped`.
 */
export function bulkUpdateStatus(
  userIds: string[],
  status: "active" | "suspended",
  reason?: string,
) {
  return apiFetch<BulkStatusResponse>("/users/bulk-status", {
    method: "POST",
    body: { user_ids: userIds, status, reason },
  });
}

export function updateUserStatus(userId: string, status: "active" | "suspended", reason?: string) {
  return apiFetch<UserSummary>(`/users/${userId}/status`, {
    method: "PATCH",
    body: { status, reason },
  });
}

// ------------------------------------------------------------------ organisation

export const organisationKeys = {
  all: ["organisations"] as const,
  list: () => ["organisations", "list"] as const,
  detail: (id: string) => ["organisations", id] as const,
};

export function fetchOrganisations(signal?: AbortSignal) {
  return apiFetch<Page<Organisation>>(`/organisations${query({ limit: 100 })}`, { signal });
}

export function fetchOrganisation(organisationId: string, signal?: AbortSignal) {
  return apiFetch<Organisation>(`/organisations/${organisationId}`, { signal });
}

export type OrganisationPayload = {
  name: string;
  code: string;
  contact_email?: string;
  logo_url?: string;
};

export function createOrganisation(body: OrganisationPayload) {
  return apiFetch<Organisation>("/organisations", { method: "POST", body });
}

export function updateOrganisation(
  organisationId: string,
  body: Partial<Omit<OrganisationPayload, "code">>,
) {
  return apiFetch<Organisation>(`/organisations/${organisationId}`, { method: "PATCH", body });
}

export function archiveOrganisation(organisationId: string) {
  return apiFetch<Organisation>(`/organisations/${organisationId}/archive`, { method: "POST" });
}

export const instituteKeys = {
  all: ["institutes"] as const,
  list: () => ["institutes", "list"] as const,
  branches: (instituteId: string) => ["institutes", instituteId, "branches"] as const,
  sessions: (instituteId: string) => ["institutes", instituteId, "sessions"] as const,
  classes: (instituteId: string, branchId?: string) =>
    ["institutes", instituteId, "classes", branchId ?? "all"] as const,
};

export function fetchInstitutes(signal?: AbortSignal) {
  return apiFetch<Page<Institute>>(`/institutes${query({ limit: 100 })}`, { signal });
}

export function fetchBranches(instituteId: string, signal?: AbortSignal) {
  return apiFetch<Page<Branch>>(
    `/institutes/${instituteId}/branches${query({ limit: 100, status: "active" })}`,
    { signal },
  );
}

export function fetchSessions(instituteId: string, signal?: AbortSignal) {
  return apiFetch<Page<Session>>(`/institutes/${instituteId}/sessions${query({ limit: 100 })}`, {
    signal,
  });
}

export function fetchClasses(instituteId: string, branchId?: string, signal?: AbortSignal) {
  return apiFetch<Page<ClassRow>>(
    `/institutes/${instituteId}/classes${query({ limit: 100, status: "active", branch_id: branchId })}`,
    { signal },
  );
}

export type CreateInstituteWithAdminPayload = {
  institute: {
    name: string;
    code: string;
    type: "school" | "college" | "coaching" | "academy";
    contact_email?: string;
  };
  admin_full_name: string;
  admin_email: string;
};

export function createInstituteWithAdmin(body: CreateInstituteWithAdminPayload) {
  return apiFetch<{ institute: Institute; admin_user_id: string; admin_email: string }>(
    "/institutes/with-admin",
    { method: "POST", body },
  );
}

// ------------------------------------------------------------------------ audit

export type AuditFilters = { action?: string; cursor?: string; limit?: number };

export const auditKeys = {
  all: ["audit"] as const,
  list: (filters: AuditFilters) => ["audit", "list", filters] as const,
};

export function fetchAuditLog(filters: AuditFilters, signal?: AbortSignal) {
  return apiFetch<Page<AuditEntry>>(`/audit-logs${query(filters)}`, { signal });
}

// --------------------------------------------------------------- sign-in statistics

export const statsKeys = {
  signins: (days: number) => ["audit", "stats", days] as const,
};

export function fetchSigninStats(days: number, signal?: AbortSignal) {
  return apiFetch<SigninStats>(`/audit-logs/stats${query({ days })}`, { signal });
}

// ----------------------------------------------------------------- access control

export const accessKeys = {
  roles: (instituteId?: string) => ["access", "roles", instituteId ?? "all"] as const,
  permissions: () => ["access", "permissions"] as const,
  grants: (userId: string) => ["access", "grants", userId] as const,
  myAccess: () => ["access", "me"] as const,
};

export function fetchRoles(instituteId?: string, signal?: AbortSignal) {
  return apiFetch<Role[]>(`/roles${query({ institute_id: instituteId })}`, { signal });
}

/**
 * Set what a role allows inside one institute.
 *
 * Send the full effective set, not a difference — the server works the difference out.
 * Sending exactly the role's own definition clears the customisation.
 */
export function setInstituteRolePermissions(
  roleId: string,
  instituteId: string,
  permissions: string[],
) {
  return apiFetch<Role>(`/roles/${roleId}/institutes/${instituteId}/permissions`, {
    method: "PUT",
    body: { permissions },
  });
}

export function fetchPermissions(signal?: AbortSignal) {
  return apiFetch<PermissionInfo[]>("/permissions", { signal });
}

export function fetchMyAccess(signal?: AbortSignal) {
  return apiFetch<MyAccess>("/me/access", { signal });
}

export type RolePayload = {
  name: string;
  description?: string;
  scope_level: "institute" | "branch";
  rank: number;
  institute_id: string;
  permissions: string[];
};

export function createRole(body: RolePayload) {
  return apiFetch<Role>("/roles", { method: "POST", body });
}

export function updateRole(
  roleId: string,
  body: { name?: string; description?: string; permissions?: string[] },
) {
  return apiFetch<Role>(`/roles/${roleId}`, { method: "PATCH", body });
}

/** What happened when a custom role was removed. Two outcomes, behind one button. */
export type RoleRemoval = {
  id: string;
  key: string;
  name: string;
  /** True when the row is gone. False when it was retired and the definition is kept. */
  deleted: boolean;
  /** A sentence for the person who pressed the button, saying which one they got. */
  message: string;
};

/**
 * Remove a custom role.
 *
 * The server decides between deleting and retiring, because only the server knows whether
 * anybody has ever held it. A role nobody was ever given is deleted outright and its name
 * becomes free again; one with a history is retired, so the audit log can still say what
 * it allowed. The response says which, and the screen repeats it rather than claiming the
 * one that sounds better.
 */
export function removeRole(roleId: string) {
  return apiFetch<RoleRemoval>(`/roles/${roleId}`, { method: "DELETE" });
}

// --------------------------------------------------------------------------- guardians

export type Guardian = {
  user_id: string;
  full_name: string;
  email: string;
  status: string;
  relationship: string | null;
  is_primary: boolean;
  /** Null until the adult has completed setup at their own address. */
  verified_at: string | null;
};

export type Child = {
  user_id: string;
  full_name: string;
  email: string;
  status: string;
  relationship: string | null;
};

export const guardianKeys = {
  of: (studentId: string) => ["users", studentId, "guardians"] as const,
  mine: ["me", "children"] as const,
};

export function fetchGuardians(studentId: string, signal?: AbortSignal) {
  return apiFetch<Guardian[]>(`/users/${studentId}/guardians`, { signal });
}

export type GuardianLink = {
  email: string;
  full_name?: string;
  relationship?: string;
  is_primary?: boolean;
};

export function linkGuardian(studentId: string, body: GuardianLink) {
  return apiFetch<UserSummary>(`/users/${studentId}/guardians`, { method: "POST", body });
}

export function unlinkGuardian(studentId: string, parentId: string) {
  return apiFetch<void>(`/users/${studentId}/guardians/${parentId}`, { method: "DELETE" });
}

export function fetchMyChildren(signal?: AbortSignal) {
  return apiFetch<Child[]>("/me/children", { signal });
}

export function fetchGrants(userId: string, signal?: AbortSignal) {
  return apiFetch<Grant[]>(`/users/${userId}/grants`, { signal });
}

export type GrantPayload = {
  permission: string;
  effect: "allow" | "deny";
  institute_id?: string;
  branch_id?: string;
  reason: string;
  expires_at?: string;
};

export function createGrant(userId: string, body: GrantPayload) {
  return apiFetch<Grant>(`/users/${userId}/grants`, { method: "POST", body });
}

export function revokeGrant(userId: string, grantId: string) {
  return apiFetch<void>(`/users/${userId}/grants/${grantId}`, { method: "DELETE" });
}

// ------------------------------------------------------------------------ search

export const searchKeys = {
  query: (term: string) => ["search", term] as const,
};

export function globalSearch(term: string, signal?: AbortSignal) {
  return apiFetch<SearchResults>(`/search${query({ q: term })}`, { signal });
}

// ---------------------------------------------------------------- bulk invitation

export type BulkInviteRow = {
  /** The row number Excel shows, so the person can go and look at it. */
  row: number;
  full_name: string;
  email: string;
  outcome: "invited" | "ready" | "skipped";
  reason: string | null;
  branch: string | null;
  class_name: string | null;
  parent_email: string | null;
  parent_outcome: "invited" | "linked" | "ready" | "skipped" | null;
  parent_reason: string | null;
};

export type BulkInviteReport = {
  dry_run: boolean;
  institute_id: string;
  rows: BulkInviteRow[];
  invited: number;
  parents: number;
  skipped: number;
};

export function downloadInviteTemplate() {
  return apiDownload("/users/bulk-invite/template", "invite-learners.xlsx");
}

/**
 * Upload the file. `preview` reads it and reports what would happen without writing
 * anything; without it, the invitations are sent.
 */
export function bulkInvite(file: File, instituteId: string | null, preview: boolean) {
  const body = new FormData();
  body.append("file", file);
  if (instituteId) body.append("institute_id", instituteId);
  return apiFetch<BulkInviteReport>(`/users/bulk-invite${preview ? "/preview" : ""}`, {
    method: "POST",
    body,
  });
}
