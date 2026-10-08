import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/app/layouts/AppShell";
import { DashboardPage } from "@/app/pages/DashboardPage";
import { NotFoundPage } from "@/app/pages/NotFoundPage";
import { AuditPage } from "@/features/admin/pages/AuditPage";
import { CreateInstitutePage } from "@/features/admin/pages/CreateInstitutePage";
import { InstitutesPage } from "@/features/admin/pages/InstitutesPage";
import { RolesPage } from "@/features/admin/pages/RolesPage";
import { UsersPage } from "@/features/admin/pages/UsersPage";
import { ForgotPasswordPage } from "@/features/auth/pages/ForgotPasswordPage";
import { LoginPage } from "@/features/auth/pages/LoginPage";
import { RegisterPage } from "@/features/auth/pages/RegisterPage";
import { SetupPasswordPage } from "@/features/auth/pages/SetupPasswordPage";
import { RedirectIfSignedIn, RequireAuth, RequirePermission } from "@/features/auth/guards";
import { MyAccessPage } from "@/features/profile/pages/MyAccessPage";
import { SettingsPage } from "@/features/profile/pages/SettingsPage";

/**
 * Route table.
 *
 * Guards here are navigation convenience only: they stop someone landing on a page that
 * would just show errors. Every endpoint behind them re-checks the permission against the
 * target's scope, which is the authorization that actually counts (PRD §5.2).
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <RedirectIfSignedIn>
            <LoginPage />
          </RedirectIfSignedIn>
        }
      />
      <Route
        path="/register"
        element={
          <RedirectIfSignedIn>
            <RegisterPage />
          </RedirectIfSignedIn>
        }
      />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/set-password" element={<SetupPasswordPage />} />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route
          path="/users"
          element={
            <RequirePermission permission="user:read">
              <UsersPage />
            </RequirePermission>
          }
        />
        <Route
          path="/institutes"
          element={
            <RequirePermission permission="institute:read">
              <InstitutesPage />
            </RequirePermission>
          }
        />
        <Route
          path="/institutes/new"
          element={
            <RequirePermission permission="institute:create">
              <CreateInstitutePage />
            </RequirePermission>
          }
        />
        <Route
          path="/roles"
          element={
            <RequirePermission permission="role:read">
              <RolesPage />
            </RequirePermission>
          }
        />
        <Route
          path="/audit"
          element={
            <RequirePermission permission="audit:read">
              <AuditPage />
            </RequirePermission>
          }
        />
        <Route path="/my-access" element={<MyAccessPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        {/* The old paths still resolve, so a bookmark or an emailed link keeps working. */}
        {/* Search results link to /hierarchy; it is the same screen under a clearer name. */}
        <Route path="/hierarchy" element={<Navigate to="/institutes" replace />} />
        <Route path="/profile" element={<Navigate to="/settings" replace />} />
        <Route path="/profile/password" element={<Navigate to="/settings" replace />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
