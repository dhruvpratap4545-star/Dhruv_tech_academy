import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import {
  accessKeys,
  fetchInstitutes,
  fetchPermissions,
  fetchRoles,
  instituteKeys,
  removeRole,
  setInstituteRolePermissions,
  updateRole,
} from "@/features/admin/api";
import type { RoleRemoval } from "@/features/admin/api";
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
  const [toggleError, setToggleError] = useState<string | null>(null);
  const [removalNote, setRemovalNote] = useState<RoleRemoval | null>(null);

  // Which institute's view this is, and it is the most important control on the page.
  //
  // Every role, built-in ones included, can be adjusted for one institute at a time: what
  // Faculty allows at ABC College is ABC's business and changes nothing about Faculty
  // anywhere else. The one thing nobody may edit is a built-in role's *platform-wide*
  // definition, because that is what the word "Faculty" means everywhere, and a product
  // where it varies per customer cannot be supported.
  //
  // That made the previous version of this page useless to exactly the people who needed
  // it most. The institute list came from the caller's own role assignments, and platform
  // staff hold none — so a Super Admin saw no selector at all, landed on the read-only
  // platform view, and found every cell locked with nothing to explain why or what to do.
  // Platform staff now get the full list of institutes to choose from.
  const myInstitutes = (user?.roles ?? [])
    .filter((role) => role.institute_id)
    .map((role) => ({ id: role.institute_id!, name: role.institute_name ?? "Institute" }));

  const isPlatformStaff = myInstitutes.length === 0;
  const allInstitutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
    enabled: isPlatformStaff,
  });

  const choices = isPlatformStaff
    ? (allInstitutes.data?.items ?? []).map((row) => ({ id: row.id, name: row.name }))
    : dedupe(myInstitutes);

  // Platform staff start on the platform-wide definitions, because that is the view that
  // belongs to them. Everyone else starts on their own institute, which is the only view
  // that answers the question they came here with.
  const [instituteId, setInstituteId] = useState<string>("");
  const effectiveId = instituteId || (isPlatformStaff ? "" : (choices[0]?.id ?? ""));
  const viewing = effectiveId || undefined;

  const queryClient = useQueryClient();

  /**
   * Toggling one cell sends the role's whole permission set, not a delta.
   *
   * The endpoint takes a set, and sending one is what makes the write idempotent: a
   * double-click, or two administrators on the same row, converge on the same answer
   * instead of adding and removing the same permission twice. On success the roles query
   * is invalidated, so the table shows the server's answer rather than an optimistic guess
   * that might have been refused.
   */
  const toggle = useMutation({
    mutationFn: ({ role, permission, next }: { role: Role; permission: string; next: boolean }) => {
      const permissions = next
        ? [...role.permissions, permission]
        : role.permissions.filter((p) => p !== permission);

      // Which endpoint depends on what the displayed set actually *is*.
      //
      // With an institute in view, `role.permissions` is that institute's effective set —
      // the definition plus its additions, minus its removals. Posting that to
      // `updateRole` would bake the overrides into the role's own definition and leave the
      // override rows behind, so a permission sitting in a `deny` would appear to toggle
      // on and then vanish on the next refetch, with no error. `setInstituteRolePermissions`
      // takes the effective set and works out the difference, which is what we mean.
      return viewing
        ? setInstituteRolePermissions(role.id, viewing, permissions)
        : updateRole(role.id, { permissions });
    },
    // `await`, so the mutation stays pending until the refetch lands. Without it
    // `isPending` drops while the table still holds the pre-change permissions, and a
    // second click in that window sends a set computed from stale data — silently
    // reverting the first change.
    onSuccess: async () => {
      setToggleError(null);
      await queryClient.invalidateQueries({ queryKey: ["access", "roles"] });
    },
    onError: (error: Error) => setToggleError(error.message),
  });

  const roles = useQuery({
    queryKey: accessKeys.roles(viewing),
    queryFn: ({ signal }) => fetchRoles(viewing, signal),
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

      {(choices.length > 1 || isPlatformStaff) && (
        <Card className="animate-fade flex flex-wrap items-center gap-3 p-4">
          <span className="text-sm font-medium text-fg">Showing permissions for</span>
          <select
            value={effectiveId}
            onChange={(event) => setInstituteId(event.target.value)}
            aria-label="Institute whose permissions are shown"
            className="h-9 rounded-lg border border-line bg-surface px-2.5 text-sm text-fg"
          >
            {/* Platform staff only. An institute administrator has no business reading the
                platform-wide definitions, and offering the option would hand them a view
                where everything is locked for reasons that are not theirs. */}
            {isPlatformStaff && <option value="">Platform-wide definitions</option>}
            {choices.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
          <p className="text-xs text-fg-2">
            {viewing
              ? "Every role can be adjusted here. Changes apply to this institute only."
              : "Read-only. Pick an institute to change what a role allows there."}
          </p>
        </Card>
      )}

      {removalNote && (
        <Alert
          tone={removalNote.deleted ? "success" : "info"}
          title={removalNote.deleted ? "Role deleted" : "Role retired"}
          onDismiss={() => setRemovalNote(null)}
        >
          <p>{removalNote.message}</p>
        </Alert>
      )}

      {toggleError && (
        <Alert tone="danger" title="That change was not applied">
          <p>{toggleError}</p>
        </Alert>
      )}

      <RoleSummary roles={builtIn} myRank={myRank} />

      <PermissionMatrix
        roles={active}
        permissions={permissions.data}
        myRank={myRank}
        instituteId={viewing}
        onCustomise={setEditing}
        onToggle={(role, permission, next) => toggle.mutate({ role, permission, next })}
        saving={toggle.isPending}
      />

      <CustomRoles
        roles={custom}
        canManage={canManage}
        onEdit={(role) => setEditing(role)}
        onCreate={() => setEditing("new")}
        onRemoved={setRemovalNote}
      />

      {editing && (
        <RoleEditor
          role={editing === "new" ? null : editing}
          permissions={permissions.data}
          viewingInstituteId={viewing}
          onClose={() => setEditing(null)}
          onRemoved={setRemovalNote}
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
  instituteId,
  onCustomise,
  onToggle,
  saving,
}: {
  roles: Role[];
  permissions: PermissionInfo[];
  myRank: number;
  instituteId?: string;
  onCustomise: (role: Role) => void;
  onToggle: (role: Role, permission: string, next: boolean) => void;
  saving: boolean;
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
                  <span className="block">{role.name}</span>
                  {role.customised_here && (
                    <span className="mt-0.5 block text-[0.6rem] font-medium text-accent-ink">
                      adjusted here
                    </span>
                  )}
                  {instituteId && role.customisable && (
                    <button
                      type="button"
                      onClick={() => onCustomise(role)}
                      className="mt-1 block w-full text-[0.65rem] font-medium text-accent hover:underline"
                    >
                      Change
                    </button>
                  )}
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
                      {roles.map((role) => {
                        const allowed = held.get(role.id)?.has(permission.key) ?? false;
                        // With an institute in view a cell follows `customisable`,
                        // which includes built-ins: adjusting Faculty for ABC changes
                        // nothing about Faculty anywhere else. Without one it follows
                        // `editable`, which is custom roles only — a built-in's own
                        // definition is read-only to everyone, Super Admin included.
                        const canToggle =
                          (instituteId ? role.customisable : role.editable) && !saving;

                        return (
                          <td
                            key={role.id}
                            className={cn(
                              "px-2 py-2 text-center",
                              role.rank === myRank && "bg-accent-soft/50",
                            )}
                          >
                            {canToggle ? (
                              <button
                                type="button"
                                role="switch"
                                aria-checked={allowed}
                                aria-label={`${role.name}: ${permission.description}`}
                                onClick={() => onToggle(role, permission.key, !allowed)}
                                className={cn(
                                  "mx-auto flex size-6 items-center justify-center rounded-sm",
                                  "hover:ring-2 hover:ring-accent focus-visible:ring-2",
                                  "focus-visible:ring-accent focus-visible:outline-none",
                                  allowed ? "text-ok" : "text-fg-3 hover:text-fg-2",
                                )}
                              >
                                {allowed ? <Icon name="check" className="size-4" /> : "—"}
                              </button>
                            ) : allowed ? (
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
                        );
                      })}
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
  onRemoved,
}: {
  roles: Role[];
  canManage: boolean;
  onEdit: (role: Role) => void;
  onCreate: () => void;
  onRemoved: (outcome: RoleRemoval) => void;
}) {
  const queryClient = useQueryClient();
  const [removing, setRemoving] = useState<Role | null>(null);

  // Deleting from here as well as from inside the editor. Somebody who wants a role gone
  // looks at the list of roles, not inside the dialog for changing one.
  const remove = useMutation({
    mutationFn: (role: Role) => removeRole(role.id),
    onSuccess: async (outcome) => {
      await queryClient.invalidateQueries({ queryKey: ["access", "roles"] });
      setRemoving(null);
      onRemoved(outcome);
    },
  });

  return (
    <Card>
      <div className="border-b border-line p-4">
        <h2 className="font-display text-base font-bold text-fg">Roles you have defined</h2>
        <p className="mt-0.5 text-sm text-fg-2">
          Roles you create here belong to your institute alone. The six built-in roles keep their
          platform-wide meaning, but what each one allows can still be adjusted for your institute
          in the table above.
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
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="press"
                    onClick={() => onEdit(role)}
                  >
                    Edit
                  </Button>
                  {/* Only while nobody holds it. Removing a role out from under forty
                      people is a different and much larger decision, and the server
                      refuses it anyway — offering the button would just produce an error
                      message where a disabled control would have explained itself. */}
                  {role.holder_count === 0 && (
                    <Button
                      size="sm"
                      variant="danger"
                      className="press"
                      onClick={() => setRemoving(role)}
                    >
                      Delete
                    </Button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        onConfirm={() => removing && remove.mutate(removing)}
        title={`Delete ${removing?.name ?? "this role"}?`}
        confirmLabel="Delete it"
        pending={remove.isPending}
        error={remove.error?.message ?? null}
      >
        <p>It stops being offered anywhere, immediately.</p>
        <p>
          If nobody has ever been given this role it is deleted outright, and the name{" "}
          <strong className="font-semibold text-fg">{removing?.name}</strong> becomes free to use
          again. If somebody has held it, the definition is kept instead so the activity log can
          still say what it allowed.
        </p>
      </ConfirmDialog>
    </Card>
  );
}

/** One entry per institute. Somebody holding two roles at the same college appears twice. */
function dedupe(rows: { id: string; name: string }[]) {
  return [...new Map(rows.map((row) => [row.id, row])).values()];
}
