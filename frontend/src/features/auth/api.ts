import { apiFetch, cancelPendingRefresh } from "@/lib/api";

import type {
  AssignableRole,
  CurrentUser,
  LoginResponse,
  MessageResponse,
  Preferences,
  Overview,
  UserProfile,
  VerifyOtpResponse,
} from "./types";

export const meKey = ["me"] as const;

export const overviewKey = ["me", "overview"] as const;

export function fetchOverview(signal?: AbortSignal) {
  return apiFetch<Overview>("/me/overview", { signal });
}

export function fetchMe(signal?: AbortSignal) {
  return apiFetch<CurrentUser>("/me", { signal });
}

export function login(body: { email: string; password: string; remember_me: boolean }) {
  return apiFetch<LoginResponse>("/auth/login", { method: "POST", body });
}

export function register(body: {
  full_name: string;
  email: string;
  password: string;
  accept_terms: true;
}) {
  return apiFetch<LoginResponse>("/auth/register", { method: "POST", body });
}

export async function logout() {
  await apiFetch<MessageResponse>("/auth/logout", { method: "POST" });
  // Any refresh still in flight belongs to the session we just ended.
  cancelPendingRefresh();
}

export function forgotPassword(body: { email: string }) {
  return apiFetch<MessageResponse>("/auth/password/forgot", { method: "POST", body });
}

export function verifyOtp(body: { email: string; code: string }) {
  return apiFetch<VerifyOtpResponse>("/auth/password/verify-otp", { method: "POST", body });
}

export function resetPassword(body: { reset_token: string; new_password: string }) {
  return apiFetch<MessageResponse>("/auth/password/reset", { method: "POST", body });
}

export function setupPassword(body: { email: string; code: string; new_password: string }) {
  return apiFetch<MessageResponse>("/auth/password/setup", { method: "POST", body });
}

export function changePassword(body: { current_password: string; new_password: string }) {
  return apiFetch<MessageResponse>("/auth/password/change", { method: "POST", body });
}

export function updatePreferences(body: Partial<Preferences>) {
  return apiFetch<Preferences>("/me/preferences", { method: "PATCH", body });
}

/** Returns the updated profile only — not permissions. Invalidate `/me` for those. */
export function updateProfile(body: { full_name?: string; phone?: string | null }) {
  return apiFetch<UserProfile>("/me", { method: "PATCH", body });
}

/** Roles the signed-in user is allowed to hand out — the backend already filters by rank. */
export function fetchAssignableRoles() {
  return apiFetch<AssignableRole[]>("/users/roles/catalogue");
}
