import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
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
  fetchInstitutes,
  fetchPermissions,
  instituteKeys,
  revokeGrant,
} from "@/features/admin/api";
import type { Institute, UserSummary } from "@/features/auth/types";
import { useCurrentUser } from "@/features/auth/useAuth";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { isPlatformStaff } from "@/lib/permissions";

/** Where an exception applies. A personal grant names an institute, a branch, or neither. */
type GrantScope = {
  value: string;
  label: string;
  instituteId: string | null;
  branchId: string | null;
};

/**
 * The places an exception for this person can sit: each institute and branch their roles
 * cover. A grant cannot name an organisation, so an organisation-wide role offers each of
 * that organisation's institutes instead. "Platform-wide" is for platform staff only —
 * anybody else sending no scope would be refused.
 */
function grantScopes(
  user: UserSummary,
  orgInstitutes: Map<string, Institute[]>,
  platformAdmin: boolean,
): GrantScope[] {
  const scopes = new Map<string, GrantScope>();
  const addInstitute = (id: string, name: string | null) =>
    scopes.set(id, {
      value: id,
      label: `${name ?? "Institute"} (whole institute)`,
      instituteId: id,
      branchId: null,
    });

  for (const role of user.roles) {
    if (role.institute_id && role.branch_id) {
      scopes.set(`${role.institute_id}:${role.branch_id}`, {
        value: `${role.institute_id}:${role.branch_id}`,
        label: `${role.institute_name ?? "Institute"} · ${role.branch_name ?? "Branch"} (branch only)`,
        instituteId: role.institute_id,
        branchId: role.branch_id,
      });
    }
    if (role.institute_id) addInstitute(role.institute_id, role.institute_name);
    else if (role.organisation_id) {
      for (const row of orgInstitutes.get(role.organisation_id) ?? []) {
        addInstitute(row.id, row.name);
      }
    }
  }
  if (platformAdmin) {
    scopes.set("platform", {
      value: "platform",
      label: "Platform-wide",
      instituteId: null,
      branchId: null,
    });
  }
  return [...scopes.values()];
}

/**
 * One person's exceptions: extra permissions, or blocks.
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
  const me = useCurrentUser();
  const [adding, setAdding] = useState(false);

  // An organisation-wide role names no institute, and a grant must name one: fetch the
  // institutes of each organisation they hold a role across, so those can be offered.
  const orgIds = [
    ...new Set(
      (user?.roles ?? [])
        .filter((role) => !role.institute_id && role.organisation_id)
        .map((role) => role.organisation_id!),
    ),
  ];
  const orgInstituteQueries = useQueries({
    queries: orgIds.map((orgId) => ({
      queryKey: instituteKeys.list(orgId),
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchInstitutes(signal, orgId),
      enabled: open,
    })),
  });
  const orgInstitutes = new Map(
    orgIds.map((orgId, index) => [orgId, orgInstituteQueries[index]?.data?.items ?? []]),
  );

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

  // The scopes a grant can attach to: the places their roles already apply, since an
  // exception is meaningless outside them. The first is the default.
  const scopes = grantScopes(user, orgInstitutes, isPlatformStaff(me));

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
            scopes={scopes}
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
  scopes,
  permissions,
  onDone,
  onCancel,
}: {
  userId: string;
  scopes: GrantScope[];
  permissions: { key: string; description: string; group: string }[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [permission, setPermission] = useState("");
  const [effect, setEffect] = useState<"allow" | "deny">("allow");
  const [reason, setReason] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [scopeValue, setScopeValue] = useState("");
  // Default to the first, which may only arrive once an organisation's institutes load.
  const scope = scopes.find((row) => row.value === scopeValue) ?? scopes[0];

  const save = useMutation({
    mutationFn: () =>
      createGrant(userId, {
        permission,
        effect,
        institute_id: scope?.instituteId ?? undefined,
        branch_id: scope?.branchId ?? undefined,
        reason,
        // A date input gives a local date; the end of that day is what "until the 20th"
        // means to a person, so the grant lasts through it rather than expiring at 00:00.
        expires_at: expiresAt ? new Date(`${expiresAt}T23:59:59`).toISOString() : undefined,
      }),
    onSuccess: onDone,
  });

  const valid = permission && reason.trim().length >= 4 && Boolean(scope);

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
        {scopes.length > 1 && (
          <SelectField
            label="Applies to"
            value={scope?.value ?? ""}
            onChange={(event) => setScopeValue(event.target.value)}
            options={scopes.map((row) => ({ value: row.value, label: row.label }))}
          />
        )}
      </div>

      {scopes.length === 0 && (
        <Alert tone="warning">
          <p>
            This person holds no role in an institute or branch, so there is nowhere for an
            exception to apply. Give them a role first.
          </p>
        </Alert>
      )}

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
