import { Badge } from "@/components/Badge";
import type { Homework, StudentStatus } from "@/features/homework/api";
import { STATUS_TONE } from "@/features/homework/logic";
import { useT } from "@/features/i18n/useT";

export function StudentStatusBadge({ status, late }: { status: StudentStatus; late?: boolean }) {
  const { t } = useT();
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Badge tone={STATUS_TONE[status]}>{t(`homework.student.${status}` as const)}</Badge>
      {late && <Badge tone="warning">{t("homework.late")}</Badge>}
    </span>
  );
}

/** Draft / Scheduled / Published / Archived, as a teacher reads their list. */
export function HomeworkStatusBadge({ homework }: { homework: Homework }) {
  const { t } = useT();
  if (homework.status === "published" && !homework.is_visible) {
    return <Badge tone="warning">{t("homework.status.scheduled")}</Badge>;
  }
  const tone =
    homework.status === "published"
      ? "success"
      : homework.status === "draft"
        ? "neutral"
        : "danger";
  return <Badge tone={tone}>{t(`homework.status.${homework.status}` as const)}</Badge>;
}
