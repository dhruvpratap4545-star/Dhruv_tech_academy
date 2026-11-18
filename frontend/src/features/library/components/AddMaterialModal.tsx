import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import { FileUpload } from "@/components/FileUpload";
import { Modal } from "@/components/Modal";
import type { ItemKind, LinkedNode, Medium } from "@/features/library/api";
import { createItem, libraryKeys, uploadDocument } from "@/features/library/api";
import { TopicPicker } from "@/features/library/components/TopicPicker";
import { validateMaterial } from "@/features/library/material";
import { useOwnerOptions } from "@/features/library/useOwnerOptions";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/**
 * Add a document, video, link or note to the library, filed under the section that is open
 * (more can be added). PDFs and images go straight to storage on a presigned link; the
 * item is published the moment the server has checked the file.
 */
export function AddMaterialModal({
  topics: initialTopics,
  onClose,
}: {
  topics: LinkedNode[];
  onClose: () => void;
}) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const owners = useOwnerOptions();
  const [owner, setOwner] = useState<string | null>(null);
  const [kind, setKind] = useState<ItemKind>("pdf");
  const [title, setTitle] = useState("");
  const [topics, setTopics] = useState<LinkedNode[]>(initialTopics);
  const [medium, setMedium] = useState<Medium>("en");
  const [url, setUrl] = useState("");
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [author, setAuthor] = useState("");
  const [source, setSource] = useState("");
  const [problem, setProblem] = useState<ReturnType<typeof validateMaterial>>(null);
  const instituteId = (owner ?? owners[0]?.value ?? "") || null;

  const save = useMutation({
    mutationFn: () => {
      const node_ids = topics.map((n) => n.id);
      if (kind === "pdf" || kind === "image") {
        return uploadDocument({
          file: files[0]!,
          title: title.trim(),
          node_ids,
          medium,
          institute_id: instituteId,
          author: author.trim() || undefined,
          source: source.trim() || undefined,
        });
      }
      return createItem({
        institute_id: instituteId,
        title: title.trim(),
        kind,
        url: kind === "text" ? null : url.trim(),
        body: kind === "text" ? body : null,
        node_ids,
        medium,
        author: author.trim() || null,
        source: source.trim() || null,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      onClose();
    },
  });

  function submit() {
    const found = validateMaterial({
      kind,
      title,
      nodeIds: topics.map((n) => n.id),
      url,
      body,
      files,
    });
    setProblem(found);
    if (!found) save.mutate();
  }

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={t("library.review.add")}
      description={t("library.form.visibleAtOnce")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button loading={save.isPending} onClick={submit}>
            {t("library.form.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {owners.length > 1 && (
            <SelectField
              label={t("library.manage.owner")}
              value={owner ?? owners[0]?.value ?? ""}
              onChange={(e) => setOwner(e.target.value)}
              options={owners}
            />
          )}
          <SelectField
            label={t("library.form.kind")}
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as ItemKind);
              setFiles([]);
            }}
            options={(["pdf", "image", "video_link", "link", "text"] as const).map((k) => ({
              value: k,
              label: t(`library.kind.${k}`),
            }))}
          />
          <SelectField
            label={t("library.medium")}
            value={medium}
            onChange={(e) => setMedium(e.target.value as Medium)}
            options={(["en", "hi", "both"] as const).map((m) => ({
              value: m,
              label: t(`library.medium.${m}`),
            }))}
          />
        </div>
        <TextField
          label={t("library.form.title")}
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
        />
        <TopicPicker
          label={t("library.form.topics")}
          hint={t("library.form.topicsHint")}
          value={topics}
          onChange={setTopics}
        />
        {(kind === "pdf" || kind === "image") && (
          <FileUpload
            label={t("library.form.file")}
            files={files}
            onChange={setFiles}
            max={1}
            camera={false}
          />
        )}
        {(kind === "link" || kind === "video_link") && (
          <TextField
            label={t("library.form.url")}
            type="url"
            inputMode="url"
            value={url}
            hint={kind === "video_link" ? t("library.form.urlHint") : undefined}
            onChange={(e) => setUrl(e.target.value)}
          />
        )}
        {kind === "text" && (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-fg">{t("library.form.body")}</span>
            <textarea
              rows={6}
              maxLength={20000}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface p-3 text-sm text-fg"
            />
          </label>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label={t("library.form.author")}
            value={author}
            maxLength={120}
            onChange={(e) => setAuthor(e.target.value)}
          />
          <TextField
            label={t("library.form.source")}
            value={source}
            maxLength={200}
            onChange={(e) => setSource(e.target.value)}
          />
        </div>
        {problem && <Alert tone="warning">{t(problem)}</Alert>}
        {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
      </div>
    </Modal>
  );
}
