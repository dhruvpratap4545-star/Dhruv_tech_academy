import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { Icon } from "@/components/Icon";
import { Avatar, Wordmark } from "@/components/Logo";
import type { NavGroup } from "@/app/navigation";
import { visibleNavigation } from "@/app/navigation";
import { logout } from "@/features/auth/api";
import { useAuth } from "@/features/auth/useAuth";
import { GlobalSearch } from "@/features/search/GlobalSearch";
import { ThemeToggle } from "@/features/theme/ThemeToggle";
import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";
import { ROLE_LABEL, scopeLabel } from "@/lib/permissions";

/**
 * The console shell: sidebar, topbar, content.
 *
 * It renders navigation but does not define it — `app/navigation.ts` is the single
 * registry, so the sidebar and "My access" can never disagree about what exists.
 */
export function AppShell() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const signOut = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.clear();
      navigate("/login", { replace: true });
    },
  });

  // Close the drawer when the route changes. Adjusted during render rather than in an
  // effect: an effect would paint the new page with the drawer still over it for a frame.
  const [lastPath, setLastPath] = useState(location.pathname);
  if (location.pathname !== lastPath) {
    setLastPath(location.pathname);
    if (drawerOpen) setDrawerOpen(false);
  }

  // Escape closes it, which is what a drawer is expected to do and does not happen for free.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  const groups = visibleNavigation(user);
  const primaryRole = user?.roles.length
    ? [...user.roles].sort((a, b) => b.rank - a.rank)[0]
    : undefined;

  return (
    <div className="min-h-dvh bg-bg">
      <a
        href="#main"
        className="sr-only focus-not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-sm focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:text-accent-fg"
      >
        Skip to content
      </a>

      {/* The drawer's scrim. Only on small screens, where the sidebar overlays content. */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-overlay lg:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="lg:grid lg:grid-cols-[16rem_1fr]">
        <Sidebar
          groups={groups}
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          scope={user ? scopeLabel(user) : ""}
        />

        <div className="flex min-w-0 flex-col">
          <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
            <div className="flex h-14 items-center gap-2 px-4 sm:gap-3 sm:px-6">
              <button
                type="button"
                onClick={() => setDrawerOpen(true)}
                aria-expanded={drawerOpen}
                aria-controls="app-nav"
                className="-ml-2 rounded-sm p-2 text-fg-2 hover:bg-surface-2 hover:text-fg lg:hidden"
              >
                <Icon name="menu" className="size-5" title="Open navigation" />
              </button>

              <div className="lg:hidden">
                <Wordmark />
              </div>

              <GlobalSearch />

              <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
                {primaryRole && (
                  <span className="hidden items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent-ink md:inline-flex">
                    <Icon name="key" className="size-3.5" />
                    {ROLE_LABEL[primaryRole.role_key] ?? primaryRole.role_name}
                  </span>
                )}
                <ThemeToggle />
                <div className="hidden items-center gap-2 lg:flex">
                  <Avatar initials={initials(user?.full_name ?? "")} />
                  <span className="max-w-28 truncate text-xs font-semibold text-fg">
                    {user?.full_name}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => signOut.mutate()}
                  disabled={signOut.isPending}
                  className="rounded-sm p-2 text-fg-2 hover:bg-surface-2 hover:text-fg disabled:opacity-55 sm:px-2.5 sm:py-1.5"
                >
                  <Icon name="out" className="size-4 sm:hidden" title="Log out" />
                  <span className="hidden text-sm font-semibold sm:inline">Log out</span>
                </button>
              </div>
            </div>
          </header>

          <main id="main" className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
            <div className="mx-auto max-w-6xl">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

function Sidebar({
  groups,
  open,
  onClose,
  scope,
}: {
  groups: NavGroup[];
  open: boolean;
  onClose: () => void;
  scope: string;
}) {
  return (
    <nav
      id="app-nav"
      aria-label="Main"
      className={cn(
        "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-line bg-surface",
        "transition-transform duration-(--duration-base) ease-(--ease-out-soft)",
        "lg:sticky lg:top-0 lg:z-auto lg:h-dvh lg:translate-x-0 lg:transition-none",
        open ? "translate-x-0" : "-translate-x-full",
      )}
    >
      <div className="flex h-14 items-center justify-between gap-2 px-4">
        <Wordmark className="[&>span]:inline" />
        <button
          type="button"
          onClick={onClose}
          className="-mr-1 rounded-sm p-1.5 text-fg-2 hover:bg-surface-2 hover:text-fg lg:hidden"
        >
          <Icon name="close" className="size-5" title="Close navigation" />
        </button>
      </div>

      {/* Where the signed-in person actually sits in the hierarchy. Not a switcher:
          an account with roles in several institutes is rare, and a control that only
          ever has one option is clutter. */}
      {scope && (
        <div className="mx-3 mb-2 rounded-md bg-surface-2 px-3 py-2.5">
          <p className="eyebrow">Your scope</p>
          <p className="truncate text-sm font-semibold text-fg">{scope}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {groups.map((group) => (
          <div key={group.label} className="mb-4">
            <p className="eyebrow px-3 pb-1.5">{group.label}</p>
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.id}>
                  <NavLink
                    to={item.to}
                    end={item.to === "/"}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2.5 rounded-sm px-3 py-2 text-sm",
                        "transition-colors duration-(--duration-fast)",
                        isActive
                          ? "bg-accent-soft font-semibold text-accent-ink"
                          : "font-medium text-fg-2 hover:bg-surface-2 hover:text-fg",
                      )
                    }
                  >
                    <Icon name={item.icon} className="size-4" />
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}
