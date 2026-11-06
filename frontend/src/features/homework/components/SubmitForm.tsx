import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { FileUpload } from "@/components/FileUpload";
import type { Submission } from "@/features/homework/api";
import { homeworkKeys, submitHomework } from "@/features/homework/api";
import { MAX_SUBMISSION_FILES } from "@/features/homework/logic";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/**
 * A typed answer and/or up to five photos or PDFs. The camera button opens the phone
 * camera directly, which is how most students will hand in a notebook page. The server
 * decides whether a late or repeated submission is allowed; its message is shown as is.
 */
export function SubmitForm({
  homeworkId,
  existing,
  onSubmitted,
}: {
  homeworkId: string;
  existing: Submission | null;
  onSubmitted?: () => void;
}) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const [text, setText] = useState(existing?.text ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: () => submitHomework(homeworkId, text, files),
    onSuccess: () => {
      setFiles([]);
      void queryClient.invalidateQueries({ queryKey: homeworkKeys.all });
      onSubmitted?.();
    },
  });

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!text.trim() && files.length === 0) {
          setProblem(t("homework.submit.needSomething"));
          return;
        }
        setProblem(null);
        send.mutate();
      }}
    >
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-fg">{t("homework.submit.answer")}</span>
        <textarea
          rows={5}
          maxLength={10000}
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="w-full rounded-lg border border-line bg-surface p-3 text-sm text-fg"
        />
      </label>
      <FileUpload
        label={t("homework.submit.files")}
        files={files}
        onChange={setFiles}
        max={MAX_SUBMISSION_FILES}
        camera
        disabled={send.isPending}
      />
      {existing && existing.files.length > 0 && (
        <p className="text-xs text-fg-2">{t("homework.submit.keepFiles")}</p>
      )}
      {problem && <Alert tone="warning">{problem}</Alert>}
      {send.error instanceof ApiError && <Alert tone="danger">{send.error.message}</Alert>}
      {send.isSuccess && <Alert tone="success">{t("homework.submit.done")}</Alert>}
      <Button type="submit" loading={send.isPending} block>
        {existing ? t("homework.submit.resend") : t("homework.submit.send")}
      </Button>
    </form>
  );
}
