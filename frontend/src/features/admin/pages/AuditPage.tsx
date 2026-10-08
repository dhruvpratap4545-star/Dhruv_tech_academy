import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { SelectField } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import type { Column } from "@/components/Table";
import { EmptyState, Table } from "@/components/Table";
import { auditKeys, fetchAuditLog } from "@/features/admin/api";
import type { AuditEntry } from "@/features/auth/types";
import { formatDateTime } from "@/lib/format";

/**
 * Audit log (PRD §7.6, §8).
 *
 * Read-only on purpose: the table is append-only, and an audit trail with an edit button
 * is not an audit trail. Scoping is the server's — platform staff see every event,
 * institute and branch admins only their own institutes.
 */

/** Grouped so the filter reads as a question a person would ask, not a list of keys. */
const ACTION_FILTERS: { value: string; label: string }[] = [
  { value: "login_success", label: "Successful sign-in" },
  { value: "login_failure", label: "Failed sign-in" },
  { value: "account_locked", label: "Account locked" },
  { value: "token_reuse_detected", label: "Session token reused" },
  { value: "password_reset_requested", label: "Password reset requested" },
  { value: "password_reset_completed", label: "Password reset completed" },
  { value: "password_changed", label: "Password changed" },
  { value: "user_registered", label: "User signed up" },
  { value: "user_invited", label: "User invited" },
  { value: "user_suspended", label: "User suspended" },
  { value: "user_reactivated", label: "User re-activated" },
  { value: "role_assigned", label: "Role given" },
  { value: "role_revoked", label: "Role taken away" },
  { value: "institute_created", label: "Institute created" },
];

const LABELS = new Map(ACTION_FILTERS.map((a) => [a.value, a.label]));

function actionLabel(action: string): string {
  return (
    LABELS.get(action) ??
    action.replace(/_/g, " ").replace(/^./, (character) => character.toUpperCase())
  );
}

/** Security-relevant events are coloured so they stand out when scanning. */
function actionTone(action: string): "neutral" | "success" | "warning" | "danger" {
  if (action === "login_success") return "success";
  if (action === "login_failure") return "warning";
  if (action === "account_locked" || action === "token_reuse_detected") return "danger";
  if (action === "user_suspended") return "danger";
  return "neutral";
}

export function AuditPage() {
  const [action, setAction] = useState("");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);

  // Changing the filter invalidates the cursor trail. Adjusted during render rather than
  // in an effect, so no stale page is committed first.
  const [lastAction, setLastAction] = useState(action);
  if (action !== lastAction) {
    setLastAction(action);
    setCursors([null]);
    setPageIndex(0);
  }

  const filters = {
    action: action || undefined,
    cursor: cursors[pageIndex] ?? undefined,
    limit: 25,
  };

  const log = useQuery({
    queryKey: auditKeys.list(filters),
    queryFn: ({ signal }) => fetchAuditLog(filters, signal),
    placeholderData: (previous) => previous,
  });

  const columns: Column<AuditEntry>[] = [
    {
      key: "when",
      primary: true,
      header: "When",
      cell: (row) => (
        <span className="num text-sm whitespace-nowrap text-fg-2">
          {formatDateTime(row.created_at)}
        </span>
      ),
    },
    {
      key: "action",
      header: "Event",
      cell: (row) => <Badge tone={actionTone(row.action)}>{actionLabel(row.action)}</Badge>,
    },
    {
      key: "target",
      header: "Target",
      secondary: true,
      cell: (row) =>
        row.target_type ? (
          <span className="text-sm text-fg-2">
            {row.target_type}
            {row.target_id && (
              <span className="mono ml-1 text-fg-3">{row.target_id.slice(0, 8)}</span>
            )}
          </span>
        ) : (
          <span className="text-fg-3">—</span>
        ),
    },
    {
      key: "ip",
      header: "From",
      secondary: true,
      cell: (row) => <span className="mono text-fg-3">{row.ip ?? "—"}</span>,
    },
    {
      key: "detail",
      header: "Detail",
      secondary: true,
      cell: (row) => {
        const entries = Object.entries(row.metadata ?? {});
        if (entries.length === 0) return <span className="text-fg-3">—</span>;
        return (
          <span className="text-xs text-fg-2">
            {entries
              .slice(0, 2)
              .map(([key, value]) => `${key}: ${String(value)}`)
              .join(", ")}
          </span>
        );
      },
    },
  ];

  const hasNext = Boolean(log.data?.next_cursor);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Administration"
        title="Audit log"
        description="Every security and administrative event, newest first. This record cannot be edited or deleted."
      />

      <Card>
        <div className="border-b border-line p-4">
          <div className="max-w-xs">
            <SelectField
              label="Event type"
              placeholder="All events"
              value={action}
              onChange={(event) => setAction(event.target.value)}
              options={ACTION_FILTERS}
            />
          </div>
        </div>

        {log.error ? (
          <Alert tone="danger" className="m-4">
            <p>{log.error.message}</p>
          </Alert>
        ) : (
          <Table
            caption="Audit events in your scope"
            columns={columns}
            rows={log.data?.items ?? []}
            rowKey={(row) => row.id}
            loading={log.isLoading}
            empty={
              <EmptyState
                title={action ? "No events of that type" : "No activity recorded yet"}
                description={
                  action
                    ? "Try a different event type, or clear the filter."
                    : "Events appear here as people sign in and administrators make changes."
                }
              />
            }
          />
        )}

        {(pageIndex > 0 || hasNext) && (
          <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-3">
            <Button
              size="sm"
              variant="secondary"
              disabled={pageIndex === 0}
              onClick={() => setPageIndex((index) => Math.max(0, index - 1))}
            >
              Previous
            </Button>
            <span className="text-xs text-fg-3">Page {pageIndex + 1}</span>
            <Button
              size="sm"
              variant="secondary"
              disabled={!hasNext}
              onClick={() => {
                const next = log.data?.next_cursor ?? null;
                setCursors((trail) => (trail.length > pageIndex + 1 ? trail : [...trail, next]));
                setPageIndex((index) => index + 1);
              }}
            >
              Next
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
