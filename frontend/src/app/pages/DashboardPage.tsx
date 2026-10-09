import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "@/components/Badge";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/Spinner";
import { SigninChart } from "@/features/admin/components/SigninChart";
import { fetchOverview, overviewKey } from "@/features/auth/api";
import { useCurrentUser } from "@/features/auth/useAuth";
import { cn } from "@/lib/cn";
import type { Permission } from "@/lib/permissions";
import { can, ROLE_LABEL, roleScopeLabel, scopeLabel } from "@/lib/permissions";

type Shortcut = { to: string; title: string; description: string; permission?: Permission };

const SHORTCUTS: Shortcut[] = [
  {
    to: "/users",
    title: "Manage people",
    description: "Invite someone, change a role, suspend an account.",
    permission: "user:read",
  },
  {
    to: "/institutes",
    title: "Hierarchy",
    description: "Institutes and the branches inside them.",
    permission: "institute:read",
  },
  {
    to: "/audit",
    title: "Audit log",
    description: "Who changed what, and when.",
    permission: "audit:read",
  },
  { to: "/my-access", title: "My access", description: "What your roles let you do." },
];

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export function DashboardPage() {
  const user = useCurrentUser();
  const shortcuts = SHORTCUTS.filter((item) => !item.permission || can(user, item.permission));
  const canSeeStats = can(user, "user:read");
  // The chart reads the audit log, so it is only requested by someone who may read it.
  const canSeeAudit = can(user, "audit:read");

  // Only requested when the user may read people. Otherwise the endpoint would 403 and the
  // tiles would show an error to someone who simply has no business seeing them.
  const overview = useQuery({
    queryKey: overviewKey,
    queryFn: ({ signal }) => fetchOverview(signal),
    enabled: canSeeStats,
  });

  const firstName = user?.full_name.trim().split(/\s+/)[0] ?? "there";
  const primaryRole = user?.roles[0];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={user ? scopeLabel(user) : undefined}
        title={`${greeting()}, ${firstName}`}
        description={
          primaryRole
            ? `${ROLE_LABEL[primaryRole.role_key] ?? primaryRole.role_name} · ${roleScopeLabel(primaryRole)}`
            : "Your administrator has not given you a role yet."
        }
      />

      {canSeeStats && (
        // `stagger`: the four cards arrive left to right rather than all at once, which
        // reads as a row being laid down instead of a block appearing. 40ms apart, so the
        // last one is on screen 120ms after the first.
        <section aria-label="Summary" className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat
            label="People in scope"
            value={overview.data?.users_total}
            note={
              overview.data
                ? `${overview.data.users_active} active · ${overview.data.users_suspended} suspended`
                : undefined
            }
            loading={overview.isLoading}
          />
          <Stat
            label="Pending invitations"
            value={overview.data?.users_invited}
            note="Waiting for a password to be set"
            loading={overview.isLoading}
          />
          <Stat
            label="Institutes"
            value={overview.data?.institutes_total}
            note="Visible to you"
            loading={overview.isLoading}
          />
          <Stat
            label="Security events · 24h"
            value={overview.data?.security_events_24h}
            note="Failed sign-ins and locks"
            tone={overview.data && overview.data.security_events_24h > 0 ? "warn" : "normal"}
            loading={overview.isLoading}
          />
        </section>
      )}

      {canSeeAudit && <SigninChart />}

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Where to go" description="Everything your role can reach." />
          <CardBody className="grid gap-3 sm:grid-cols-2">
            {shortcuts.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "group rounded-md border border-line bg-surface p-3.5",
                  "transition-[border-color,box-shadow] duration-(--duration-base)",
                  "hover:border-accent hover:shadow-card",
                )}
              >
                <p className="font-semibold text-fg group-hover:text-accent-ink">{item.title}</p>
                <p className="mt-0.5 text-sm text-fg-2">{item.description}</p>
              </Link>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Your access" />
          <CardBody className="space-y-3">
            {user?.roles.length ? (
              <ul className="space-y-2">
                {user.roles.map((role) => (
                  <li
                    key={`${role.role_key}-${role.branch_id ?? role.institute_id ?? "platform"}`}
                    className="space-y-0.5"
                  >
                    <Badge tone="accent">{ROLE_LABEL[role.role_key] ?? role.role_name}</Badge>
                    <p className="text-xs text-fg-2">{roleScopeLabel(role)}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-fg-2">No roles yet.</p>
            )}
            <p className="text-sm text-fg-2">
              {user?.permissions.length ?? 0} permissions in total.
            </p>
            <Link
              to="/my-access"
              className="inline-flex h-8 items-center rounded-sm border border-line-strong px-3 text-xs font-semibold text-fg hover:bg-surface-2"
            >
              See my access
            </Link>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  note,
  loading,
  tone = "normal",
}: {
  label: string;
  value: number | undefined;
  note?: string;
  loading?: boolean;
  tone?: "normal" | "warn";
}) {
  return (
    <div className="rounded-md border border-line bg-surface p-4 shadow-card">
      <p className="eyebrow">{label}</p>
      {loading ? (
        <Skeleton className="mt-1.5 h-8 w-16" />
      ) : (
        <p
          className={cn(
            "num font-display text-3xl font-extrabold",
            tone === "warn" && value ? "text-warn" : "text-fg",
          )}
        >
          {value ?? "—"}
        </p>
      )}
      {note && <p className="mt-0.5 text-xs text-fg-2">{note}</p>}
    </div>
  );
}
