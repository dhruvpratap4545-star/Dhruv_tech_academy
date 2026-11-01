import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Spinner } from "@/components/Spinner";
import type { Column } from "@/components/Table";
import { Table } from "@/components/Table";
import type { BoardRow, Homework, TrackerRow } from "@/features/homework/api";
import {
  archiveHomework,
  duplicateHomework,
  fetchHomework,
  fetchShareText,
  fetchTracker,
  homeworkKeys,
  publishHomework,
  remindPending,
} from "@/features/homework/api";
import { AttachmentList } from "@/features/homework/components/AttachmentList";
import { CheckModal } from "@/features/homework/components/CheckModal";
import { HomeworkLayout } from "@/features/homework/components/HomeworkLayout";
import {
  HomeworkStatusBadge,
  StudentStatusBadge,
} from "@/features/homework/components/StatusBadges";
import { SubmitForm } from "@/features/homework/components/SubmitForm";
import { canStillSubmit, whatsappUrl } from "@/features/homework/logic";
import { useCan } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

/** `/homework/:id` — the tracker for a teacher, the work and the submit form for a learner. */
export function HomeworkDetailPage() {
  const { id } = useParams();
  const canManage = useCan("homework:manage");
  const detail = useQuery({
    queryKey: homeworkKeys.detail(id!),
    queryFn: ({ signal }) => fetchHomework(id!, signal),
  });
  if (detail.isLoading) return <Spinner />;
  if (detail.error || !detail.data) {
    return <Alert tone="danger">{detail.error?.message ?? "Not found."}</Alert>;
  }
  return canManage ? (
    <TeacherView homework={detail.data.homework} />
  ) : (
    <LearnerView row={detail.data} />
  );
}

function Summary({ homework }: { homework: Homework }) {
  const { t } = useT();
  return (
    <Card>
      <CardBody className="space-y-4">
        <p className="num text-sm text-fg-2">
          {homework.subject} · {homework.class_name} ·{" "}
          {t("homework.detail.due", { when: formatDateTime(homework.due_at) })}
          {homework.total_marks != null &&
            ` · ${t("homework.detail.marks", { marks: homework.total_marks })}`}
        </p>
        <section className="space-y-1">
          <h2 className="text-sm font-semibold text-fg">{t("homework.detail.instructions")}</h2>
          {/* Plain text: instructions are rendered as written, never as HTML. */}
          <p className="text-sm whitespace-pre-wrap text-fg">{homework.instructions || "—"}</p>
        </section>
        <section className="space-y-1.5">
          <h2 className="text-sm font-semibold text-fg">{t("homework.detail.attachments")}</h2>
          <AttachmentList files={homework.attachments} empty={t("homework.detail.noAttachments")} />
        </section>
      </CardBody>
    </Card>
  );
}

function TeacherView({ homework }: { homework: Homework }) {
  const { t } = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [checking, setChecking] = useState<string | null>(null);
  const [archiving, setArchiving] = useState(false);
  const tracker = useQuery({
    queryKey: homeworkKeys.tracker(homework.id),
    queryFn: ({ signal }) => fetchTracker(homework.id, signal),
    enabled: homework.status !== "draft",
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: homeworkKeys.all });
  const publish = useMutation({
    mutationFn: () => publishHomework(homework.id),
    onSuccess: refresh,
  });
  const archive = useMutation({
    mutationFn: () => archiveHomework(homework.id),
    onSuccess: () => {
      setArchiving(false);
      void refresh();
    },
  });
  const duplicate = useMutation({
    mutationFn: () => duplicateHomework(homework.id),
    onSuccess: (copy) => navigate(`/homework/${copy.id}/edit`),
  });
  const remind = useMutation({ mutationFn: () => remindPending(homework.id), onSuccess: refresh });
  const share = useMutation({
    mutationFn: () => fetchShareText(homework.id),
    onSuccess: (data) => window.open(whatsappUrl(data.text), "_blank", "noopener,noreferrer"),
  });
  const failure = [publish, archive, duplicate, remind, share].find(
    (m) => m.error instanceof ApiError,
  )?.error as ApiError | undefined;

  const columns: Column<TrackerRow>[] = [
    {
      key: "name",
      header: t("homework.tracker.student"),
      primary: true,
      cell: (r) => (
        <span className="text-fg">
          {r.full_name}
          {r.roll_no && <span className="ml-1 text-xs text-fg-3">#{r.roll_no}</span>}
        </span>
      ),
    },
    {
      key: "status",
      header: t("homework.col.status"),
      cell: (r) => <StudentStatusBadge status={r.student_status} late={r.is_late} />,
    },
    {
      key: "submitted",
      header: t("homework.tracker.submitted"),
      secondary: true,
      cell: (r) => <span className="num text-sm text-fg-2">{formatDateTime(r.submitted_at)}</span>,
    },
    { key: "marks", header: t("homework.tracker.marks"), cell: (r) => r.marks ?? "—" },
    {
      key: "check",
      header: "",
      cell: (r) =>
        r.submission_id ? (
          <Button size="sm" variant="secondary" onClick={() => setChecking(r.submission_id)}>
            {t("homework.tracker.check")}
          </Button>
        ) : null,
    },
  ];

  return (
    <HomeworkLayout
      title={homework.title}
      actions={
        <>
          <HomeworkStatusBadge homework={homework} />
          {homework.status !== "archived" && (
            <Link to={`/homework/${homework.id}/edit`}>
              <Button variant="secondary" size="sm">
                {t("homework.action.edit")}
              </Button>
            </Link>
          )}
          {homework.status === "draft" && (
            <Button size="sm" loading={publish.isPending} onClick={() => publish.mutate()}>
              {t("homework.action.publish")}
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            loading={duplicate.isPending}
            onClick={() => duplicate.mutate()}
          >
            {t("homework.action.duplicate")}
          </Button>
          {homework.status === "published" && (
            <Button
              variant="secondary"
              size="sm"
              loading={share.isPending}
              onClick={() => share.mutate()}
            >
              {t("homework.action.share")}
            </Button>
          )}
          {homework.status !== "archived" && (
            <Button variant="ghost" size="sm" onClick={() => setArchiving(true)}>
              {t("homework.action.archive")}
            </Button>
          )}
        </>
      }
    >
      {failure && <Alert tone="danger">{failure.message}</Alert>}
      {remind.data && (
        <Alert tone="success">{t("homework.action.reminded", { count: remind.data.sent })}</Alert>
      )}
      <Summary homework={homework} />
      {tracker.data && (
        <Card>
          <CardHeader
            title={t("homework.tracker.title")}
            description={
              <span className="flex flex-wrap gap-1.5">
                {Object.entries(tracker.data.counts).map(([status, count]) => (
                  <Badge key={status}>
                    {t(`homework.student.${status as BoardRow["student_status"]}` as const)}:{" "}
                    {count}
                  </Badge>
                ))}
                {tracker.data.late > 0 && (
                  <Badge tone="warning">
                    {t("homework.tracker.lateCount", { count: tracker.data.late })}
                  </Badge>
                )}
              </span>
            }
            actions={
              homework.status === "published" ? (
                <Button
                  size="sm"
                  variant="secondary"
                  loading={remind.isPending}
                  onClick={() => remind.mutate()}
                >
                  {t("homework.action.remind")}
                </Button>
              ) : undefined
            }
          />
          <Table columns={columns} rows={tracker.data.rows} rowKey={(r) => r.student_user_id} />
        </Card>
      )}
      {checking && (
        <CheckModal homework={homework} submissionId={checking} onClose={() => setChecking(null)} />
      )}
      <ConfirmDialog
        open={archiving}
        onClose={() => setArchiving(false)}
        onConfirm={() => archive.mutate()}
        title={t("homework.action.archive")}
        confirmLabel={t("homework.action.archive")}
        tone="danger"
        pending={archive.isPending}
        error={archive.error?.message ?? null}
      >
        {t("homework.action.archiveConfirm")}
      </ConfirmDialog>
    </HomeworkLayout>
  );
}

function LearnerView({ row }: { row: BoardRow }) {
  const { t } = useT();
  const canSubmit = useCan("homework:submit");
  const { homework, submission, student_status } = row;
  return (
    <HomeworkLayout
      title={homework.title}
      actions={<StudentStatusBadge status={student_status} late={submission?.is_late} />}
    >
      <Summary homework={homework} />
      {submission && (submission.status === "checked" || submission.status === "redo") && (
        <Card>
          <CardHeader title={t("homework.result.title")} />
          <CardBody>
            <dl className="grid gap-2 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-fg-3">{t("homework.result.marks")}</dt>
                <dd className="num text-fg">
                  {submission.marks ?? "—"}
                  {homework.total_marks != null &&
                    submission.marks != null &&
                    ` / ${homework.total_marks}`}
                </dd>
              </div>
              <div>
                <dt className="text-fg-3">{t("homework.result.grade")}</dt>
                <dd className="text-fg">{submission.grade ?? "—"}</dd>
              </div>
              <div className="sm:col-span-3">
                <dt className="text-fg-3">{t("homework.result.remark")}</dt>
                <dd className="whitespace-pre-wrap text-fg">{submission.remark ?? "—"}</dd>
              </div>
            </dl>
          </CardBody>
        </Card>
      )}
      {submission && (
        <Card>
          <CardHeader
            title={t("homework.submit.title")}
            description={formatDateTime(submission.submitted_at)}
          />
          <CardBody className="space-y-2">
            <p className="text-sm whitespace-pre-wrap text-fg">{submission.text || "—"}</p>
            <AttachmentList files={submission.files} />
          </CardBody>
        </Card>
      )}
      {canSubmit &&
        (canStillSubmit(row) ? (
          <Card>
            <CardBody>
              <SubmitForm homeworkId={homework.id} existing={submission} />
            </CardBody>
          </Card>
        ) : (
          student_status !== "checked" && <Alert tone="info">{t("homework.submit.closed")}</Alert>
        ))}
    </HomeworkLayout>
  );
}
