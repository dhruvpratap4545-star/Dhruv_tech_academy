import type {
  AuditEntry,
  Branch,
  ClassRow,
  Grant,
  Institute,
  MyAccess,
  PermissionInfo,
  Role,
  RoleKey,
  Session,
  SearchResults,
  SigninStats,
  UserSummary,
} from "@/features/auth/types";
import type { Page } from "@/lib/api";
import { apiFetch, query } from "@/lib/api";

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
};

export function fetchUsers(filters: UserFilters, signal?: AbortSignal) {
  return apiFetch<Page<UserSummary>>(`/users${query(filters)}`, { signal });
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

export function archiveRole(roleId: string) {
  return apiFetch<Role>(`/roles/${roleId}/archive`, { method: "POST" });
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
