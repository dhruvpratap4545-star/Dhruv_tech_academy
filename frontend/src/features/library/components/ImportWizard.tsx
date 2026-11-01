import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import type { ImportResult } from "@/features/library/api";
import { downloadImportTemplate, importSyllabus, libraryKeys } from "@/features/library/api";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/**
 * Template → upload → preview with row errors → import. The preview is a dry run on the
 * server, so what it reports is exactly what the import will do.
 */
export function ImportWizard({ instituteId }: { instituteId: string | null }) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const template = useMutation({ mutationFn: downloadImportTemplate });
  const run = useMutation({
    mutationFn: (dryRun: boolean) => importSyllabus(file!, dryRun, instituteId),
    onSuccess: (result) => {
      if (result.dry_run) {
        setPreview(result);
        setDone(null);
      } else {
        setDone(result);
        setPreview(null);
        void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      }
    },
  });

  return (
    <div className="space-y-3">
      <p className="text-sm text-fg-2">{t("library.import.description")}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          loading={template.isPending}
          onClick={() => template.mutate()}
        >
          {t("library.import.template")}
        </Button>
        <label className="text-sm text-fg">
          <span className="sr-only">{t("library.import.file")}</span>
          <input
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label={t("library.import.file")}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setPreview(null);
              setDone(null);
            }}
            className="text-sm"
          />
        </label>
        <Button
          size="sm"
          disabled={!file}
          loading={run.isPending && !preview}
          onClick={() => run.mutate(true)}
        >
          {t("library.import.preview")}
        </Button>
      </div>
      {run.error instanceof ApiError && <Alert tone="danger">{run.error.message}</Alert>}
      {preview && (
        <div className="space-y-2">
          <Alert tone={preview.problems.length ? "warning" : "info"}>
            {t("library.import.summary", {
              valid: preview.rows_valid,
              total: preview.rows_total,
              created: preview.created,
              updated: preview.updated,
              unchanged: preview.unchanged,
            })}
          </Alert>
          {preview.problems.length > 0 && (
            <ul className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-line p-2 text-xs">
              {preview.problems.map((problem) => (
                <li key={problem.row}>
                  <span className="font-semibold">
                    {t("library.import.row", { row: problem.row })}:
                  </span>{" "}
                  {problem.messages.join(" ")}
                </li>
              ))}
            </ul>
          )}
          <Button
            disabled={preview.rows_valid === 0}
            loading={run.isPending}
            onClick={() => run.mutate(false)}
          >
            {t("library.import.commit", { count: preview.rows_valid })}
          </Button>
        </div>
      )}
      {done && (
        <Alert tone="success">
          {t("library.import.done", {
            created: done.created,
            updated: done.updated,
            unchanged: done.unchanged,
          })}
        </Alert>
      )}
    </div>
  );
}
