import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Badge, StatusBadge } from "@/components/Badge";
import { Avatar } from "@/components/Logo";
import { Button } from "@/components/Button";
import { Pagination } from "@/components/Pagination";
import { Checkbox } from "@/components/Field";
import { Card } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import type { Column } from "@/components/Table";
import { EmptyState, Table } from "@/components/Table";
import type { UserFilters } from "@/features/admin/api";
import type { BulkStatusResponse } from "@/features/admin/api";
import {
  bulkUpdateStatus,
  fetchUsers,
  resendInvite,
  updateUserStatus,
  userKeys,
} from "@/features/admin/api";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ChangeRoleModal } from "@/features/admin/components/ChangeRoleModal";
import { InviteUserModal } from "@/features/admin/components/InviteUserModal";
import { UserAccessModal } from "@/features/admin/components/UserAccessModal";
import type { UserSummary } from "@/features/auth/types";
import { useCan, useCurrentUser } from "@/features/auth/useAuth";
import { formatRelative, initials } from "@/lib/format";
import { ROLE_LABEL, roleScopeLabel } from "@/lib/permissions";

/** Debounce so typing a name does not fire a request per keystroke. */
function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** One page of users. The query and the "page X of Y" arithmetic must agree. */
const PAGE_SIZE = 20;

export function UsersPage() {
  const queryClient = useQueryClient();
  const me = useCurrentUser();
  const canInvite = useCan("user:invite");
  const canChangeStatus = useCan("user:update_status");
  const canAssignRole = useCan("role:assign");
  const canGrant = useCan("permission:grant");

  // Seeded from the URL, so arriving from the global search lands on the person you
  // picked. The header search links here as `/users?q=<email>`; without reading it the
  // list opened unfiltered on page one, with the chosen person usually not on screen and
  // the filter box empty — which looks like the search simply failed.
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");

  // The link may be followed again with a different address while this page is already
  // mounted, which does not remount it.
  const fromUrl = params.get("q") ?? "";
  const [lastFromUrl, setLastFromUrl] = useState(fromUrl);
  if (fromUrl !== lastFromUrl) {
    setLastFromUrl(fromUrl);
    setSearch(fromUrl);
  }
  const [status, setStatus] = useState("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [roleTarget, setRoleTarget] = useState<UserSummary | null>(null);
  const [accessTarget, setAccessTarget] = useState<UserSummary | null>(null);
  // Suspension signs the person out immediately and refuses their next sign-in, so it
  // asks first. Re-activation restores access and needs no ceremony.
  const [suspendTarget, setSuspendTarget] = useState<UserSummary | null>(null);
  const [invited, setInvited] = useState<string | null>(null);

  // Selected ids, for the bulk actions. Held as ids rather than rows so a refetch that
  // returns new objects does not silently empty the selection.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkIntent, setBulkIntent] = useState<"active" | "suspended" | null>(null);
  const [bulkSummary, setBulkSummary] = useState<BulkStatusResponse | null>(null);
  const [role, setRole] = useState("");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);

  const debouncedSearch = useDebounced(search);

  // Changing a filter invalidates the cursor trail: page 3 of the old result set is
  // meaningless against the new one. Adjusted during render rather than in an effect —
  // React re-renders immediately without committing the stale page, so there is no flash
  // of the wrong results and no cascading effect.
  const filterKey = `${debouncedSearch}|${status}|${role}`;

  // Changing filters *or page* changes who is on screen. Keeping a selection across that
  // would mean acting on people the administrator can no longer see, which is exactly the
  // mistake a confirmation dialog cannot catch — and "Select everyone on this page" would
  // report itself unchecked while a hidden selection was still live.
  //
  // One block, not two. Two blocks keyed on overlapping values ran in an order that was
  // only correct by accident: the filter reset sets `pageIndex` to 0, which changes the
  // view key the block above had just recorded, so clearing the selection depended on
  // which one happened to be written first.
  const viewKey = `${filterKey}|${pageIndex}`;
  const [lastView, setLastView] = useState(viewKey);
  if (viewKey !== lastView) {
    const filtersChanged = lastView.slice(0, lastView.lastIndexOf("|")) !== filterKey;
    if (filtersChanged) {
      // Page 3 of the old result set is meaningless against the new one.
      setCursors([null]);
      setPageIndex(0);
      setLastView(`${filterKey}|0`);
    } else {
      setLastView(viewKey);
    }
    if (selected.size > 0) setSelected(new Set());
  }

  const filters: UserFilters = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      status: status || undefined,
      role_key: role || undefined,
      cursor: cursors[pageIndex] ?? undefined,
      limit: PAGE_SIZE,
    }),
    [debouncedSearch, status, role, cursors, pageIndex],
  );

  const users = useQuery({
    queryKey: userKeys.list(filters),
    queryFn: ({ signal }) => fetchUsers(filters, signal),
    placeholderData: (previous) => previous,
  });

  const setStatusMutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: "active" | "suspended" }) =>
      updateUserStatus(id, next),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
      setSuspendTarget(null);
    },
  });

  const bulk = useMutation({
    mutationFn: (next: "active" | "suspended") => bulkUpdateStatus([...selected], next),
    onSuccess: (summary) => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
      setBulkSummary(summary);
      setBulkIntent(null);
      setSelected(new Set());
    },
  });

  const resend = useMutation({
    mutationFn: (id: string) => resendInvite(id),
  });

  const visible = users.data?.items ?? [];
  // Your own row is never selectable: the server refuses it anyway, and offering a
  // checkbox that is guaranteed to come back "skipped" is just a trap.
  const selectable = visible.filter((row) => row.id !== me?.id);
  const allSelected = selectable.length > 0 && selectable.every((row) => selected.has(row.id));

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const columns: Column<UserSummary>[] = [
    ...(canChangeStatus
      ? [
          {
            key: "select",
            label: "Select",
            className: "w-10",
            header: (
              <Checkbox
                label=""
                aria-label="Select everyone on this page"
                checked={allSelected}
                onChange={() =>
                  setSelected(allSelected ? new Set() : new Set(selectable.map((r) => r.id)))
                }
              />
            ),
            cell: (row: UserSummary) =>
              row.id === me?.id ? null : (
                <Checkbox
                  label=""
                  aria-label={`Select ${row.full_name}`}
                  checked={selected.has(row.id)}
                  onChange={() => toggle(row.id)}
                />
              ),
          } satisfies Column<UserSummary>,
        ]
      : []),
    {
      key: "person",
      primary: true,
      header: "Name",
      cell: (row) => (
        <div className="flex min-w-0 items-center gap-2.5">
          <Avatar initials={initials(row.full_name)} />
          <div className="min-w-0">
            <p className="truncate font-semibold text-fg">{row.full_name}</p>
            <p className="truncate text-xs text-fg-2">{row.email}</p>
          </div>
        </div>
      ),
    },
    {
      key: "roles",
      header: "Roles",
      secondary: true,
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.roles.length === 0 && <span className="text-xs text-fg-3">—</span>}
          {row.roles.map((role) => (
            <Badge key={`${role.role_key}-${role.branch_id ?? role.institute_id ?? "platform"}`}>
              {ROLE_LABEL[role.role_key] ?? role.role_name}
            </Badge>
          ))}
        </div>
      ),
    },
    {
      key: "scope",
      header: "Scope",
      secondary: true,
      cell: (row) => (
        <div className="space-y-0.5">
          {row.roles.length === 0 && <span className="text-xs text-fg-3">&mdash;</span>}
          {[...new Set(row.roles.map(roleScopeLabel))].map((label) => (
            <p key={label} className="text-xs text-fg-2">
              {label}
            </p>
          ))}
        </div>
      ),
    },
    { key: "status", header: "Status", cell: (row) => <StatusBadge status={row.status} /> },
    {
      key: "last_login",
      header: "Last login",
      secondary: true,
      cell: (row) => <span className="text-sm text-fg-2">{formatRelative(row.last_login_at)}</span>,
    },
    {
      key: "actions",
      label: "Actions",
      header: <span className="sr-only">Actions</span>,
      className: "text-right",
      cell: (row) => (
        <div className="flex flex-wrap justify-end gap-1.5">
          {row.id === me?.id && <span className="px-2 text-xs text-fg-3">You</span>}
          {row.id !== me?.id && canAssignRole && (
            <Button size="sm" variant="ghost" onClick={() => setRoleTarget(row)}>
              Change role
            </Button>
          )}
          {row.id !== me?.id && canGrant && (
            <Button size="sm" variant="ghost" onClick={() => setAccessTarget(row)}>
              Access
            </Button>
          )}
          {row.status === "invited" && canInvite && (
            <Button
              size="sm"
              variant="ghost"
              loading={resend.isPending && resend.variables === row.id}
              onClick={() => resend.mutate(row.id)}
            >
              Resend invite
            </Button>
          )}
          {/* Suspending yourself is refused by the server (it would lock an institute
              out of its own account), so the action is not offered. */}
          {canChangeStatus && row.status !== "invited" && row.id !== me?.id && (
            <Button
              size="sm"
              variant={row.status === "suspended" ? "secondary" : "ghost"}
              loading={setStatusMutation.isPending && setStatusMutation.variables?.id === row.id}
              onClick={() => {
                if (row.status === "suspended") {
                  setStatusMutation.mutate({ id: row.id, next: "active" });
                } else {
                  setSuspendTarget(row);
                }
              }}
            >
              {row.status === "suspended" ? "Re-activate" : "Suspend"}
            </Button>
          )}
        </div>
      ),
    },
  ];

  const hasNext = Boolean(users.data?.next_cursor);
  const filtering = Boolean(search || status || role);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Users"
        description="Everyone you can see and manage in your scope."
        actions={
          canInvite && (
            <Button onClick={() => setInviteOpen(true)} icon={<PlusIcon />}>
              Invite user
            </Button>
          )
        }
      />

      {/* The send happens in the background and can fail — a wrong address, a provider
          rejection — without the request failing. Saying what *should* arrive, and naming
          the recovery, is more honest than a bare "Invited". */}
      {invited && (
        <Alert tone="success" title={`${invited} has been invited`}>
          <p>
            An email with a 6-digit setup code is on its way, valid for 48 hours. They set their own
            password with it — nobody else sees it, including you.
          </p>
          <p className="mt-1">
            If it does not arrive, check the address in the list below and use{" "}
            <strong className="font-semibold">Resend invite</strong> to send a fresh code.
          </p>
        </Alert>
      )}

      {bulkSummary && (
        <Alert
          tone={bulkSummary.skipped > 0 ? "warning" : "success"}
          title={`${bulkSummary.succeeded} ${bulkSummary.succeeded === 1 ? "account" : "accounts"} updated`}
        >
          {bulkSummary.skipped > 0 && (
            <>
              <p>
                {bulkSummary.skipped} {bulkSummary.skipped === 1 ? "was" : "were"} skipped:
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {bulkSummary.results
                  .filter((r) => r.outcome === "skipped")
                  .map((r) => (
                    <li key={r.user_id}>{r.reason}</li>
                  ))}
              </ul>
            </>
          )}
          <button
            type="button"
            onClick={() => setBulkSummary(null)}
            className="mt-2 text-xs font-semibold underline"
          >
            Dismiss
          </button>
        </Alert>
      )}

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-accent/40 bg-accent-soft px-4 py-3">
          <span className="text-sm font-semibold text-fg">{selected.size} selected</span>
          <div className="ml-auto flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setBulkIntent("active")}>
              Activate
            </Button>
            <Button size="sm" variant="danger" onClick={() => setBulkIntent("suspended")}>
              Suspend
            </Button>
          </div>
        </div>
      )}

      {resend.isSuccess && (
        // Dismissible, and cleared on the way out. It used to survive changing the filter
        // and paging forward, with no way to get rid of it, so it stopped reading as a
        // response to anything.
        <Alert tone="success" onDismiss={() => resend.reset()}>
          <p>A new setup code has been sent.</p>
        </Alert>
      )}
      {resend.error && (
        <Alert tone="danger">
          <p>{resend.error.message}</p>
        </Alert>
      )}
      {setStatusMutation.error && (
        <Alert tone="danger">
          <p>{setStatusMutation.error.message}</p>
        </Alert>
      )}

      <Card>
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-2 lg:grid-cols-[1fr_11rem_11rem]">
          <TextField
            label="Search"
            type="search"
            placeholder="Name or email address"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              if (params.has("q")) {
                // Drop the stale link parameter, or going back and forward would restore
                // a term the box no longer shows.
                const next = new URLSearchParams(params);
                next.delete("q");
                setParams(next, { replace: true });
              }
            }}
          />
          <SelectField
            label="Role"
            placeholder="All roles"
            value={role}
            onChange={(event) => setRole(event.target.value)}
            options={[
              { value: "super_admin", label: "Super Admin" },
              { value: "platform_admin", label: "Platform Admin" },
              { value: "institute_admin", label: "Institute Admin" },
              { value: "branch_admin", label: "Branch Admin" },
              { value: "faculty", label: "Faculty" },
              { value: "student", label: "Student" },
            ]}
          />
          <SelectField
            label="Status"
            placeholder="All statuses"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            options={[
              { value: "active", label: "Active" },
              { value: "invited", label: "Invited" },
              { value: "suspended", label: "Suspended" },
            ]}
          />
        </div>

        {users.error ? (
          <Alert tone="danger" className="m-4">
            <p>{users.error.message}</p>
          </Alert>
        ) : (
          <Table
            caption="Users in your scope"
            columns={columns}
            rows={users.data?.items ?? []}
            rowKey={(row) => row.id}
            loading={users.isLoading}
            empty={
              <EmptyState
                // Every filter, not two of them. Narrowing to a role nobody holds used to
                // say "No users yet · Invite someone to get started", which is both wrong
                // and unhelpful: there are users, just not that kind.
                title={filtering ? "No users match those filters" : "No users yet"}
                description={
                  filtering
                    ? "Try a different search or clear the filters."
                    : "Invite someone to get started."
                }
                action={
                  canInvite && !filtering ? (
                    <Button size="sm" onClick={() => setInviteOpen(true)}>
                      Invite user
                    </Button>
                  ) : undefined
                }
              />
            }
          />
        )}

        <Pagination
          pageIndex={pageIndex}
          pageSize={PAGE_SIZE}
          total={users.data?.total ?? 0}
          shown={visible.length}
          hasNext={hasNext}
          noun="users"
          onPrevious={() => setPageIndex((index) => Math.max(0, index - 1))}
          onNext={() => {
            const next = users.data?.next_cursor ?? null;
            setCursors((trail) => (trail.length > pageIndex + 1 ? trail : [...trail, next]));
            setPageIndex((index) => index + 1);
          }}
        />
      </Card>

      <InviteUserModal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        onInvited={setInvited}
      />
      <ChangeRoleModal
        user={roleTarget}
        open={roleTarget !== null}
        onClose={() => setRoleTarget(null)}
      />

      <UserAccessModal
        user={accessTarget}
        open={accessTarget !== null}
        onClose={() => setAccessTarget(null)}
      />

      <ConfirmDialog
        open={bulkIntent !== null}
        onClose={() => {
          setBulkIntent(null);
          bulk.reset();
        }}
        onConfirm={() => bulkIntent && bulk.mutate(bulkIntent)}
        title={
          bulkIntent === "suspended"
            ? `Suspend ${selected.size} ${selected.size === 1 ? "account" : "accounts"}?`
            : `Re-activate ${selected.size} ${selected.size === 1 ? "account" : "accounts"}?`
        }
        confirmLabel={bulkIntent === "suspended" ? "Suspend them" : "Re-activate them"}
        tone={bulkIntent === "suspended" ? "danger" : "primary"}
        pending={bulk.isPending}
        error={bulk.error?.message ?? null}
      >
        {bulkIntent === "suspended" ? (
          <>
            <p>
              They will be signed out of every device straight away and will not be able to sign in
              again. Nothing is deleted, and you can re-activate them at any time.
            </p>
            <p>
              Anyone you are not allowed to suspend is skipped, and you will be told who and why.
            </p>
          </>
        ) : (
          <p>
            They will be able to sign in again. Anyone who never set a password returns to "invited"
            rather than active, so their invitation still has to be completed.
          </p>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={suspendTarget !== null}
        onClose={() => {
          setSuspendTarget(null);
          setStatusMutation.reset();
        }}
        onConfirm={() =>
          suspendTarget && setStatusMutation.mutate({ id: suspendTarget.id, next: "suspended" })
        }
        title={`Suspend ${suspendTarget?.full_name ?? ""}?`}
        confirmLabel="Suspend this account"
        pending={setStatusMutation.isPending}
        error={setStatusMutation.error?.message ?? null}
      >
        <p>
          <strong className="font-semibold text-fg">{suspendTarget?.full_name}</strong> will be
          signed out of every device straight away and will not be able to sign in again.
        </p>
        <p>
          Nothing is deleted — their roles, classes and history stay exactly as they are, and you
          can re-activate the account at any time.
        </p>
      </ConfirmDialog>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" fill="none" aria-hidden>
      <path d="M8 3.5v9M3.5 8h9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
