import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import type { AiReadOptions, ImportResult, ImportRowCells, Track } from "@/features/library/api";
import {
  downloadRowsAsExcel,
  importRows,
  libraryKeys,
  readSyllabusWithAi,
} from "@/features/library/api";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

const TRACKS: { value: Track; label: string }[] = [
  { value: "cbse", label: "CBSE" },
  { value: "neet", label: "NEET" },
  { value: "jee", label: "JEE" },
  { value: "upsc", label: "UPSC" },
  { value: "custom", label: "Custom" },
];
const COLUMNS = ["level", "subject", "unit", "chapter", "topic"] as const;
/** Rendering hundreds of rows of inputs at once is slow on a phone; show a page first. */
const FIRST_PAGE = 100;

/**
 * PDF or photo → AI reading → editable rows → dry run → import.
 *
 * The AI only proposes rows. They are checked by the same server rules as a spreadsheet,
 * and nothing is saved until the reviewer presses Import — so a misreading costs an edit.
 */
export function AiImport({ instituteId }: { instituteId: string | null }) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<AiReadOptions>({
    track: "custom",
    level: "",
    medium: "Both",
    difficulty: "",
    examTags: "",
  });
  const [rows, setRows] = useState<ImportRowCells[] | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);

  const read = useMutation({
    mutationFn: () => readSyllabusWithAi(file!, { ...options, instituteId }),
    onSuccess: (result) => {
      setRows(result.rows);
      setPreview(null);
      setDone(null);
      setShowAll(false);
    },
  });
  const run = useMutation({
    mutationFn: (dryRun: boolean) => importRows(rows!, dryRun, instituteId),
    onSuccess: (result) => {
      // The server numbers rows from 1 in the order sent: put its findings on the rows.
      const byRow = new Map(result.problems.map((p) => [p.row, p.messages]));
      setRows((current) =>
        current ? current.map((row, i) => ({ ...row, problems: byRow.get(i + 1) ?? [] })) : null,
      );
      if (result.dry_run) {
        setPreview(result);
      } else {
        setDone(result);
        setPreview(null);
        void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      }
    },
  });
  const download = useMutation({ mutationFn: () => downloadRowsAsExcel(rows!) });

  const edit = (index: number, column: (typeof COLUMNS)[number], value: string) => {
    setRows((current) =>
      current
        ? current.map((row, i) => (i === index ? { ...row, [column]: value, problems: [] } : row))
        : null,
    );
    setPreview(null);
  };
  const remove = (index: number) => {
    setRows((current) => (current ? current.filter((_, i) => i !== index) : null));
    setPreview(null);
  };
  const startOver = () => {
    setRows(null);
    setPreview(null);
    setDone(null);
    read.reset();
    run.reset();
  };

  const set = <K extends keyof AiReadOptions>(key: K, value: AiReadOptions[K]) =>
    setOptions((current) => ({ ...current, [key]: value }));
  const error = [read.error, run.error, download.error].find((e) => e instanceof ApiError);
  const result = read.data;
  const withProblems = rows?.filter((row) => row.problems?.length).length ?? 0;
  const shown = rows && !showAll ? rows.slice(0, FIRST_PAGE) : rows;

  if (!rows || !result) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-fg-2">{t("library.ai.description")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField
            label={t("library.ai.track")}
            value={options.track}
            onChange={(e) => set("track", e.target.value as Track)}
            options={TRACKS}
          />
          <TextField
            label={t("library.ai.level")}
            hint={t("library.ai.levelHint")}
            value={options.level}
            maxLength={120}
            onChange={(e) => set("level", e.target.value)}
          />
          <SelectField
            label={t("library.ai.medium")}
            value={options.medium}
            onChange={(e) => set("medium", e.target.value as AiReadOptions["medium"])}
            options={[
              { value: "Both", label: t("library.medium.both") },
              { value: "English", label: t("library.medium.en") },
              { value: "Hindi", label: t("library.medium.hi") },
            ]}
          />
          <SelectField
            label={t("library.ai.difficulty")}
            value={options.difficulty}
            onChange={(e) => set("difficulty", e.target.value as AiReadOptions["difficulty"])}
            options={[
              { value: "", label: t("library.ai.difficultyNone") },
              { value: "Easy", label: "Easy" },
              { value: "Medium", label: "Medium" },
              { value: "Hard", label: "Hard" },
            ]}
          />
          <TextField
            label={t("library.ai.examTags")}
            hint={t("library.ai.examTagsHint")}
            value={options.examTags}
            maxLength={200}
            onChange={(e) => set("examTags", e.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm text-fg">
            <span className="sr-only">{t("library.ai.file")}</span>
            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              aria-label={t("library.ai.file")}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="text-sm"
            />
          </label>
          <Button size="sm" disabled={!file} loading={read.isPending} onClick={() => read.mutate()}>
            {t("library.ai.read")}
          </Button>
        </div>
        {read.isPending && <Alert tone="info">{t("library.ai.reading")}</Alert>}
        {error && <Alert tone="danger">{error.message}</Alert>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Alert tone="info">
        {result.status === "cached"
          ? t("library.ai.cached", { rows: result.rows.length, file: result.file_name })
          : t("library.ai.result", {
              rows: result.rows.length,
              file: result.file_name,
              model: result.model_id,
              cost: (result.cost_paise / 100).toFixed(2),
            })}
      </Alert>
      {result.missing_papers.length > 0 && (
        <Alert tone="warning">
          {t("library.ai.missing", { papers: result.missing_papers.join(", ") })}
        </Alert>
      )}
      {withProblems > 0 && (
        <Alert tone="warning">{t("library.ai.problems", { count: withProblems })}</Alert>
      )}
      <p className="text-sm text-fg-2">{t("library.ai.reviewHint")}</p>

      <div className="max-h-[28rem] overflow-auto rounded-md border border-line">
        <table className="w-full min-w-[48rem] text-xs">
          <thead className="sticky top-0 bg-surface-2 text-left text-fg-2">
            <tr>
              <th className="w-10 px-2 py-1.5">#</th>
              {COLUMNS.map((column) => (
                <th key={column} className="px-2 py-1.5 font-medium">
                  {t(`library.kindName.${column}`)}
                </th>
              ))}
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {shown!.map((row, index) => (
              <tr
                key={index}
                className={cn(
                  "border-t border-line",
                  row.problems?.length ? "bg-warn-soft" : undefined,
                )}
                title={row.problems?.join(" ")}
              >
                <td className="num px-2 py-1 text-fg-3">{index + 1}</td>
                {COLUMNS.map((column) => (
                  <td key={column} className="px-1 py-0.5">
                    <input
                      value={row[column]}
                      aria-label={`${t(`library.kindName.${column}`)} ${index + 1}`}
                      onChange={(e) => edit(index, column, e.target.value)}
                      className="h-7 w-full rounded border border-transparent bg-transparent px-1 hover:border-line focus:border-accent focus:outline-none"
                    />
                  </td>
                ))}
                <td className="px-1">
                  <button
                    type="button"
                    aria-label={t("library.ai.remove", { row: index + 1 })}
                    onClick={() => remove(index)}
                    className="rounded px-1.5 text-fg-3 hover:bg-surface-2 hover:text-bad"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!showAll && rows.length > FIRST_PAGE && (
        <p className="text-xs text-fg-2">
          {t("library.ai.showing", { shown: FIRST_PAGE, total: rows.length })}{" "}
          <button type="button" className="text-accent underline" onClick={() => setShowAll(true)}>
            {t("library.ai.showAll")}
          </button>
        </p>
      )}

      {error && <Alert tone="danger">{error.message}</Alert>}
      {preview && (
        <Alert tone={preview.problems.length ? "warning" : "info"}>
          {t("library.import.summary", {
            valid: preview.rows_valid,
            total: preview.rows_total,
            created: preview.created,
            updated: preview.updated,
            unchanged: preview.unchanged,
          })}
        </Alert>
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

      <div className="flex flex-wrap gap-2">
        {preview ? (
          <Button
            disabled={preview.rows_valid === 0}
            loading={run.isPending}
            onClick={() => run.mutate(false)}
          >
            {t("library.import.commit", { count: preview.rows_valid })}
          </Button>
        ) : (
          !done && (
            <Button
              disabled={rows.length === 0}
              loading={run.isPending}
              onClick={() => run.mutate(true)}
            >
              {t("library.ai.check")}
            </Button>
          )
        )}
        <Button
          variant="secondary"
          disabled={rows.length === 0}
          loading={download.isPending}
          onClick={() => download.mutate()}
        >
          {t("library.ai.download")}
        </Button>
        <Button variant="ghost" onClick={startOver}>
          {t("library.ai.startOver")}
        </Button>
      </div>
    </div>
  );
}
