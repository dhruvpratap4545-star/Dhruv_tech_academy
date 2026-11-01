import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Card, CardBody } from "@/components/Card";
import { Checkbox, SelectField, TextField } from "@/components/Field";
import { FileUpload } from "@/components/FileUpload";
import { Icon } from "@/components/Icon";
import { Spinner } from "@/components/Spinner";
import type { Homework, HomeworkPayload, Medium, TopicHit } from "@/features/homework/api";
import {
  createHomework,
  fetchHomework,
  homeworkKeys,
  publishHomework,
  searchTopics,
  updateHomework,
  uploadAttachments,
} from "@/features/homework/api";
import { HomeworkLayout } from "@/features/homework/components/HomeworkLayout";
import { useClassOptions } from "@/features/homework/components/useClassOptions";
import { MAX_SUBMISSION_FILES, toIstInput } from "@/features/homework/logic";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

type PublishMode = HomeworkPayload["publish"];

/** Create (`/homework/new`) or edit (`/homework/:id/edit`) one homework. */
export function HomeworkFormPage() {
  const { id } = useParams();
  const existing = useQuery({
    queryKey: homeworkKeys.detail(id ?? "new"),
    queryFn: ({ signal }) => fetchHomework(id!, signal),
    enabled: Boolean(id),
  });
  if (id && existing.isLoading) return <Spinner />;
  if (id && existing.error) return <Alert tone="danger">{existing.error.message}</Alert>;
  return <HomeworkForm key={id ?? "new"} homework={existing.data?.homework ?? null} />;
}

function HomeworkForm({ homework }: { homework: Homework | null }) {
  const { t } = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { options } = useClassOptions();
  const [form, setForm] = useState({
    class_id: homework?.class_id ?? "",
    subject: homework?.subject ?? "",
    title: homework?.title ?? "",
    instructions: homework?.instructions ?? "",
    medium: (homework?.medium ?? "") as Medium | "",
    total_marks: homework?.total_marks?.toString() ?? "",
    due_at: toIstInput(homework?.due_at),
    publish: (homework ? "draft" : "now") as PublishMode,
    publish_at: toIstInput(homework?.publish_at),
    allow_late: homework?.allow_late ?? true,
    allow_resubmit: homework?.allow_resubmit ?? true,
  });
  const [topic, setTopic] = useState<{ id: string; label: string } | null>(
    homework?.node_id ? { id: homework.node_id, label: homework.node_id } : null,
  );
  const [keptAttachments, setKept] = useState(homework?.attachments ?? []);
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const isDraft = !homework || homework.status === "draft";

  const save = useMutation({
    mutationFn: async () => {
      const payload: HomeworkPayload = {
        class_id: form.class_id,
        subject: form.subject,
        title: form.title,
        instructions: form.instructions,
        node_id: topic?.id ?? null,
        medium: form.medium || null,
        total_marks: form.total_marks.trim() === "" ? null : Number(form.total_marks),
        publish: form.publish,
        publish_at: form.publish === "schedule" ? form.publish_at : null,
        due_at: form.due_at,
        allow_late: form.allow_late,
        allow_resubmit: form.allow_resubmit,
      };
      let saved: Homework;
      if (homework) {
        saved = await updateHomework(homework.id, {
          ...payload,
          publish_at: undefined,
          attachment_ids: keptAttachments.map((a) => a.id),
        });
      } else {
        // Saved as a draft first so attachments land before students are emailed.
        saved = await createHomework({ ...payload, publish: "draft", publish_at: null });
      }
      if (files.length > 0) saved = await uploadAttachments(saved.id, files);
      if (isDraft && form.publish !== "draft") {
        saved = await publishHomework(
          saved.id,
          form.publish === "schedule" ? form.publish_at : null,
        );
      }
      return saved;
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: homeworkKeys.all });
      navigate(`/homework/${saved.id}`);
    },
  });

  function submit() {
    if (!form.class_id || !form.subject.trim() || form.title.trim().length < 2 || !form.due_at) {
      setProblem(t("homework.form.required"));
      return;
    }
    setProblem(null);
    save.mutate();
  }

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <HomeworkLayout title={homework ? t("homework.form.editTitle") : t("homework.form.newTitle")}>
      <Card>
        <CardBody>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField
                label={t("homework.form.class")}
                required
                disabled={Boolean(homework)}
                value={form.class_id}
                placeholder={t("homework.form.chooseClass")}
                options={options}
                onChange={(e) => set("class_id", e.target.value)}
              />
              <TextField
                label={t("homework.form.subject")}
                required
                maxLength={80}
                value={form.subject}
                onChange={(e) => set("subject", e.target.value)}
              />
            </div>
            <TextField
              label={t("homework.form.title")}
              required
              maxLength={200}
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
            />
            <label className="block space-y-1.5">
              <span className="text-sm font-medium text-fg">{t("homework.form.instructions")}</span>
              <textarea
                rows={5}
                maxLength={10000}
                value={form.instructions}
                onChange={(e) => set("instructions", e.target.value)}
                className="w-full rounded-lg border border-line bg-surface p-3 text-sm text-fg"
              />
            </label>
            <TopicPicker value={topic} onChange={setTopic} />
            <div className="grid gap-3 sm:grid-cols-3">
              <SelectField
                label={t("homework.form.medium")}
                value={form.medium}
                onChange={(e) => set("medium", e.target.value as Medium | "")}
                options={[
                  { value: "", label: t("homework.form.mediumAny") },
                  { value: "en", label: t("homework.form.mediumEn") },
                  { value: "hi", label: t("homework.form.mediumHi") },
                  { value: "bilingual", label: t("homework.form.mediumBoth") },
                ]}
              />
              <TextField
                label={t("homework.form.marks")}
                type="number"
                min={0}
                max={1000}
                value={form.total_marks}
                onChange={(e) => set("total_marks", e.target.value)}
              />
              <TextField
                label={t("homework.form.due")}
                type="datetime-local"
                required
                value={form.due_at}
                onChange={(e) => set("due_at", e.target.value)}
              />
            </div>
            {isDraft && (
              <div className="grid gap-3 sm:grid-cols-2">
                <SelectField
                  label={t("homework.form.publish")}
                  value={form.publish}
                  onChange={(e) => set("publish", e.target.value as PublishMode)}
                  options={[
                    { value: "now", label: t("homework.form.publishNow") },
                    { value: "schedule", label: t("homework.form.publishLater") },
                    { value: "draft", label: t("homework.form.publishDraft") },
                  ]}
                />
                {form.publish === "schedule" && (
                  <TextField
                    label={t("homework.form.publishAt")}
                    type="datetime-local"
                    required
                    value={form.publish_at}
                    onChange={(e) => set("publish_at", e.target.value)}
                  />
                )}
              </div>
            )}
            <div className="space-y-2">
              <Checkbox
                label={t("homework.form.allowLate")}
                checked={form.allow_late}
                onChange={(e) => set("allow_late", e.target.checked)}
              />
              <Checkbox
                label={t("homework.form.allowResubmit")}
                checked={form.allow_resubmit}
                onChange={(e) => set("allow_resubmit", e.target.checked)}
              />
            </div>
            {keptAttachments.length > 0 && (
              <ul className="flex flex-wrap gap-2">
                {keptAttachments.map((file) => (
                  <li
                    key={file.id}
                    className="flex items-center gap-1.5 rounded-full bg-surface-3 py-1 pr-1 pl-3 text-xs text-fg"
                  >
                    <span className="truncate">{file.original_name}</span>
                    <button
                      type="button"
                      aria-label={t("upload.remove", { name: file.original_name })}
                      onClick={() => setKept(keptAttachments.filter((f) => f.id !== file.id))}
                      className="rounded-full p-1 text-fg-2 hover:bg-surface-2"
                    >
                      <Icon name="close" className="size-3" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <FileUpload
              label={t("homework.form.attachments")}
              files={files}
              onChange={setFiles}
              max={MAX_SUBMISSION_FILES - keptAttachments.length}
              camera={false}
              disabled={save.isPending}
            />
            {problem && <Alert tone="warning">{problem}</Alert>}
            {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
            <Button type="submit" loading={save.isPending}>
              {t("homework.form.save")}
            </Button>
          </form>
        </CardBody>
      </Card>
    </HomeworkLayout>
  );
}

/** Optional link to a chapter or topic, found by typing at least two letters. */
function TopicPicker({
  value,
  onChange,
}: {
  value: { id: string; label: string } | null;
  onChange: (topic: { id: string; label: string } | null) => void;
}) {
  const { t } = useT();
  const [term, setTerm] = useState("");
  const hits = useQuery({
    queryKey: ["homework", "topics", term],
    queryFn: ({ signal }) => searchTopics(term, signal),
    enabled: term.trim().length >= 2,
  });
  if (value) {
    return (
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-fg">{t("homework.form.topic")}</p>
        <div className="flex items-center gap-2">
          <span className="truncate text-sm text-fg">{value.label}</span>
          <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
            {t("homework.form.topicClear")}
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <TextField
        label={t("homework.form.topic")}
        placeholder={t("homework.form.topicSearch")}
        value={term}
        onChange={(e) => setTerm(e.target.value)}
      />
      {(hits.data ?? []).length > 0 && (
        <ul className="max-h-48 divide-y divide-line overflow-y-auto rounded-lg border border-line">
          {(hits.data ?? []).slice(0, 10).map((hit: TopicHit) => (
            <li key={hit.id}>
              <button
                type="button"
                onClick={() => onChange({ id: hit.id, label: hit.path || hit.name })}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-2"
              >
                <span className="text-fg">{hit.name}</span>
                <span className="block text-xs text-fg-3">{hit.path}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
