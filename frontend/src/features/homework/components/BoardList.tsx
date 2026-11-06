import { Link } from "react-router-dom";

import { Card } from "@/components/Card";
import { EmptyState } from "@/components/Table";
import type { BoardRow } from "@/features/homework/api";
import { StudentStatusBadge } from "@/features/homework/components/StatusBadges";
import { sortByDue } from "@/features/homework/logic";
import { useT } from "@/features/i18n/useT";
import { formatDateTime } from "@/lib/format";

/** A student's or a parent's list of homework, soonest due first. */
export function BoardList({
  rows,
  empty,
  studentId,
}: {
  rows: BoardRow[];
  empty: string;
  /** A parent's chosen child, carried to the detail page so it shows that child's work. */
  studentId?: string;
}) {
  const { t } = useT();
  if (rows.length === 0) return <EmptyState title={empty} />;
  return (
    <ul className="space-y-3">
      {sortByDue(rows).map(({ homework, student_status, submission }) => (
        <li key={homework.id}>
          <Link
            to={`/homework/${homework.id}${studentId ? `?student=${studentId}` : ""}`}
            className="block"
          >
            <Card className="space-y-2 p-4 transition-colors hover:bg-surface-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-semibold text-fg">{homework.title}</p>
                  <p className="text-sm text-fg-2">
                    {homework.subject} · {homework.class_name}
                  </p>
                </div>
                <StudentStatusBadge status={student_status} late={submission?.is_late} />
              </div>
              <p className="num text-xs text-fg-2">
                {t("homework.detail.due", { when: formatDateTime(homework.due_at) })}
                {submission?.marks != null &&
                  ` · ${t("homework.result.marks")}: ${submission.marks}${homework.total_marks != null ? ` / ${homework.total_marks}` : ""}`}
              </p>
              {submission?.remark && (
                <p className="text-sm whitespace-pre-wrap text-fg-2">
                  {t("homework.result.remark")}: {submission.remark}
                </p>
              )}
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
