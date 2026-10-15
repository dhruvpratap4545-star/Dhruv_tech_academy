import { useQueryClient } from "@tanstack/react-query";
import { use } from "react";

import { meKey } from "@/features/auth/api";
import type { AuthState } from "@/features/auth/authContext";
import { AuthContext } from "@/features/auth/authContext";
import type { CurrentUser } from "@/features/auth/types";
import type { Permission } from "@/lib/permissions";
import { can } from "@/lib/permissions";

export function useAuth(): AuthState {
  return use(AuthContext);
}

export function useCurrentUser(): CurrentUser | null {
  return use(AuthContext).user;
}

/**
 * Permission check for conditional UI.
 *
 * Decides what to *show*, never what is *allowed* — the backend re-checks every request
 * against the target's scope, and that is the only answer that counts (PRD §5.2).
 */
export function useCan(permission: Permission): boolean {
  return can(use(AuthContext).user, permission);
}

export function useInvalidateMe() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: meKey });
}
