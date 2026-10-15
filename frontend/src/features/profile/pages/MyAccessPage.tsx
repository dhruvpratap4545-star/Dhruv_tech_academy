import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { ALL_NAV_ITEMS, isReachable } from "@/app/navigation";
import { accessKeys, fetchMyAccess } from "@/features/admin/api";
import type { EffectivePermission } from "@/features/auth/types";
import { useAuth } from "@/features/auth/useAuth";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";

/**
 * "What can I actually do here?" — answered from the server, for this person.
 *
 * This is the one screen that shows permissions you do **not** have. Everywhere else, a
 * thing you cannot use is simply absent; here the boundary is the subject. A
 * list of destinations is navigation and should contain only open doors; a list of
 * permissions is an explanation, and an explanation that omits the limits explains nothing.
 */
export function MyAccessPage() {
  const { user } = useAuth();
  const access = useQuery({
    queryKey: accessKeys.myAccess(),
    queryFn: ({ signal }) => fetchMyAccess(signal),
  });

  if (access.error) {
    return (
      <Alert tone="danger">
        <p>{access.error.message}</p>
      </Alert>
    );
  }

  if (!access.data) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  const data = access.data;
  const reachable = ALL_NAV_ITEMS.filter((item) => isReachable(user, item));
  const groups = [...new Set(data.permissions.map((p) => p.group))];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Overview"
        title="My access"
        description="Your roles, where each one applies, and exactly what they let you do."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Your role" value={data.roles[0]?.name ?? "No role yet"}>
          {data.roles[0] ? `Level ${data.roles[0].rank}` : "Ask an administrator"}
        </Tile>
        <Tile label="Where it applies" value={data.roles[0]?.scope_label ?? "—"}>
          {data.roles.length > 1 ? `and ${data.roles.length - 1} more` : "Your whole scope"}
        </Tile>
        <Tile label="You can add" value={String(data.can_grant_roles.length)}>
          {data.can_grant_roles.join(", ") || "Nobody"}
        </Tile>
        <Tile label="Permissions" value={`${data.granted_count} / ${data.total_count}`}>
          {data.total_count - data.granted_count} not available to you
        </Tile>
      </div>

      {data.roles.length > 1 && (
        <Card>
          <div className="border-b border-line p-4">
            <h2 className="font-display text-base font-bold text-fg">All your roles</h2>
          </div>
          <ul className="divide-y divide-line">
            {data.roles.map((role) => (
              <li key={`${role.key}-${role.institute_id}-${role.branch_id}`} className="p-4">
                <p className="font-semibold text-fg">{role.name}</p>
                <p className="text-sm text-fg-2">{role.scope_label}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <div className="border-b border-line p-4">
          <h2 className="font-display text-base font-bold text-fg">Pages you can open</h2>
          <p className="mt-0.5 text-sm text-fg-2">
            Everything in your navigation, and nothing else — there are no locked pages waiting for
            you elsewhere.
          </p>
        </div>
        <div className="grid gap-2 p-4 sm:grid-cols-2">
          {reachable.map((item) => (
            <Link
              key={item.id}
              to={item.to}
              className="flex items-start gap-3 rounded-md border border-line p-3 hover:border-accent hover:bg-surface-2"
            >
              <span className="mt-0.5 rounded-sm bg-accent-soft p-1.5 text-accent-ink">
                <Icon name={item.icon} className="size-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-fg">{item.label}</span>
                <span className="block text-xs text-fg-2">{item.blurb}</span>
              </span>
            </Link>
          ))}
        </div>
      </Card>

      {data.direct_grants.length > 0 && (
        <Card>
          <div className="border-b border-line p-4">
            <h2 className="font-display text-base font-bold text-fg">Exceptions for you</h2>
            <p className="mt-0.5 text-sm text-fg-2">
              Access given to you personally, on top of — or instead of — your role.
            </p>
          </div>
          <ul className="divide-y divide-line">
            {data.direct_grants.map((grant) => (
              <li key={grant.id} className="flex flex-wrap items-start gap-3 p-4">
                <Badge tone={grant.effect === "deny" ? "danger" : "success"}>
                  {grant.effect === "deny" ? "Blocked" : "Extra"}
                </Badge>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-fg">{grant.description}</p>
                  <p className="text-xs text-fg-3">
                    {grant.scope_label} · {grant.reason}
                  </p>
                </div>
                {grant.expires_at && (
                  <p className={cn("num text-xs", grant.expired ? "text-bad" : "text-fg-3")}>
                    {grant.expired ? "expired" : "until"} {formatDate(grant.expires_at)}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <div className="border-b border-line p-4">
          <h2 className="font-display text-base font-bold text-fg">Everything you may do</h2>
          <p className="mt-0.5 text-sm text-fg-2">
            The full list, including what you cannot do — so you know where the edge is.
          </p>
        </div>
        <div className="divide-y divide-line">
          {groups.map((group) => (
            <section key={group}>
              <p className="eyebrow bg-surface-2 px-4 py-1.5">{group}</p>
              <ul>
                {data.permissions
                  .filter((p) => p.group === group)
                  .map((permission) => (
                    <PermissionRow key={permission.key} permission={permission} />
                  ))}
              </ul>
            </section>
          ))}
        </div>
      </Card>
    </div>
  );
}

function PermissionRow({ permission }: { permission: EffectivePermission }) {
  return (
    <li className="flex items-center gap-3 px-4 py-2">
      <span
        className={cn(
          "shrink-0",
          permission.granted
            ? "text-ok"
            : permission.source === "blocked"
              ? "text-bad"
              : "text-fg-3",
        )}
      >
        {permission.granted ? (
          <Icon name="check" className="size-4" />
        ) : permission.source === "blocked" ? (
          <Icon name="ban" className="size-4" />
        ) : (
          <span className="block w-4 text-center">—</span>
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block text-sm", permission.granted ? "text-fg" : "text-fg-3")}>
          {permission.description}
        </span>
        <span className="mono block text-xs text-fg-3">{permission.key}</span>
      </span>
      <span className="shrink-0 text-right text-xs">
        {permission.granted ? (
          <>
            <span className="block text-fg-2">{permission.scope_label}</span>
            {permission.source === "direct" && (
              <span className="text-accent-ink">given to you personally</span>
            )}
          </>
        ) : permission.source === "blocked" ? (
          <span className="text-bad">blocked for you</span>
        ) : (
          <span className="text-fg-3">not in your role</span>
        )}
      </span>
    </li>
  );
}

function Tile({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-4">
      <p className="eyebrow">{label}</p>
      <p className="mt-1 truncate font-display text-base font-bold text-fg">{value}</p>
      <p className="mt-0.5 truncate text-xs text-fg-3">{children}</p>
    </Card>
  );
}
