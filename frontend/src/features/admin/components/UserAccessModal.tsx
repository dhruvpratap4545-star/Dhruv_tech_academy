import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import {
  accessKeys,
  createGrant,
  fetchGrants,
  fetchPermissions,
  revokeGrant,
} from "@/features/admin/api";
import type { UserSummary } from "@/features/auth/types";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";

/**
 * One person's exceptions: extra permissions, or blocks (ADR-017).
 *
 * This is the detailed control. A role answers "what does this job allow?"; this answers
 * "what is different about this person?" — covering someone's leave for a fortnight, or
 * stopping one administrator reading student records while an incident is investigated.
 *
 * Two deliberate frictions, both carried over from the API rather than invented here:
 *
 * - **A reason is required.** An exception nobody can explain is an exception nobody dares
 *   remove, and those accumulate until the role model means nothing.
 * - **An expiry is offered first.** Temporary is almost always what is meant, and an
 *   exception with no end date is how a fortnight's cover becomes a permanent promotion
 *   that nobody ever decided to grant.
 */
export function UserAccessModal({
  user,
  open,
  onClose,
}: {
  user: UserSummary | null;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);

  const grants = useQuery({
    queryKey: accessKeys.grants(user?.id ?? ""),
    queryFn: ({ signal }) => fetchGrants(user!.id, signal),
    enabled: Boolean(user) && open,
  });

  const permissions = useQuery({
    queryKey: accessKeys.permissions(),
    queryFn: ({ signal }) => fetchPermissions(signal),
    enabled: open,
    staleTime: Infinity,
  });

  const remove = useMutation({
    mutationFn: (grantId: string) => revokeGrant(user!.id, grantId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accessKeys.grants(user!.id) }),
  });

  if (!user) return null;

  // The scope to attach a grant to: the person's own institute, since an exception is
  // meaningless outside the place their role already applies.
  const scope = user.roles[0];

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={`Access for ${user.full_name}`}
      description="Extra permissions and blocks that apply to this person alone, on top of their role."
      footer={
        <div className="ml-auto">
          <Button variant="secondary" onClick={onClose}>
            Done
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="rounded-md bg-surface-2 p-3">
          <p className="eyebrow">Their role</p>
          <p className="text-sm font-semibold text-fg">
            {user.roles.map((role) => role.role_name).join(", ") || "No role yet"}
          </p>
          <p className="text-xs text-fg-3">
            Everything below is in addition to — or instead of — what that role allows.
          </p>
        </div>

        {grants.isLoading && (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        )}

        {grants.data && grants.data.length === 0 && !adding && (
          <div className="rounded-md border border-dashed border-line px-4 py-8 text-center">
            <p className="text-sm font-medium text-fg">No exceptions</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-fg-2">
              This person has exactly what their role gives them — which is usually how it should
              stay.
            </p>
          </div>
        )}

        {grants.data && grants.data.length > 0 && (
          <ul className="divide-y divide-line rounded-md border border-line">
            {grants.data.map((grant) => (
              <li key={grant.id} className="flex flex-wrap items-start gap-3 p-3">
                <Badge tone={grant.effect === "deny" ? "danger" : "success"}>
                  {grant.effect === "deny" ? "Blocked" : "Extra"}
                </Badge>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-fg">{grant.description}</p>
                  <p className="mono text-xs text-fg-3">{grant.permission}</p>
                  <p className="mt-1 text-xs text-fg-2">
                    {grant.scope_label} · {grant.reason}
                    {grant.granted_by_name && ` · by ${grant.granted_by_name}`}
                  </p>
                  {grant.expires_at && (
                    <p className={cn("num text-xs", grant.expired ? "text-bad" : "text-fg-3")}>
                      {grant.expired ? "Expired " : "Until "}
                      {formatDate(grant.expires_at)}
                    </p>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => remove.mutate(grant.id)}
                  disabled={remove.isPending}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}

        {remove.error && (
          <Alert tone="danger">
            <p>{remove.error.message}</p>
          </Alert>
        )}

        {adding ? (
          <GrantForm
            userId={user.id}
            instituteId={scope?.institute_id ?? null}
            branchId={scope?.branch_id ?? null}
            permissions={permissions.data ?? []}
            onDone={() => {
              setAdding(false);
              void queryClient.invalidateQueries({ queryKey: accessKeys.grants(user.id) });
            }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            <Icon name="plus" className="size-4" />
            Add an exception
          </Button>
        )}
      </div>
    </Modal>
  );
}

function GrantForm({
  userId,
  instituteId,
  branchId,
  permissions,
  onDone,
  onCancel,
}: {
  userId: string;
  instituteId: string | null;
  branchId: string | null;
  permissions: { key: string; description: string; group: string }[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [permission, setPermission] = useState("");
  const [effect, setEffect] = useState<"allow" | "deny">("allow");
  const [reason, setReason] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [applyToBranch, setApplyToBranch] = useState(Boolean(branchId));

  const save = useMutation({
    mutationFn: () =>
      createGrant(userId, {
        permission,
        effect,
        institute_id: instituteId ?? undefined,
        branch_id: applyToBranch && branchId ? branchId : undefined,
        reason,
        // A date input gives a local date; the end of that day is what "until the 20th"
        // means to a person, so the grant lasts through it rather than expiring at 00:00.
        expires_at: expiresAt ? new Date(`${expiresAt}T23:59:59`).toISOString() : undefined,
      }),
    onSuccess: onDone,
  });

  const valid = permission && reason.trim().length >= 4;

  return (
    <div className="space-y-3 rounded-md border border-accent/40 bg-accent-soft/30 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField
          label="Permission"
          value={permission}
          onChange={(event) => setPermission(event.target.value)}
          placeholder="Choose one"
          options={permissions.map((p) => ({
            value: p.key,
            label: `${p.group} — ${p.description}`,
          }))}
        />
        <SelectField
          label="Effect"
          hint="A block beats every role, including a Super Admin's."
          value={effect}
          onChange={(event) => setEffect(event.target.value as "allow" | "deny")}
          options={[
            { value: "allow", label: "Allow — give them this as well" },
            { value: "deny", label: "Block — stop them doing this" },
          ]}
        />
      </div>

      <TextField
        label="Why?"
        hint="Required. The next administrator needs to know whether this can be removed."
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Covering for the branch head until 20-10-2026"
        required
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          label="Until (optional)"
          type="date"
          hint="Leave empty only if this is meant to be permanent."
          value={expiresAt}
          onChange={(event) => setExpiresAt(event.target.value)}
        />
        {branchId && (
          <SelectField
            label="Applies to"
            value={applyToBranch ? "branch" : "institute"}
            onChange={(event) => setApplyToBranch(event.target.value === "branch")}
            options={[
              { value: "branch", label: "Their branch only" },
              { value: "institute", label: "The whole institute" },
            ]}
          />
        )}
      </div>

      {save.error && (
        <Alert tone="danger">
          <p>{save.error.message}</p>
        </Alert>
      )}

      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={() => save.mutate()} disabled={!valid || save.isPending}>
          {save.isPending ? "Saving…" : "Add exception"}
        </Button>
      </div>
    </div>
  );
}
