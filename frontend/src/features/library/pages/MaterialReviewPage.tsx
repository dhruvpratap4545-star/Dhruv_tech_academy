import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import { FileUpload } from "@/components/FileUpload";
import { Icon } from "@/components/Icon";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import { EmptyState } from "@/components/Table";
import type { ContentItem, ItemKind, LinkedNode, Medium } from "@/features/library/api";
import {
  createItem,
  fetchItems,
  fetchVersions,
  libraryKeys,
  uploadItem,
} from "@/features/library/api";
import { ItemActions } from "@/features/library/components/ItemActions";
import { LibraryLayout } from "@/features/library/components/LibraryLayout";
import { MaterialCard } from "@/features/library/components/MaterialCard";
import { TopicPicker } from "@/features/library/components/TopicPicker";
import { validateMaterial } from "@/features/library/material";
import { useOwnerOptions } from "@/features/library/useOwnerOptions";
import { useCan } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

/**
 * Material & review. Contributors (faculty and up) add material as drafts and send it for
 * review; holders of `library:publish` see the queue and publish or send it back.
 */
export function MaterialReviewPage() {
  const { t } = useT();
  const canPublish = useCan("library:publish");
  const [adding, setAdding] = useState(false);
  const [history, setHistory] = useState<ContentItem | null>(null);

  return (
    <LibraryLayout
      title={t("library.review.title")}
      description={t("library.review.description")}
      actions={
        <Button icon={<Icon name="plus" />} onClick={() => setAdding(true)}>
          {t("library.review.add")}
        </Button>
      }
    >
      {canPublish && (
        <ItemSection
          title={t("library.review.queue")}
          empty={t("library.review.emptyQueue")}
          filters={{ status: "in_review" }}
          onHistory={setHistory}
        />
      )}
      <ItemSection
        title={t("library.review.mine")}
        empty={t("library.review.emptyMine")}
        filters={{ mine: true }}
        onHistory={setHistory}
      />
      {adding && <MaterialForm onClose={() => setAdding(false)} />}
      {history && <HistoryModal item={history} onClose={() => setHistory(null)} />}
    </LibraryLayout>
  );
}

function ItemSection({
  title,
  empty,
  filters,
  onHistory,
}: {
  title: string;
  empty: string;
  filters: { status?: "in_review"; mine?: boolean };
  onHistory: (item: ContentItem) => void;
}) {
  const items = useQuery({
    queryKey: libraryKeys.items({ ...filters, limit: 50 }),
    queryFn: ({ signal }) => fetchItems({ ...filters, limit: 50 }, signal),
  });
  return (
    <section className="space-y-3">
      <h2 className="font-display text-lg font-bold text-fg">{title}</h2>
      {items.isLoading && <Spinner />}
      {items.error && <Alert tone="danger">{items.error.message}</Alert>}
      {items.data && items.data.items.length === 0 && <EmptyState title={empty} />}
      <div className="grid gap-3 lg:grid-cols-2">
        {(items.data?.items ?? []).map((item) => (
          <MaterialCard
            key={item.id}
            item={item}
            showStatus
            actions={<ItemActions item={item} onHistory={() => onHistory(item)} />}
          />
        ))}
      </div>
    </section>
  );
}

function MaterialForm({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const owners = useOwnerOptions();
  const [owner, setOwner] = useState<string | null>(null);
  const [kind, setKind] = useState<ItemKind>("pdf");
  const [title, setTitle] = useState("");
  const [topics, setTopics] = useState<LinkedNode[]>([]);
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
        return uploadItem({
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

function HistoryModal({ item, onClose }: { item: ContentItem; onClose: () => void }) {
  const { t } = useT();
  const versions = useQuery({
    queryKey: libraryKeys.versions(item.id),
    queryFn: ({ signal }) => fetchVersions(item.id, signal),
  });
  return (
    <Modal open onClose={onClose} title={`${t("library.review.history")}: ${item.title}`}>
      {versions.isLoading && <Spinner />}
      {versions.data && versions.data.length === 0 && (
        <p className="text-sm text-fg-2">{t("library.review.noHistory")}</p>
      )}
      <ul className="space-y-2">
        {(versions.data ?? []).map((v) => (
          <li key={v.id}>
            <Card>
              <CardHeader
                title={t("library.review.version", { version: v.version })}
                description={formatDateTime(v.created_at)}
              />
              <CardBody>
                <dl className="space-y-1 text-xs">
                  {Object.entries(v.fields)
                    .filter(([, value]) => value !== null && typeof value !== "object")
                    .map(([key, value]) => (
                      <div key={key} className="flex gap-2">
                        <dt className="w-24 shrink-0 text-fg-3">{key}</dt>
                        <dd className="min-w-0 break-words text-fg">{String(value)}</dd>
                      </div>
                    ))}
                </dl>
              </CardBody>
            </Card>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
