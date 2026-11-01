import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { SelectField } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { Pagination } from "@/components/Pagination";
import type { Column } from "@/components/Table";
import { EmptyState, Table } from "@/components/Table";
import type { Homework, HomeworkStatus } from "@/features/homework/api";
import { fetchHomeworkList, homeworkKeys } from "@/features/homework/api";
import { HomeworkLayout } from "@/features/homework/components/HomeworkLayout";
import { HomeworkStatusBadge } from "@/features/homework/components/StatusBadges";
import { useClassOptions } from "@/features/homework/components/useClassOptions";
import { useT } from "@/features/i18n/useT";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 20;

/** Homework for the classes a teacher teaches, or an admin manages. */
export function TeacherListPage() {
  const { t } = useT();
  const navigate = useNavigate();
  const { options } = useClassOptions();
  const [classId, setClassId] = useState("");
  const [status, setStatus] = useState<HomeworkStatus | "">("");
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);
  const filters = {
    class_id: classId || undefined,
    status: status || undefined,
    cursor: cursors[pageIndex] ?? undefined,
    limit: PAGE_SIZE,
  };
  const list = useQuery({
    queryKey: homeworkKeys.list(filters),
    queryFn: ({ signal }) => fetchHomeworkList(filters, signal),
    placeholderData: (previous) => previous,
  });

  function reset() {
    setCursors([null]);
    setPageIndex(0);
  }

  const columns: Column<Homework>[] = [
    {
      key: "title",
      header: t("homework.col.title"),
      primary: true,
      cell: (h) => (
        <div className="min-w-0">
          <p className="font-medium text-fg">{h.title}</p>
          <p className="text-xs text-fg-2">{h.subject}</p>
        </div>
      ),
    },
    { key: "class", header: t("homework.col.class"), cell: (h) => h.class_name },
    {
      key: "due",
      header: t("homework.col.due"),
      cell: (h) => <span className="num text-sm text-fg-2">{formatDateTime(h.due_at)}</span>,
    },
    {
      key: "status",
      header: t("homework.col.status"),
      cell: (h) => <HomeworkStatusBadge homework={h} />,
    },
  ];

  const page = list.data;
  return (
    <HomeworkLayout
      title={t("homework.list.title")}
      description={t("homework.list.description")}
      actions={
        <Link to="/homework/new">
          <Button icon={<Icon name="plus" />}>{t("homework.new")}</Button>
        </Link>
      }
    >
      <Card className="grid gap-3 p-4 sm:grid-cols-2">
        <SelectField
          label={t("homework.filter.class")}
          value={classId}
          onChange={(e) => {
            setClassId(e.target.value);
            reset();
          }}
          options={[{ value: "", label: t("common.all") }, ...options]}
        />
        <SelectField
          label={t("homework.filter.status")}
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as HomeworkStatus | "");
            reset();
          }}
          options={[
            { value: "", label: t("common.all") },
            { value: "draft", label: t("homework.status.draft") },
            { value: "published", label: t("homework.status.published") },
            { value: "archived", label: t("homework.status.archived") },
          ]}
        />
      </Card>
      {list.error && <Alert tone="danger">{list.error.message}</Alert>}
      <Card>
        <Table
          columns={columns}
          rows={page?.items ?? []}
          rowKey={(h) => h.id}
          loading={list.isLoading}
          onRowClick={(h) => navigate(`/homework/${h.id}`)}
          empty={<EmptyState title={t("homework.empty")} />}
        />
        {page && page.total > 0 && (
          <Pagination
            pageIndex={pageIndex}
            pageSize={PAGE_SIZE}
            total={page.total}
            shown={page.items.length}
            hasNext={Boolean(page.next_cursor)}
            noun="homework"
            onPrevious={() => setPageIndex((i) => Math.max(0, i - 1))}
            onNext={() => {
              if (!page.next_cursor) return;
              setCursors((trail) => [...trail.slice(0, pageIndex + 1), page.next_cursor]);
              setPageIndex((i) => i + 1);
            }}
          />
        )}
      </Card>
    </HomeworkLayout>
  );
}
