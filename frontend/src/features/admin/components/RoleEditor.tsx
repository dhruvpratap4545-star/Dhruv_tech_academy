import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Checkbox, SelectField, TextField } from "@/components/Field";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Modal } from "@/components/Modal";
import {
  removeRole,
  createRole,
  setInstituteRolePermissions,
  updateRole,
} from "@/features/admin/api";
import type { RoleRemoval } from "@/features/admin/api";
import type { PermissionInfo, Role } from "@/features/auth/types";
import { useAuth } from "@/features/auth/useAuth";
import { cn } from "@/lib/cn";

/**
 * Create or edit a role belonging to one institute (ADR-017).
 *
 * The permission list is deliberately *not* filtered to what the author may grant. The
 * server refuses anything beyond their own authority, and it says which key it refused —
 * which teaches far more than a silently shortened list, where the permission you were
 * looking for simply is not there and you cannot tell whether it exists at all.
 *
 * Rank and scope are fixed once the role exists. Changing either would rewrite what every
 * current holder may do, with no event that honestly describes the change.
 */
export function RoleEditor({
  role,
  permissions,
  viewingInstituteId,
  onClose,
  onRemoved,
}: {
  role: Role | null;
  permissions: PermissionInfo[];
  /** The institute whose view is on screen, when there is one. Distinct from the
   *  `instituteId` state below, which is the institute a *new* role is being created for. */
  viewingInstituteId?: string;
  onClose: () => void;
  /** Called with what the server actually did, so the page can report it after the dialog
   *  has closed. Deleting and retiring look identical from in here. */
  onRemoved?: (outcome: RoleRemoval) => void;
}) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const editing = role !== null;

  /**
   * Two different jobs share this dialog, and they must not be confused.
   *
   * *Adjusting* changes what a role allows inside one institute, and is offered for the
   * built-ins too. *Defining* changes the role itself, and only a custom role can be
   * defined. A built-in that is customisable but not editable lands in the first mode.
   */
  const adjusting = editing && !role.editable && role.customisable && Boolean(viewingInstituteId);

  const institutes = (user?.roles ?? []).filter((r) => r.institute_id);
  const myRank = user?.roles.length ? Math.max(...user.roles.map((r) => r.rank)) : 0;

  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [scopeLevel, setScopeLevel] = useState<"institute" | "branch">(
    (role?.scope_level as "institute" | "branch") ?? "branch",
  );
  const [rank, setRank] = useState(String(role?.rank ?? Math.max(1, Math.min(20, myRank - 1))));
  const [instituteId, setInstituteId] = useState(
    role?.institute_id ?? institutes[0]?.institute_id ?? "",
  );
  const [chosen, setChosen] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const [error, setError] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  const done = () => {
    void queryClient.invalidateQueries({ queryKey: ["access", "roles"] });
    onClose();
  };

  const save = useMutation({
    mutationFn: () =>
      adjusting
        ? setInstituteRolePermissions(role.id, viewingInstituteId!, [...chosen])
        : editing
          ? updateRole(role.id, {
              name,
              description: description || undefined,
              permissions: [...chosen],
            })
          : createRole({
              name,
              description: description || undefined,
              scope_level: scopeLevel,
              rank: Number(rank),
              institute_id: instituteId,
              permissions: [...chosen],
            }),
    onSuccess: done,
    onError: (err: Error) => setError(err.message),
  });

  // Delete or retire — the server picks, because only the server knows whether anybody has
  // ever held this role. The outcome is handed back to the page, which says which happened
  // instead of announcing the one that sounds tidier.
  const remove = useMutation({
    mutationFn: () => removeRole(role!.id),
    onSuccess: (outcome) => {
      onRemoved?.(outcome);
      done();
    },
    onError: (err: Error) => setError(err.message),
  });

  const groups = [...new Set(permissions.map((p) => p.group))];
  // Adjusting borrows the role's own name and institute, so neither is ours to validate.
  // A role with no permissions at all is legitimate here: it is how an institute says
  // "holders of this role may do nothing in our institute".
  const valid =
    adjusting || (name.trim().length >= 2 && chosen.size > 0 && (editing || instituteId));

  function toggle(key: string) {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={
        adjusting ? `${role.name} in your institute` : editing ? `Edit ${role.name}` : "New role"
      }
      description={
        adjusting
          ? "Changes what this role allows inside your institute only. Holders of the same role elsewhere are not affected, and the role's own definition does not change."
          : editing
            ? "Changes apply immediately to everyone holding this role."
            : "A role is a bundle of permissions. Where it applies is decided when you give it to someone."
      }
      footer={
        <div className="flex w-full flex-wrap items-center gap-2">
          {/* Retiring is about the role itself, so it has no place while adjusting one
              institute's view of a built-in. */}
          {editing && !adjusting && role.holder_count === 0 && (
            <Button variant="danger" size="sm" onClick={() => setConfirmRemove(true)}>
              Delete this role
            </Button>
          )}
          <div className="ml-auto flex gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={() => save.mutate()} disabled={!valid || save.isPending}>
              {save.isPending
                ? "Saving…"
                : adjusting
                  ? "Save for this institute"
                  : editing
                    ? "Save changes"
                    : "Create role"}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {error && (
          <Alert tone="danger">
            <p>{error}</p>
          </Alert>
        )}

        {/* Name, purpose, level and scope belong to the role itself. When this dialog is
            adjusting one institute's view of a built-in, none of them is ours to change —
            only which permissions apply here. */}
        {!adjusting && (
          <>
            <TextField
              label="Name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Lab Assistant"
              required
            />
            <TextField
              label="What is it for?"
              hint="One line, so the next administrator knows why it exists."
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Can see classes and students, but change nothing."
            />
          </>
        )}

        {!editing && (
          <div className="grid gap-4 sm:grid-cols-2">
            {institutes.length > 1 && (
              <SelectField
                label="Institute"
                value={instituteId}
                onChange={(event) => setInstituteId(event.target.value)}
                options={institutes.map((r) => ({
                  value: r.institute_id!,
                  label: r.institute_name ?? "Institute",
                }))}
              />
            )}
            <SelectField
              label="Applies to"
              hint="Fixed once the role exists."
              value={scopeLevel}
              onChange={(event) => setScopeLevel(event.target.value as "institute" | "branch")}
              options={[
                { value: "branch", label: "One branch at a time" },
                { value: "institute", label: "A whole institute" },
              ]}
            />
            <TextField
              label="Level"
              type="number"
              min={1}
              max={Math.max(1, myRank - 1)}
              hint={`Must be below your own level of ${myRank}. Higher means more authority.`}
              value={rank}
              onChange={(event) => setRank(event.target.value)}
            />
          </div>
        )}

        <fieldset className="rounded-md border border-line">
          <legend className="mx-3 px-1 text-sm font-semibold text-fg">
            Permissions
            <span className="ml-1.5 font-normal text-fg-3">({chosen.size} chosen)</span>
          </legend>
          <div className="max-h-72 space-y-3 overflow-y-auto p-3">
            {groups.map((group) => (
              <div key={group}>
                <p className="eyebrow pb-1">{group}</p>
                <div className="space-y-0.5">
                  {permissions
                    .filter((p) => p.group === group)
                    .map((permission) => (
                      <label
                        key={permission.key}
                        className={cn(
                          "flex cursor-pointer items-start gap-2.5 rounded-sm px-2 py-1.5",
                          chosen.has(permission.key) ? "bg-accent-soft" : "hover:bg-surface-2",
                        )}
                      >
                        <Checkbox
                          checked={chosen.has(permission.key)}
                          onChange={() => toggle(permission.key)}
                          label=""
                        />
                        <span className="min-w-0">
                          <span className="block text-sm text-fg">{permission.description}</span>
                          <span className="mono block text-xs text-fg-3">{permission.key}</span>
                        </span>
                      </label>
                    ))}
                </div>
              </div>
            ))}
          </div>
        </fieldset>

        {adjusting && (
          <Alert tone="info">
            <p>
              This changes <strong className="font-semibold">{role.name}</strong> for your institute
              only. The same role in other institutes keeps its own permissions, and the built-in
              definition is untouched.
            </p>
          </Alert>
        )}

        {editing && !adjusting && role.holder_count > 0 && (
          <Alert tone="info">
            <p>
              {role.holder_count} {role.holder_count === 1 ? "person holds" : "people hold"} this
              role. To retire it, move them to another role first.
            </p>
          </Alert>
        )}
      </div>

      <ConfirmDialog
        open={confirmRemove}
        onClose={() => setConfirmRemove(false)}
        onConfirm={() => remove.mutate()}
        title={`Delete ${role?.name ?? "this role"}?`}
        confirmLabel="Delete it"
        pending={remove.isPending}
        error={remove.error?.message ?? null}
      >
        <p>It stops being offered anywhere, immediately.</p>
        {/* Two outcomes, and which one applies is not ours to guess here — the count of
            people who have *ever* held the role is not on this object. So the dialog
            describes both, and the page reports afterwards which one happened. */}
        <p>
          If nobody has ever been given this role it is deleted outright, and the name{" "}
          <strong className="font-semibold text-fg">{role?.name}</strong> becomes free to use again.
        </p>
        <p>
          If somebody has held it, the definition is kept instead, so the activity log can still say
          what it allowed at the time. The name stays reserved in that case.
        </p>
      </ConfirmDialog>
    </Modal>
  );
}
