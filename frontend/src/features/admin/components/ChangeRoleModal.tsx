import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { SelectField } from "@/components/Field";
import { Modal } from "@/components/Modal";
import { assignRole, revokeRole, userKeys } from "@/features/admin/api";
import { fetchAssignableRoles } from "@/features/auth/api";
import type { RoleKey, UserSummary } from "@/features/auth/types";
import { ROLE_LABEL, ROLE_REQUIREMENTS, roleScopeLabel } from "@/lib/permissions";

/**
 * Give someone an additional role, or take one away (PRD §4.5, §3.1).
 *
 * The list of roles comes from the server, already filtered to what this caller may grant.
 * Scope is inherited from the role being replaced rather than asked for again: changing a
 * Faculty member to a Branch Admin keeps them in the same branch, which is what "change
 * role" means to the person doing it.
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

  const roles = useQuery({
    queryKey: ["assignable-roles"],
    queryFn: fetchAssignableRoles,
    enabled: open,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: userKeys.all });

  const give = useMutation({
    mutationFn: async () => {
      if (!user) return;
      // Inherit the scope of the role they already hold; a role must be granted somewhere.
      const existing = user.roles[0];
      const requirements = ROLE_REQUIREMENTS[roleKey as RoleKey];
      await assignRole(user.id, {
        role_key: roleKey as RoleKey,
        institute_id: requirements?.institute ? (existing?.institute_id ?? undefined) : undefined,
        branch_id: requirements?.branch ? (existing?.branch_id ?? undefined) : undefined,
      });
    },
    onSuccess: async () => {
      await refresh();
      setRoleKey("");
      onClose();
    },
  });

  const take = useMutation({
    mutationFn: (role: UserSummary["roles"][number]) =>
      revokeRole(user!.id, {
        role_key: role.role_key,
        institute_id: role.institute_id ?? undefined,
        branch_id: role.branch_id ?? undefined,
      }),
    onSuccess: refresh,
  });

  const error = give.error ?? take.error;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Change role"
      description={user ? `${user.full_name} · ${user.email}` : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button disabled={!roleKey} loading={give.isPending} onClick={() => give.mutate()}>
            Give role
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error && (
          <Alert tone="danger" title="Could not change the role">
            <p>{error.message}</p>
          </Alert>
        )}

        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-fg">Roles they hold now</h3>
          {user?.roles.length ? (
            <ul className="space-y-2">
              {user.roles.map((role) => (
                <li
                  key={`${role.role_key}-${role.branch_id ?? role.institute_id ?? "platform"}`}
                  className="flex items-center justify-between gap-3 rounded-sm border border-line px-3 py-2"
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
          ) : (
            <p className="text-sm text-fg-2">They hold no roles.</p>
          )}
        </section>

        <section className="space-y-2 border-t border-line pt-4">
          <SelectField
            label="Give another role"
            placeholder={roles.isLoading ? "Loading roles…" : "Choose a role"}
            hint="You can only give roles below your own level, inside your own scope."
            disabled={roles.isLoading}
            value={roleKey}
            onChange={(event) => setRoleKey(event.target.value)}
            options={(roles.data ?? []).map((role) => ({ value: role.key, label: role.name }))}
          />
          {roles.data?.length === 0 && <Badge tone="warning">You cannot give out any roles.</Badge>}
        </section>
      </div>
    </Modal>
  );
}
