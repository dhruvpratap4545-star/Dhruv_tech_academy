import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import type { Homework, Submission } from "@/features/homework/api";
import { checkSubmission, fetchSubmission, homeworkKeys } from "@/features/homework/api";
import { AttachmentList } from "@/features/homework/components/AttachmentList";
import { StudentStatusBadge } from "@/features/homework/components/StatusBadges";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

/** The teacher's "check" drawer: the work, then marks, grade and remark — or redo. */
export function CheckModal({
  homework,
  submissionId,
  onClose,
}: {
  homework: Homework;
  submissionId: string;
  onClose: () => void;
}) {
  const { t } = useT();
  const submission = useQuery({
    queryKey: homeworkKeys.submission(homework.id, submissionId),
    queryFn: ({ signal }) => fetchSubmission(homework.id, submissionId, signal),
  });
  return (
    <Modal
      open
      onClose={onClose}
      title={t("homework.check.title")}
      description={homework.title}
      size="lg"
    >
      {submission.isLoading && <Spinner />}
      {submission.error && <Alert tone="danger">{submission.error.message}</Alert>}
      {submission.data && (
        <CheckForm homework={homework} submission={submission.data} onDone={onClose} />
      )}
    </Modal>
  );
}

function CheckForm({
  homework,
  submission,
  onDone,
}: {
  homework: Homework;
  submission: Submission;
  onDone: () => void;
}) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const [marks, setMarks] = useState(submission.marks?.toString() ?? "");
  const [grade, setGrade] = useState(submission.grade ?? "");
  const [remark, setRemark] = useState(submission.remark ?? "");
  const save = useMutation({
    mutationFn: (redo: boolean) =>
      checkSubmission(homework.id, submission.id, {
        marks: marks.trim() === "" ? null : Number(marks),
        grade: grade.trim() || null,
        remark: remark.trim() || null,
        redo,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: homeworkKeys.all });
      onDone();
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-fg-2">
        <span className="font-medium text-fg">{submission.student_name}</span>
        <StudentStatusBadge status={submission.status} late={submission.is_late} />
        <span>{formatDateTime(submission.submitted_at)}</span>
        <span>· {t("homework.check.attempts", { count: submission.attempts })}</span>
      </div>
      <section className="space-y-1">
        <h3 className="text-sm font-semibold text-fg">{t("homework.check.answer")}</h3>
        {/* Plain text: what a student typed is never rendered as HTML. */}
        <p className="text-sm whitespace-pre-wrap text-fg">
          {submission.text || <span className="text-fg-3">{t("homework.check.noText")}</span>}
        </p>
      </section>
      <section className="space-y-1">
        <h3 className="text-sm font-semibold text-fg">{t("homework.check.files")}</h3>
        <AttachmentList files={submission.files} empty="—" />
      </section>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          label={t("homework.check.marks")}
          type="number"
          min={0}
          max={homework.total_marks ?? undefined}
          hint={
            homework.total_marks != null
              ? t("homework.detail.marks", { marks: homework.total_marks })
              : undefined
          }
          value={marks}
          onChange={(e) => setMarks(e.target.value)}
        />
        <TextField
          label={t("homework.check.grade")}
          maxLength={10}
          value={grade}
          onChange={(e) => setGrade(e.target.value)}
        />
      </div>
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-fg">{t("homework.check.remark")}</span>
        <textarea
          rows={3}
          maxLength={2000}
          value={remark}
          onChange={(e) => setRemark(e.target.value)}
          className="w-full rounded-lg border border-line bg-surface p-3 text-sm text-fg"
        />
      </label>
      {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          variant="secondary"
          loading={save.isPending && save.variables}
          onClick={() => save.mutate(true)}
        >
          {t("homework.check.redo")}
        </Button>
        <Button loading={save.isPending && !save.variables} onClick={() => save.mutate(false)}>
          {t("homework.check.save")}
        </Button>
      </div>
    </div>
  );
}
