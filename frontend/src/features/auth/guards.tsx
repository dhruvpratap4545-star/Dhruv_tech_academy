import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { Spinner } from "@/components/Spinner";
import { useAuth } from "@/features/auth/useAuth";
import type { Permission } from "@/lib/permissions";
import { can } from "@/lib/permissions";

/**
 * Gate for signed-in routes.
 *
 * Waits for `/me` to resolve before deciding. Redirecting while the answer is unknown
 * would bounce every signed-in user to the login page on a hard refresh.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, resolved } = useAuth();
  const location = useLocation();

  if (!resolved) return <FullPageSpinner />;
  if (!user) {
    // Remember where they were headed so login can send them back.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

/** Hides a whole route behind a permission. Cosmetic — the API still enforces it. */
export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const { user, resolved } = useAuth();

  if (!resolved) return <FullPageSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (!can(user, permission)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** Keeps signed-in users away from login and sign-up. */
export function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { user, resolved } = useAuth();
  if (!resolved) return <FullPageSpinner />;
  if (user) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function FullPageSpinner() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-surface">
      <Spinner className="size-7" />
    </div>
  );
}
