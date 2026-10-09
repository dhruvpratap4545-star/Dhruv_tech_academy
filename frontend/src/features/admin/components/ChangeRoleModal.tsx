import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { SelectField } from "@/components/Field";
import { Modal } from "@/components/Modal";
import {
  assignRole,
  fetchBranches,
  fetchInstitutes,
  fetchUser,
  instituteKeys,
  revokeRole,
  userKeys,
} from "@/features/admin/api";
import { fetchAssignableRoles } from "@/features/auth/api";
import type { AssignableRole, RoleAssignment, RoleKey, UserSummary } from "@/features/auth/types";
import { ROLE_LABEL, roleScopeLabel } from "@/lib/permissions";

/**
 * Add a role to somebody, or take one away (PRD §4.5, §3.1).
 *
 * Three things here were wrong before, and each of them is worth naming because the fix
 * is shaped by the mistake:
 *
 * **It was called "Change role" and it never changed anything.** Giving a Faculty member
 * Branch Admin left them holding both, which is correct — roles add up, and somebody can
 * genuinely teach in one branch while running another. But a dialog titled "Change role"
 * promises a swap, so the second role looked like a bug rather than the feature it is.
 * It is called "Manage roles" now, and it says out loud that permissions combine.
 *
 * **Removing a role did not remove it from this dialog.** The list of roles came from the
 * table row handed over when the dialog opened, and that copy never changed. Refetching
 * the whole table behind it made no difference to the stale object in front. The roles
 * shown now come from the server, by id, so they answer to the buttons beside them.
 *
 * **Scope was inherited silently, and then refused.** Whatever scope the person's *first*
 * role happened to have was reused for the new one. Give Faculty to somebody whose only
 * role is institute-wide and the server answers "Faculty must be given within a specific
 * branch" — correctly, because it must — while this dialog offered no way to name one.
 * The institute and branch are asked for, and only when the chosen role needs them.
 */
export function ChangeRoleModal({
  user,
  open,
  onClose,
}: {
  user: UserSummary | null;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [roleKey, setRoleKey] = useState("");
  const [instituteId, setInstituteId] = useState("");
  const [branchId, setBranchId] = useState("");

  // The live copy. `initialData` is the row that opened the dialog, so there is something
  // on screen from the first frame rather than a spinner over an empty list.
  const detail = useQuery({
    queryKey: userKeys.detail(user?.id ?? ""),
    queryFn: ({ signal }) => fetchUser(user!.id, signal),
    enabled: open && Boolean(user),
    initialData: user ?? undefined,
  });
  const held: RoleAssignment[] = detail.data?.roles ?? [];

  const roles = useQuery({
    queryKey: ["assignable-roles"],
    queryFn: () => fetchAssignableRoles(),
    enabled: open,
  });

  const chosen = roles.data?.find((role) => role.key === roleKey);
  const needsInstitute = chosen ? chosen.scope_level !== "platform" : false;
  const needsBranch = chosen?.scope_level === "branch";

  const institutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
    enabled: open && needsInstitute,
  });

  const branches = useQuery({
    queryKey: instituteKeys.branches(instituteId),
    queryFn: ({ signal }) => fetchBranches(instituteId, signal),
    enabled: open && needsBranch && Boolean(instituteId),
  });

  /**
   * Refresh the dialog and the table behind it.
   *
   * `await`, so the mutation stays pending until the new roles are on screen. Without it
   * the button stops spinning while the old list is still displayed, and the obvious
   * reading of that is "nothing happened".
   */
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: userKeys.all }),
      queryClient.invalidateQueries({ queryKey: ["me"] }),
    ]);
  };

  const reset = () => {
    setRoleKey("");
    setInstituteId("");
    setBranchId("");
  };

  const give = useMutation({
    mutationFn: async () => {
      if (!user || !chosen) return;
      await assignRole(user.id, {
        role_key: roleKey as RoleKey,
        institute_id: needsInstitute ? instituteId : undefined,
        branch_id: needsBranch ? branchId : undefined,
      });
    },
    onSuccess: async () => {
      await refresh();
      reset();
    },
  });

  const take = useMutation({
    mutationFn: (role: RoleAssignment) =>
      revokeRole(user!.id, {
        role_key: role.role_key,
        institute_id: role.institute_id ?? undefined,
        branch_id: role.branch_id ?? undefined,
      }),
    onSuccess: refresh,
  });

  const error = give.error ?? take.error;

  // Everything the chosen role needs has been named.
  const ready =
    Boolean(chosen) &&
    (!needsInstitute || Boolean(instituteId)) &&
    (!needsBranch || Boolean(branchId));

  const close = () => {
    reset();
    give.reset();
    take.reset();
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title="Manage roles"
      description={user ? `${user.full_name} · ${user.email}` : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Close
          </Button>
          <Button disabled={!ready} loading={give.isPending} onClick={() => give.mutate()}>
            Give this role
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error && (
          <Alert tone="danger" title="Could not change their roles">
            <p>{error.message}</p>
          </Alert>
        )}

        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-fg">Roles they hold now</h3>
          {held.length > 0 ? (
            <>
              <ul className="space-y-2">
                {held.map((role) => (
                  <li
                    key={`${role.role_key}-${role.branch_id ?? role.institute_id ?? "platform"}`}
                    className="press flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-fg">
                        {ROLE_LABEL[role.role_key] ?? role.role_name}
                      </p>
                      <p className="truncate text-xs text-fg-2">{roleScopeLabel(role)}</p>
                    </div>
                    <Button
                      size="sm"
                      variant="danger"
                      loading={take.isPending && take.variables === role}
                      onClick={() => take.mutate(role)}
                    >
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
              {held.length > 1 && (
                /* Said plainly, because two roles at once surprises people. It is not a
                   mistake and it is not a conflict: the permissions combine. */
                <p className="text-xs text-fg-2">
                  They hold {held.length} roles, so they can do everything any one of them allows.
                  The roles do not override each other.
                </p>
              )}
            </>
          ) : (
            <p className="text-sm text-fg-2">They hold no roles.</p>
          )}
        </section>

        <section className="space-y-3 border-t border-line pt-4">
          <SelectField
            label="Give another role"
            placeholder={roles.isLoading ? "Loading roles…" : "Choose a role"}
            hint="You can only give roles below your own level, inside your own scope."
            disabled={roles.isLoading}
            value={roleKey}
            onChange={(event) => {
              setRoleKey(event.target.value);
              // Pre-fill the scope from a role they already hold, where that role sits in
              // a place the new one could also sit. It is right far more often than it is
              // wrong, and it is a select, so being wrong costs one click.
              const suggestion = suggestScope(held, event.target.value, roles.data ?? []);
              setInstituteId(suggestion.instituteId);
              setBranchId(suggestion.branchId);
            }}
            options={(roles.data ?? []).map((role) => ({ value: role.key, label: role.name }))}
          />

          {roles.data?.length === 0 && <Badge tone="warning">You cannot give out any roles.</Badge>}

          {needsInstitute && (
            <SelectField
              label="Institute"
              placeholder={institutes.isLoading ? "Loading…" : "Choose an institute"}
              hint={`${chosen?.name} applies inside one institute, so it needs one named.`}
              disabled={institutes.isLoading}
              value={instituteId}
              onChange={(event) => {
                setInstituteId(event.target.value);
                setBranchId("");
              }}
              options={(institutes.data?.items ?? []).map((row) => ({
                value: row.id,
                label: row.name,
              }))}
            />
          )}

          {needsBranch && (
            <SelectField
              label="Branch"
              placeholder={
                !instituteId
                  ? "Choose an institute first"
                  : branches.isLoading
                    ? "Loading…"
                    : "Choose a branch"
              }
              hint={`${chosen?.name} is a branch role, so it has to be given within one branch.`}
              disabled={!instituteId || branches.isLoading}
              value={branchId}
              onChange={(event) => setBranchId(event.target.value)}
              options={(branches.data?.items ?? []).map((row) => ({
                value: row.id,
                label: row.name,
              }))}
            />
          )}

          {needsBranch && instituteId && branches.data?.items.length === 0 && (
            <Alert tone="warning" title="That institute has no branches yet">
              <p>
                A branch role has to be given inside a branch. Add a branch to this institute first,
                then come back.
              </p>
            </Alert>
          )}
        </section>
      </div>
    </Modal>
  );
}

/**
 * A sensible institute and branch for a role somebody is about to be given.
 *
 * The old code used `roles[0]` unconditionally, which is how a Faculty grant ended up with
 * no branch and was refused. This looks for a role they already hold that actually carries
 * what the new role needs — a branch, when the new role is a branch role — and falls back
 * to their institute, and then to nothing, in that order.
 */
function suggestScope(
  held: RoleAssignment[],
  roleKey: string,
  catalogue: AssignableRole[],
): { instituteId: string; branchId: string } {
  const level = catalogue.find((role) => role.key === roleKey)?.scope_level;
  if (!level || level === "platform") return { instituteId: "", branchId: "" };

  if (level === "branch") {
    const withBranch = held.find((role) => role.branch_id && role.institute_id);
    if (withBranch) {
      return { instituteId: withBranch.institute_id!, branchId: withBranch.branch_id! };
    }
  }

  const withInstitute = held.find((role) => role.institute_id);
  return { instituteId: withInstitute?.institute_id ?? "", branchId: "" };
}
