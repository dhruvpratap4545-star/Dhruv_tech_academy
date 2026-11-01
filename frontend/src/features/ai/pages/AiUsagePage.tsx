import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import { Pagination } from "@/components/Pagination";
import type { Column } from "@/components/Table";
import { EmptyState, Table } from "@/components/Table";
import type { AiUsageRow, UsageFilters } from "@/features/ai/api";
import { aiKeys, downloadUsage, fetchInstituteBudgets, fetchUsage } from "@/features/ai/api";
import { AiLayout } from "@/features/ai/components/AiLayout";
import { useT } from "@/features/i18n/useT";
import { formatDateTime, formatRupees, humanise } from "@/lib/format";

const PAGE_SIZE = 25;

const STATUS_TONE = {
  ok: "success",
  cached: "accent",
  blocked: "warning",
  error: "danger",
} as const;

/** Every AI request in scope, newest first, with filters and an Excel export. */
export function AiUsagePage() {
  const { t } = useT();
  const [filters, setFilters] = useState<Omit<UsageFilters, "cursor" | "limit">>({});
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);
  const institutes = useQuery({
    queryKey: aiKeys.instituteBudgets,
    queryFn: ({ signal }) => fetchInstituteBudgets(signal),
  });
  const request = { ...filters, cursor: cursors[pageIndex] ?? undefined, limit: PAGE_SIZE };
  const usage = useQuery({
    queryKey: aiKeys.usage(request),
    queryFn: ({ signal }) => fetchUsage(request, signal),
    placeholderData: (previous) => previous,
  });
  const exportFile = useMutation({ mutationFn: () => downloadUsage(filters) });
  const names = new Map((institutes.data ?? []).map((b) => [b.institute_id, b.institute_name]));

  function setFilter(key: keyof typeof filters, value: string) {
    setFilters({ ...filters, [key]: value || undefined });
    setCursors([null]);
    setPageIndex(0);
  }

  const columns: Column<AiUsageRow>[] = [
    {
      key: "when",
      header: "When",
      primary: true,
      cell: (r) => <span className="num text-sm text-fg-2">{formatDateTime(r.created_at)}</span>,
    },
    {
      key: "institute",
      header: "Institute",
      cell: (r) => (r.institute_id ? (names.get(r.institute_id) ?? "—") : "Platform"),
    },
    { key: "feature", header: "Feature", cell: (r) => humanise(r.feature_key) },
    {
      key: "role",
      header: "Role",
      secondary: true,
      cell: (r) => (r.role_key ? humanise(r.role_key) : "—"),
    },
    {
      key: "model",
      header: "Model",
      secondary: true,
      cell: (r) => (
        <span className="mono text-xs">
          {r.model_id ?? "—"}
          {r.fallback_used && " (backup)"}
        </span>
      ),
    },
    {
      key: "tokens",
      header: t("ai.tokens"),
      cell: (r) => (
        <span className="num">{(r.input_tokens + r.output_tokens).toLocaleString("en-IN")}</span>
      ),
    },
    {
      key: "cost",
      header: t("ai.cost"),
      cell: (r) => <span className="num">{formatRupees(r.cost_paise)}</span>,
    },
    {
      key: "status",
      header: "Status",
      cell: (r) => (
        <Badge tone={STATUS_TONE[r.status]}>
          {humanise(r.status)}
          {r.block_reason ? ` · ${humanise(r.block_reason)}` : ""}
        </Badge>
      ),
    },
  ];

  const page = usage.data;
  return (
    <AiLayout
      title={t("ai.nav.usage")}
      actions={
        <Button
          variant="secondary"
          loading={exportFile.isPending}
          onClick={() => exportFile.mutate()}
        >
          {t("common.export")}
        </Button>
      }
    >
      <Card className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
        <SelectField
          label="Institute"
          value={filters.institute_id ?? ""}
          onChange={(e) => setFilter("institute_id", e.target.value)}
          options={[
            { value: "", label: t("common.all") },
            ...(institutes.data ?? []).map((b) => ({
              value: b.institute_id ?? "",
              label: b.institute_name ?? "",
            })),
          ]}
        />
        <TextField
          label="Feature"
          value={filters.feature ?? ""}
          onChange={(e) => setFilter("feature", e.target.value)}
          placeholder="playground"
        />
        <SelectField
          label="Status"
          value={filters.status ?? ""}
          onChange={(e) => setFilter("status", e.target.value)}
          options={[
            { value: "", label: t("common.all") },
            { value: "ok", label: "OK" },
            { value: "cached", label: "Cached" },
            { value: "blocked", label: "Blocked" },
            { value: "error", label: "Error" },
          ]}
        />
        <TextField
          label="From"
          type="date"
          value={filters.date_from ?? ""}
          onChange={(e) => setFilter("date_from", e.target.value)}
        />
        <TextField
          label="To"
          type="date"
          value={filters.date_to ?? ""}
          onChange={(e) => setFilter("date_to", e.target.value)}
        />
      </Card>
      {exportFile.error && <Alert tone="danger">{exportFile.error.message}</Alert>}
      <Card>
        <Table
          columns={columns}
          rows={page?.items ?? []}
          rowKey={(r) => r.id}
          loading={usage.isLoading}
          empty={<EmptyState title="No AI requests match these filters" />}
        />
        {page && page.total > 0 && (
          <Pagination
            pageIndex={pageIndex}
            pageSize={PAGE_SIZE}
            total={page.total}
            shown={page.items.length}
            hasNext={Boolean(page.next_cursor)}
            noun="requests"
            onPrevious={() => setPageIndex((i) => Math.max(0, i - 1))}
            onNext={() => {
              if (!page.next_cursor) return;
              setCursors((trail) => [...trail.slice(0, pageIndex + 1), page.next_cursor]);
              setPageIndex((i) => i + 1);
            }}
          />
        )}
      </Card>
    </AiLayout>
  );
}
