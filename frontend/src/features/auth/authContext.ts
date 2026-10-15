import { createContext } from "react";

import type { CurrentUser } from "@/features/auth/types";

export type AuthState = {
  user: CurrentUser | null;
  loading: boolean;
  /** True once we know the answer either way — guards must not redirect before this. */
  resolved: boolean;
};

export const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  resolved: false,
});
