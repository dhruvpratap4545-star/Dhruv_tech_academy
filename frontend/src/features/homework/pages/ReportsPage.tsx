import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Card, CardHeader } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import { Spinner } from "@/components/Spinner";
import type { Column } from "@/components/Table";
import { Table } from "@/components/Table";
import type { ReportFilters, ReportRow } from "@/features/homework/api";
import { downloadReport, fetchReport, homeworkKeys } from "@/features/homework/api";
import { HomeworkLayout } from "@/features/homework/components/HomeworkLayout";
import { useClassOptions } from "@/features/homework/components/useClassOptions";
import { useT } from "@/features/i18n/useT";

const percent = (rate: number) => `${Math.round(rate * 1000) / 10}%`;

/** Completion by class, subject and teacher, with an Excel export of the same filters. */
export function ReportsPage() {
  const { t } = useT();
  const { options } = useClassOptions();
  const [filters, setFilters] = useState<ReportFilters>({});
  const report = useQuery({
    queryKey: homeworkKeys.report(filters),
    queryFn: ({ signal }) => fetchReport(filters, signal),
  });
  const exportFile = useMutation({ mutationFn: () => downloadReport(filters) });
  const set = (key: keyof ReportFilters, value: string) =>
    setFilters({ ...filters, [key]: value || undefined });

  const columns = (heading: string): Column<ReportRow>[] => [
    { key: "label", header: heading, primary: true, cell: (r) => r.label },
    {
      key: "homework",
      header: t("homework.reports.homework"),
      cell: (r) => <span className="num">{r.homework}</span>,
    },
    {
      key: "expected",
      header: t("homework.reports.expected"),
      secondary: true,
      cell: (r) => <span className="num">{r.expected}</span>,
    },
    {
      key: "submitted",
      header: t("homework.reports.submitted"),
      cell: (r) => <span className="num">{r.submitted}</span>,
    },
    {
      key: "late",
      header: t("homework.reports.late"),
      secondary: true,
      cell: (r) => <span className="num">{r.late}</span>,
    },
    {
      key: "rate",
      header: t("homework.reports.rate"),
      cell: (r) => <span className="num">{percent(r.completion_rate)}</span>,
    },
  ];

  const data = report.data;
  return (
    <HomeworkLayout
      title={t("homework.reports.title")}
      description={t("homework.reports.description")}
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
      <Card className="grid gap-3 p-4 sm:grid-cols-3">
        <SelectField
          label={t("homework.filter.class")}
          value={filters.class_id ?? ""}
          onChange={(e) => set("class_id", e.target.value)}
          options={[{ value: "", label: t("common.all") }, ...options]}
        />
        <TextField
          label={t("homework.reports.from")}
          type="date"
          value={filters.from ?? ""}
          onChange={(e) => set("from", e.target.value)}
        />
        <TextField
          label={t("homework.reports.to")}
          type="date"
          value={filters.to ?? ""}
          onChange={(e) => set("to", e.target.value)}
        />
      </Card>
      {exportFile.error && <Alert tone="danger">{exportFile.error.message}</Alert>}
      {report.isLoading && <Spinner />}
      {report.error && <Alert tone="danger">{report.error.message}</Alert>}
      {data && (
        <>
          <Card className="p-4">
            <p className="eyebrow">{t("homework.reports.total")}</p>
            <p className="num mt-1 font-display text-2xl font-extrabold text-fg">
              {percent(data.totals.completion_rate)}
            </p>
            <p className="num text-xs text-fg-2">
              {data.totals.submitted} / {data.totals.expected}
            </p>
          </Card>
          {(
            [
              ["homework.reports.byClass", data.by_class],
              ["homework.reports.bySubject", data.by_subject],
              ["homework.reports.byTeacher", data.by_teacher],
            ] as const
          ).map(([label, rows]) => (
            <Card key={label}>
              <CardHeader title={t(label)} />
              <Table
                columns={columns(t("homework.reports.name"))}
                rows={rows}
                rowKey={(r) => r.key ?? r.label}
              />
            </Card>
          ))}
        </>
      )}
    </HomeworkLayout>
  );
}
