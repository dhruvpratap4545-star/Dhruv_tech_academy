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

/**
 * Keeps signed-in users away from login and sign-up.
 *
 * It has to send them to the same place the login form would, not always to the
 * dashboard. `RequireAuth` records where somebody was headed before bouncing them here,
 * and the login form reads it back and navigates there — but this guard is still mounted
 * around the login route when that happens, sees the user appear, and redirects to "/"
 * on top of it. The deep link was remembered, carried, used, and then overwritten a
 * frame later; opening a bookmark of the activity log and signing in always landed on
 * the dashboard.
 *
 * Reading the same state here means whichever of the two wins the race, the destination
 * is the same one.
 */
export function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { user, resolved } = useAuth();
  const location = useLocation();
  const intended = (location.state as { from?: string } | null)?.from;

  if (!resolved) return <FullPageSpinner />;
  if (user) return <Navigate to={intended ?? "/"} replace />;
  return <>{children}</>;
}

function FullPageSpinner() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-surface">
      <Spinner className="size-7" />
    </div>
  );
}
