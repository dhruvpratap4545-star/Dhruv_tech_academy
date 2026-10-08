import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { accessKeys, fetchPermissions, fetchRoles } from "@/features/admin/api";
import { RoleEditor } from "@/features/admin/components/RoleEditor";
import type { PermissionInfo, Role } from "@/features/auth/types";
import { useAuth, useCan } from "@/features/auth/useAuth";
import { cn } from "@/lib/cn";

/**
 * What every role allows, as a matrix — and the roles this institute has defined itself.
 *
 * The matrix is built from `GET /roles` and `GET /permissions`, not from a constant in
 * this file. That matters more than it looks: a hardcoded copy of the permission model is
 * a second source of truth that drifts the first time somebody changes the real one, and
 * the drift is invisible — the screen keeps rendering, just with the wrong answer.
 */
export function RolesPage() {
  const { user } = useAuth();
  const canManage = useCan("role:manage");
  const [editing, setEditing] = useState<Role | "new" | null>(null);

  const roles = useQuery({
    queryKey: accessKeys.roles(),
    queryFn: ({ signal }) => fetchRoles(signal),
  });
  const permissions = useQuery({
    queryKey: accessKeys.permissions(),
    queryFn: ({ signal }) => fetchPermissions(signal),
    staleTime: Infinity, // The catalogue is seed data; it changes on deploy, not at runtime.
  });

  if (roles.error || permissions.error) {
    return (
      <Alert tone="danger">
        <p>{(roles.error ?? permissions.error)?.message}</p>
      </Alert>
    );
  }

  if (!roles.data || !permissions.data) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  const active = roles.data.filter((role) => role.is_active);
  const builtIn = active.filter((role) => role.is_system);
  const custom = active.filter((role) => !role.is_system);
  const myRank = user?.roles.length ? Math.max(...user.roles.map((r) => r.rank)) : 0;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Administration"
        title="Roles & permissions"
        description="A role is a named bundle of permissions. Where it applies comes from the scope it was given at, not from the role itself."
        actions={
          canManage && (
            <Button onClick={() => setEditing("new")}>
              <Icon name="plus" className="size-4" />
              New role
            </Button>
          )
        }
      />

      <RoleSummary roles={builtIn} myRank={myRank} />

      <PermissionMatrix roles={active} permissions={permissions.data} myRank={myRank} />

      <CustomRoles
        roles={custom}
        canManage={canManage}
        onEdit={(role) => setEditing(role)}
        onCreate={() => setEditing("new")}
      />

      {editing && (
        <RoleEditor
          role={editing === "new" ? null : editing}
          permissions={permissions.data}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function RoleSummary({ roles, myRank }: { roles: Role[]; myRank: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {roles
        .filter((role) => role.rank >= 30)
        .slice(0, 4)
        .map((role) => (
          <Card
            key={role.id}
            className={cn("p-4", role.rank === myRank && "ring-1 ring-accent ring-inset")}
          >
            <p className="eyebrow">{SCOPE_WORD[role.scope_level]}</p>
            <p className="mt-1 font-display text-base font-bold text-fg">{role.name}</p>
            <p className="num mt-1 text-xs text-fg-3">
              {role.holder_count} {role.holder_count === 1 ? "person" : "people"} · level{" "}
              {role.rank}
            </p>
          </Card>
        ))}
    </div>
  );
}

const SCOPE_WORD: Record<string, string> = {
  platform: "Whole platform",
  institute: "One institute",
  branch: "One branch",
};

/**
 * The matrix. Rows are permissions grouped the way an administrator reviews them; columns
 * are roles.
 *
 * It scrolls sideways inside its own container rather than stacking: a matrix *is* its
 * two-dimensional comparison, and stacking it into per-role lists destroys the only thing
 * it is for. This is the documented exception to the stacking rule (ADR-015).
 */
function PermissionMatrix({
  roles,
  permissions,
  myRank,
}: {
  roles: Role[];
  permissions: PermissionInfo[];
  myRank: number;
}) {
  const groups = [...new Set(permissions.map((p) => p.group))];
  const held = new Map(roles.map((role) => [role.id, new Set(role.permissions)]));

  return (
    <Card>
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line p-4">
        <div>
          <h2 className="font-display text-base font-bold text-fg">What each role allows</h2>
          <p className="mt-0.5 text-sm text-fg-2">
            A tick means the role carries that permission. Whether it applies to one branch or every
            institute depends on where the role was given.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-fg-3">
          <span className="inline-flex items-center gap-1.5">
            <Icon name="check" className="size-3.5 text-ok" /> allowed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="text-fg-3">—</span> not allowed
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[40rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line">
              <th className="sticky left-0 z-10 bg-surface px-4 py-2.5 text-left font-semibold text-fg-2">
                Permission
              </th>
              {roles.map((role) => (
                <th
                  key={role.id}
                  className={cn(
                    "px-2 py-2.5 text-center text-xs font-semibold whitespace-nowrap",
                    role.rank === myRank ? "text-accent-ink" : "text-fg-2",
                  )}
                >
                  {role.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <Fragment key={group}>
                <tr className="bg-surface-2">
                  <td
                    colSpan={roles.length + 1}
                    className="px-4 py-1.5 text-xs font-bold tracking-wide text-fg-2 uppercase"
                  >
                    {group}
                  </td>
                </tr>
                {permissions
                  .filter((p) => p.group === group)
                  .map((permission) => (
                    <tr key={permission.key} className="border-b border-line/60">
                      <td className="sticky left-0 z-10 bg-surface px-4 py-2">
                        <span className="mono text-xs text-fg">{permission.key}</span>
                        <span className="block text-xs text-fg-3">{permission.description}</span>
                      </td>
                      {roles.map((role) => (
                        <td
                          key={role.id}
                          className={cn(
                            "px-2 py-2 text-center",
                            role.rank === myRank && "bg-accent-soft/50",
                          )}
                        >
                          {held.get(role.id)?.has(permission.key) ? (
                            <Icon
                              name="check"
                              className="mx-auto size-4 text-ok"
                              title={`${role.name} may ${permission.description.toLowerCase()}`}
                            />
                          ) : (
                            <span className="text-fg-3" aria-label="not allowed">
                              —
                            </span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function CustomRoles({
  roles,
  canManage,
  onEdit,
  onCreate,
}: {
  roles: Role[];
  canManage: boolean;
  onEdit: (role: Role) => void;
  onCreate: () => void;
}) {
  return (
    <Card>
      <div className="border-b border-line p-4">
        <h2 className="font-display text-base font-bold text-fg">Roles you have defined</h2>
        <p className="mt-0.5 text-sm text-fg-2">
          The six built-in roles cannot be changed — they are what those names mean across the whole
          platform. Roles you create here belong to your institute alone.
        </p>
      </div>

      {roles.length === 0 ? (
        <div className="px-4 py-10 text-center">
          <p className="text-sm font-medium text-fg">No roles of your own yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-fg-2">
            Create one when a job in your institute does not match a built-in role — a lab assistant
            who may see classes but change nothing, for instance.
          </p>
          {canManage && (
            <Button variant="secondary" className="mt-4" onClick={onCreate}>
              <Icon name="plus" className="size-4" />
              New role
            </Button>
          )}
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {roles.map((role) => (
            <li key={role.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-fg">
                  {role.name}
                  <Badge tone="neutral" className="ml-2">
                    level {role.rank}
                  </Badge>
                </p>
                <p className="mono text-xs text-fg-3">{role.key}</p>
                {role.description && <p className="mt-1 text-sm text-fg-2">{role.description}</p>}
                <p className="mt-1 text-xs text-fg-3">
                  {role.permissions.length} permissions · {role.holder_count}{" "}
                  {role.holder_count === 1 ? "holder" : "holders"} ·{" "}
                  {SCOPE_WORD[role.scope_level]?.toLowerCase()}
                </p>
              </div>
              {role.editable && (
                <Button size="sm" variant="secondary" onClick={() => onEdit(role)}>
                  Edit
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
