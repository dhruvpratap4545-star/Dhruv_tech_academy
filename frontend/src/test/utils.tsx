import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { RenderOptions } from "@testing-library/react";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { AuthContext } from "@/features/auth/authContext";
import { ROLE_RANK } from "@/lib/permissions";
import type { CurrentUser, RoleAssignment, RoleKey } from "@/features/auth/types";

/** A signed-in user, overridable per test. */
export function makeUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    email: "asha@example.com",
    full_name: "Asha Rao",
    phone: null,
    status: "active",
    permissions: [],
    roles: [],
    institute_ids: [],
    preferences: { theme: "system", language: "en" },
    ...overrides,
  };
}

export function roleAssignment(
  role_key: RoleKey,
  institute_id: string | null = null,
  branch_id: string | null = null,
  names: { institute_name?: string | null; branch_name?: string | null } = {},
): RoleAssignment {
  return {
    role_key,
    role_name: role_key,
    // Mirrors the server, which now sends the rank with every assignment so custom roles
    // are ranked correctly.
    rank: ROLE_RANK[role_key] ?? 0,
    institute_id,
    branch_id,
    institute_name: names.institute_name ?? (institute_id ? "Test Institute" : null),
    branch_name: names.branch_name ?? (branch_id ? "Test Branch" : null),
  };
}

type Options = RenderOptions & {
  user?: CurrentUser | null;
  route?: string;
  resolved?: boolean;
};

/**
 * Render with router, query client and auth context.
 *
 * A fresh QueryClient per test with retries off: a shared one would leak cached results
 * between tests, and retrying a deliberately-failing request just makes failures slow.
 */
export function renderWithProviders(ui: ReactElement, options: Options = {}) {
  const { user = null, route = "/", resolved = true, ...rest } = options;

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>
          <AuthContext value={{ user, loading: false, resolved }}>{children}</AuthContext>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return { queryClient, ...render(ui, { wrapper: Wrapper, ...rest }) };
}
