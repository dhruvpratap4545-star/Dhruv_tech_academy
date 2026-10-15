import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEffect } from "react";

import { fetchMe, meKey } from "@/features/auth/api";
import { AuthContext } from "@/features/auth/authContext";
import { endSession } from "@/features/auth/session";
import { useTheme } from "@/features/theme/useTheme";
import { ApiError, onSessionExpired } from "@/lib/api";

// Registered once, at module level rather than in an effect: a 401 can land before the
// first render finishes, and a handler installed later would miss it.
onSessionExpired(endSession);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { adoptTheme } = useTheme();

  const { data, isLoading, isFetched } = useQuery({
    queryKey: meKey,
    queryFn: ({ signal }) => fetchMe(signal),
    // 401 is the normal answer for a signed-out visitor, not a failure worth retrying.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status < 500) && failureCount < 2,
    staleTime: 60_000,
  });

  const savedTheme = data?.preferences.theme;

  // The server's saved theme wins once we know who this is, so the preference follows the
  // user across devices. Until then the local copy applied by index.html is in effect.
  useEffect(() => {
    if (savedTheme) adoptTheme(savedTheme);
  }, [savedTheme, adoptTheme]);

  return (
    <AuthContext
      value={{ user: data ?? null, loading: isLoading, resolved: isFetched || !isLoading }}
    >
      {children}
    </AuthContext>
  );
}
