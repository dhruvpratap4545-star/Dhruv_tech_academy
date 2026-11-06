import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import { Modal } from "@/components/Modal";
import type { Column } from "@/components/Table";
import { Table } from "@/components/Table";
import type { AiBudget } from "@/features/ai/api";
import {
  aiKeys,
  fetchFeatureNames,
  fetchInstituteBudgets,
  fetchPlatformBudget,
  fetchRoleLimits,
  updateInstituteBudget,
  updatePlatformBudget,
  updateRoleLimits,
} from "@/features/ai/api";
import { AiLayout } from "@/features/ai/components/AiLayout";
import { BudgetBar, Switch } from "@/features/ai/components/widgets";
import { paiseToRupees, rupeesToPaise } from "@/features/ai/money";
import { useCan } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";
import { formatRupees, humanise } from "@/lib/format";

const EXCEED_OPTIONS = [
  { value: "block", label: "Block AI requests" },
  { value: "fallback", label: "Switch to the backup model" },
];

/**
 * Budgets & Limits. Platform staff set the platform budget, each institute's allocation
 * and kill switch, and the default daily limits. An institute admin sees their own
 * allocation, may split it between features, switch features off, and lower limits.
 */
export function AiBudgetsPage() {
  const { t } = useT();
  const canManage = useCan("ai:manage");
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<AiBudget | null>(null);

  const budgets = useQuery({
    queryKey: aiKeys.instituteBudgets,
    queryFn: ({ signal }) => fetchInstituteBudgets(signal),
  });
  const toggle = useMutation({
    mutationFn: (b: AiBudget) => updateInstituteBudget(b.institute_id!, { enabled: !b.enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: aiKeys.all }),
  });

  const columns: Column<AiBudget>[] = [
    { key: "name", header: "Institute", primary: true, cell: (b) => b.institute_name },
    {
      key: "limit",
      header: "Allocation",
      cell: (b) =>
        b.limit_paise ? (
          <span className="num">{formatRupees(b.limit_paise)}</span>
        ) : b.limit_tokens ? (
          <span className="num">{b.limit_tokens.toLocaleString("en-IN")} tokens</span>
        ) : (
          <span className="text-fg-3">No cap</span>
        ),
    },
    {
      key: "used",
      header: "Used",
      cell: (b) => (
        <div className="min-w-28 space-y-1">
          <span className="num text-sm">{formatRupees(b.used_paise)}</span>
          {b.percent_used !== null && <BudgetBar percent={b.percent_used} />}
        </div>
      ),
    },
    {
      key: "exceed",
      header: "At 100%",
      secondary: true,
      cell: (b) => (b.on_exceed === "block" ? "Block" : "Backup model"),
    },
    {
      key: "enabled",
      header: "AI on",
      cell: (b) =>
        canManage ? (
          <Switch
            checked={b.enabled}
            label={`AI for ${b.institute_name}`}
            disabled={toggle.isPending}
            onChange={() => toggle.mutate(b)}
          />
        ) : (
          <Badge tone={b.enabled ? "success" : "danger"}>
            {b.enabled ? t("common.on") : t("common.off")}
          </Badge>
        ),
    },
    {
      key: "edit",
      header: "",
      cell: (b) => (
        <Button size="sm" variant="secondary" onClick={() => setEditing(b)}>
          {t("common.edit")}
        </Button>
      ),
    },
  ];

  return (
    <AiLayout title={t("ai.nav.budgets")}>
      {canManage && <PlatformBudgetCard />}
      <Card>
        <CardHeader
          title="Institute allocations"
          description="This month. A new month starts with last month's allocation and the counters at zero."
        />
        {toggle.error instanceof ApiError && <Alert tone="danger">{toggle.error.message}</Alert>}
        <Table
          columns={columns}
          rows={budgets.data ?? []}
          rowKey={(b) => b.institute_id ?? "platform"}
          loading={budgets.isLoading}
        />
      </Card>
      <RoleLimitsCard institutes={budgets.data ?? []} />
      {editing && (
        <EditAllocation budget={editing} canManage={canManage} onClose={() => setEditing(null)} />
      )}
    </AiLayout>
  );
}

function PlatformBudgetCard() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const budget = useQuery({
    queryKey: aiKeys.platformBudget,
    queryFn: ({ signal }) => fetchPlatformBudget(signal),
  });
  const [rupees, setRupees] = useState<string | null>(null);
  const [onExceed, setOnExceed] = useState<"block" | "fallback" | null>(null);
  const save = useMutation({
    mutationFn: () =>
      updatePlatformBudget({
        limit_paise: rupeesToPaise(rupees ?? paiseToRupees(budget.data?.limit_paise)),
        limit_tokens: budget.data?.limit_tokens ?? null,
        on_exceed: onExceed ?? budget.data?.on_exceed ?? "block",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: aiKeys.all }),
  });
  if (!budget.data) return null;
  const b = budget.data;
  return (
    <Card>
      <CardHeader
        title={`Platform budget · ${b.month}`}
        description={
          b.limit_paise
            ? t("ai.used", { used: formatRupees(b.used_paise), limit: formatRupees(b.limit_paise) })
            : "No platform cap set."
        }
      />
      <CardBody className="space-y-4">
        <BudgetBar percent={b.percent_used} />
        <form
          className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <TextField
            label="Monthly budget (₹)"
            inputMode="decimal"
            value={rupees ?? paiseToRupees(b.limit_paise)}
            onChange={(event) => setRupees(event.target.value)}
            hint="Leave empty for no cap."
          />
          <SelectField
            label="At 100%"
            value={onExceed ?? b.on_exceed}
            onChange={(event) => setOnExceed(event.target.value as "block" | "fallback")}
            options={EXCEED_OPTIONS}
          />
          <Button type="submit" loading={save.isPending}>
            {t("common.save")}
          </Button>
        </form>
        {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
      </CardBody>
    </Card>
  );
}

function EditAllocation({
  budget,
  canManage,
  onClose,
}: {
  budget: AiBudget;
  canManage: boolean;
  onClose: () => void;
}) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const features = useQuery({
    queryKey: aiKeys.featureNames,
    queryFn: ({ signal }) => fetchFeatureNames(signal),
  });
  const [limit, setLimit] = useState(paiseToRupees(budget.limit_paise));
  const [onExceed, setOnExceed] = useState(budget.on_exceed);
  const [shares, setShares] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(budget.feature_limits).map(([k, v]) => [k, paiseToRupees(v)]),
    ),
  );
  const [disabled, setDisabled] = useState<string[]>(budget.disabled_features);

  const save = useMutation({
    mutationFn: () => {
      const feature_limits = Object.fromEntries(
        Object.entries(shares)
          .map(([k, v]) => [k, rupeesToPaise(v)] as const)
          .filter((entry): entry is readonly [string, number] => entry[1] !== null),
      );
      return updateInstituteBudget(budget.institute_id!, {
        ...(canManage ? { limit_paise: rupeesToPaise(limit), on_exceed: onExceed } : {}),
        feature_limits,
        disabled_features: disabled,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiKeys.all });
      onClose();
    },
  });

  return (
    <Modal
      open
      onClose={onClose}
      title={budget.institute_name ?? "Institute"}
      description={`AI allocation for ${budget.month}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {canManage && (
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField
              label="Monthly allocation (₹)"
              inputMode="decimal"
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
              hint="Leave empty for no cap."
            />
            <SelectField
              label="At 100%"
              value={onExceed}
              onChange={(event) => setOnExceed(event.target.value as "block" | "fallback")}
              options={EXCEED_OPTIONS}
            />
          </div>
        )}
        <div className="space-y-2">
          <p className="text-sm font-medium text-fg">Share by feature (₹ per month)</p>
          {(features.data ?? []).map(({ key, name }) => (
            <div key={key} className="flex items-end gap-3">
              <div className="flex-1">
                <TextField
                  label={name || humanise(key)}
                  inputMode="decimal"
                  value={shares[key] ?? ""}
                  onChange={(event) => setShares({ ...shares, [key]: event.target.value })}
                />
              </div>
              <label className="mb-3 flex items-center gap-2 text-sm text-fg-2">
                <input
                  type="checkbox"
                  checked={!disabled.includes(key)}
                  onChange={(event) =>
                    setDisabled(
                      event.target.checked ? disabled.filter((d) => d !== key) : [...disabled, key],
                    )
                  }
                />
                {t("common.on")}
              </label>
            </div>
          ))}
        </div>
        {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
      </div>
    </Modal>
  );
}

function RoleLimitsCard({ institutes }: { institutes: AiBudget[] }) {
  const { t } = useT();
  const canManage = useCan("ai:manage");
  const queryClient = useQueryClient();
  const [instituteId, setInstituteId] = useState<string>(
    canManage ? "" : (institutes[0]?.institute_id ?? ""),
  );
  const target = instituteId || (canManage ? undefined : institutes[0]?.institute_id) || undefined;
  const limits = useQuery({
    queryKey: aiKeys.roleLimits(target),
    queryFn: ({ signal }) => fetchRoleLimits(target, signal),
    enabled: canManage || Boolean(target),
  });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () =>
      updateRoleLimits({
        institute_id: target,
        limits: Object.fromEntries(
          Object.entries(draft)
            .filter(([, v]) => v.trim() !== "")
            .map(([k, v]) => [k, Number(v)]),
        ),
      }),
    onSuccess: () => {
      setDraft({});
      void queryClient.invalidateQueries({ queryKey: ["ai", "role-limits"] });
    },
  });

  return (
    <Card>
      <CardHeader
        title="Daily AI requests per person"
        description={
          target
            ? "This institute's limits. They can be lowered below the platform default, never raised above it."
            : "Platform defaults, used by every institute that has not lowered them."
        }
        actions={
          <SelectField
            label="Applies to"
            value={instituteId}
            onChange={(event) => {
              setInstituteId(event.target.value);
              setDraft({});
            }}
            options={[
              ...(canManage ? [{ value: "", label: "Platform defaults" }] : []),
              ...institutes.map((b) => ({
                value: b.institute_id ?? "",
                label: b.institute_name ?? "Institute",
              })),
            ]}
          />
        }
      />
      <CardBody className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(limits.data ?? []).map((row) => (
            <TextField
              key={row.role_key}
              label={humanise(row.role_key)}
              type="number"
              min={0}
              value={
                draft[row.role_key] ??
                String(
                  target ? (row.institute_value ?? row.platform_default) : row.platform_default,
                )
              }
              hint={target ? `Platform default ${row.platform_default}` : undefined}
              onChange={(event) => setDraft({ ...draft, [row.role_key]: event.target.value })}
            />
          ))}
        </div>
        {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
        <Button
          disabled={Object.keys(draft).length === 0}
          loading={save.isPending}
          onClick={() => save.mutate()}
        >
          {t("common.save")}
        </Button>
      </CardBody>
    </Card>
  );
}
