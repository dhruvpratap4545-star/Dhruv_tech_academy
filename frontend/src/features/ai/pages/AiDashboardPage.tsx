import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { SelectField } from "@/components/Field";
import { Spinner } from "@/components/Spinner";
import type { Column } from "@/components/Table";
import { Table } from "@/components/Table";
import type { UsageGroup } from "@/features/ai/api";
import {
  aiKeys,
  fetchInstituteBudgets,
  fetchSettings,
  fetchSummary,
  updateSettings,
} from "@/features/ai/api";
import { AiLayout } from "@/features/ai/components/AiLayout";
import { BudgetBar, StatTile, Switch, TrendChart } from "@/features/ai/components/widgets";
import { useCan } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { formatRupees } from "@/lib/format";

/** AI Usage Dashboard: today, this month, spend against budget, where it goes. */
export function AiDashboardPage() {
  const { t } = useT();
  const canManage = useCan("ai:manage");
  // One institute: the backend shows its allocation. Several (an organisation's admin, or
  // platform staff): pick one to see its allocation, or "All" for the combined figures.
  const [instituteId, setInstituteId] = useState("");
  const institutes = useQuery({
    queryKey: aiKeys.instituteBudgets,
    queryFn: ({ signal }) => fetchInstituteBudgets(signal),
  });
  const summary = useQuery({
    queryKey: aiKeys.summary(instituteId || undefined),
    queryFn: ({ signal }) => fetchSummary(instituteId || undefined, signal),
  });

  const groupColumns: Column<UsageGroup>[] = [
    { key: "label", header: t("ai.byFeature"), primary: true, cell: (g) => g.label },
    {
      key: "requests",
      header: t("ai.requests"),
      cell: (g) => <span className="num">{g.requests.toLocaleString("en-IN")}</span>,
    },
    {
      key: "tokens",
      header: t("ai.tokens"),
      secondary: true,
      cell: (g) => <span className="num">{g.tokens.toLocaleString("en-IN")}</span>,
    },
    {
      key: "cost",
      header: t("ai.cost"),
      cell: (g) => <span className="num">{formatRupees(g.cost_paise)}</span>,
    },
  ];

  const data = summary.data;
  return (
    <AiLayout title={t("ai.dashboard.title")} description={t("ai.dashboard.description")}>
      {canManage && <GlobalSwitch />}
      {(institutes.data?.length ?? 0) > 1 && (
        <SelectField
          label="Institute"
          value={instituteId}
          onChange={(event) => setInstituteId(event.target.value)}
          options={[
            { value: "", label: t("common.all") },
            ...(institutes.data ?? []).map((b) => ({
              value: b.institute_id ?? "",
              label: b.institute_name ?? "",
            })),
          ]}
        />
      )}
      {summary.isLoading && <Spinner />}
      {summary.error && <Alert tone="danger">{summary.error.message}</Alert>}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile
              label={`${t("ai.today")} · ${t("ai.requests")}`}
              value={data.today.requests.toLocaleString("en-IN")}
              sub={`${t("ai.blocked")}: ${data.today.blocked}`}
            />
            <StatTile
              label={`${t("ai.today")} · ${t("ai.cost")}`}
              value={formatRupees(data.today.cost_paise)}
            />
            <StatTile
              label={`${t("ai.month")} · ${t("ai.requests")}`}
              value={data.month.requests.toLocaleString("en-IN")}
              sub={`${t("ai.errors")}: ${data.month.errors}`}
            />
            <StatTile
              label={`${t("ai.month")} · ${t("ai.cost")}`}
              value={formatRupees(data.month.cost_paise)}
            />
          </div>

          {data.budget && (
            <Card>
              <CardHeader
                title={t("ai.budget")}
                description={
                  data.budget.configured && (data.budget.limit_paise || data.budget.limit_tokens)
                    ? data.budget.limit_paise
                      ? t("ai.used", {
                          used: formatRupees(data.budget.used_paise),
                          limit: formatRupees(data.budget.limit_paise),
                        })
                      : t("ai.used", {
                          used: data.budget.used_tokens.toLocaleString("en-IN"),
                          limit: (data.budget.limit_tokens ?? 0).toLocaleString("en-IN"),
                        })
                    : t("ai.noBudget")
                }
              />
              <CardBody>
                <BudgetBar percent={data.budget.percent_used} />
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title={t("ai.trend")} />
            <CardBody>
              <TrendChart days={data.trend} caption={t("ai.trend")} />
            </CardBody>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title={t("ai.byFeature")} />
              <Table columns={groupColumns} rows={data.by_feature} rowKey={(g) => g.label} />
            </Card>
            <Card>
              <CardHeader title={t("ai.byInstitute")} />
              <Table
                columns={[
                  { ...groupColumns[0]!, header: t("ai.byInstitute") },
                  ...groupColumns.slice(1),
                ]}
                rows={data.by_institute}
                rowKey={(g) => g.key ?? "platform"}
              />
            </Card>
          </div>
        </>
      )}
    </AiLayout>
  );
}

function GlobalSwitch() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: aiKeys.settings,
    queryFn: ({ signal }) => fetchSettings(signal),
  });
  const save = useMutation({
    mutationFn: (global_enabled: boolean) => updateSettings({ global_enabled }),
    onSuccess: (data) => queryClient.setQueryData(aiKeys.settings, data),
  });
  if (!settings.data) return null;
  return (
    <Card className="flex items-center justify-between gap-4 p-4">
      <div>
        <p className="font-semibold text-fg">{t("ai.globalSwitch")}</p>
        <p className="text-sm text-fg-2">{t("ai.globalSwitchHint")}</p>
      </div>
      <Switch
        checked={settings.data.global_enabled}
        label={t("ai.globalSwitch")}
        disabled={save.isPending}
        onChange={(next) => save.mutate(next)}
      />
    </Card>
  );
}
