import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Checkbox, SelectField, TextField } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import { fetchClasses, fetchInstitutes, instituteKeys } from "@/features/admin/api";
import type { NodeKind, SyllabusNode, Track } from "@/features/library/api";
import {
  archiveNode,
  createNode,
  fetchChildren,
  libraryKeys,
  reorderNode,
  updateNode,
} from "@/features/library/api";
import { ClassSyllabusPicker } from "@/features/library/components/ClassSyllabusPicker";
import { ImportWizard } from "@/features/library/components/ImportWizard";
import { LibraryLayout } from "@/features/library/components/LibraryLayout";
import { childKinds } from "@/features/library/tree";
import { useOwnerOptions } from "@/features/library/useOwnerOptions";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

type Dialog =
  | { type: "add"; parent: SyllabusNode | null }
  | { type: "rename"; node: SyllabusNode }
  | { type: "archive"; node: SyllabusNode }
  | null;

/**
 * Syllabus Manager: the tree, edited in place. Children load when a node is opened, so
 * the CBSE track's thousand nodes are never fetched at once.
 */
export function SyllabusManagerPage() {
  const { t } = useT();
  const owners = useOwnerOptions();
  const [showArchived, setShowArchived] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [importOwner, setImportOwner] = useState<string | null>(null);
  const owner = importOwner ?? owners[0]?.value ?? "";

  return (
    <LibraryLayout
      title={t("library.manage.title")}
      description={t("library.manage.description")}
      actions={
        <Button
          icon={<Icon name="plus" />}
          onClick={() => setDialog({ type: "add", parent: null })}
        >
          {t("library.manage.addTrack")}
        </Button>
      }
    >
      <Card>
        <CardHeader
          title={t("library.tracks")}
          actions={
            <Checkbox
              label={t("library.manage.showArchived")}
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
          }
        />
        <TreeLevel parentId={null} depth={0} showArchived={showArchived} onDialog={setDialog} />
      </Card>

      <Card>
        <CardHeader title={t("library.import.title")} />
        <CardBody className="space-y-3">
          {owners.length > 1 && (
            <SelectField
              label={t("library.manage.owner")}
              value={owner}
              onChange={(e) => setImportOwner(e.target.value)}
              options={owners}
            />
          )}
          <ImportWizard instituteId={owner || null} />
        </CardBody>
      </Card>

      <ClassSyllabusCard />

      {dialog?.type === "add" && (
        <AddNodeModal parent={dialog.parent} owners={owners} onClose={() => setDialog(null)} />
      )}
      {dialog?.type === "rename" && (
        <RenameModal node={dialog.node} onClose={() => setDialog(null)} />
      )}
      {dialog?.type === "archive" && (
        <ArchiveDialog node={dialog.node} onClose={() => setDialog(null)} />
      )}
    </LibraryLayout>
  );
}

function TreeLevel({
  parentId,
  depth,
  showArchived,
  onDialog,
}: {
  parentId: string | null;
  depth: number;
  showArchived: boolean;
  onDialog: (d: Dialog) => void;
}) {
  const nodes = useQuery({
    queryKey: libraryKeys.children(parentId, showArchived),
    queryFn: ({ signal }) => fetchChildren(parentId, showArchived, signal),
  });
  if (nodes.isLoading) return <Spinner className="m-3" />;
  if (nodes.error) return <Alert tone="danger">{nodes.error.message}</Alert>;
  const rows = nodes.data ?? [];
  return (
    <ul className={cn(depth > 0 && "border-l border-line", "divide-y divide-line")}>
      {rows.map((node, index) => (
        <TreeRow
          key={node.id}
          node={node}
          index={index}
          siblings={rows.length}
          depth={depth}
          showArchived={showArchived}
          onDialog={onDialog}
        />
      ))}
    </ul>
  );
}

function TreeRow({
  node,
  index,
  siblings,
  depth,
  showArchived,
  onDialog,
}: {
  node: SyllabusNode;
  index: number;
  siblings: number;
  depth: number;
  showArchived: boolean;
  onDialog: (d: Dialog) => void;
}) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const move = useMutation({
    mutationFn: (position: number) => reorderNode(node.id, position),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["library", "children", node.parent_id ?? "root"],
      }),
  });
  const archived = node.status === "archived";
  const canHaveChildren = childKinds(node.kind).length > 0;

  return (
    <li style={{ paddingLeft: depth ? 12 : 0 }}>
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={node.child_count === 0}
          aria-expanded={open}
          aria-label={node.name}
          className="rounded p-1 text-fg-3 hover:bg-surface-2 disabled:opacity-30"
        >
          <Icon
            name="chevron"
            className={cn("size-4 transition-transform", !open && "-rotate-90")}
          />
        </button>
        <span
          className={cn("min-w-0 flex-1 text-sm", archived ? "text-fg-3 line-through" : "text-fg")}
        >
          {node.name}
          <span className="ml-2 text-xs text-fg-3">{t(`library.kindName.${node.kind}`)}</span>
        </span>
        {node.institute_id === null && depth === 0 && (
          <Badge tone="accent">{t("library.manage.master")}</Badge>
        )}
        {!archived && (
          <div className="flex flex-wrap gap-1">
            {canHaveChildren && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onDialog({ type: "add", parent: node })}
              >
                {t("library.manage.addChild")}
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => onDialog({ type: "rename", node })}>
              {t("library.manage.rename")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={index === 0 || move.isPending}
              onClick={() => move.mutate(index - 1)}
              aria-label={`${t("library.manage.up")}: ${node.name}`}
            >
              ↑
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={index === siblings - 1 || move.isPending}
              onClick={() => move.mutate(index + 1)}
              aria-label={`${t("library.manage.down")}: ${node.name}`}
            >
              ↓
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onDialog({ type: "archive", node })}>
              {t("library.manage.archive")}
            </Button>
          </div>
        )}
      </div>
      {move.error instanceof ApiError && (
        <Alert tone="danger" className="mx-3 mb-2">
          {move.error.message}
        </Alert>
      )}
      {open && (
        <TreeLevel
          parentId={node.id}
          depth={depth + 1}
          showArchived={showArchived}
          onDialog={onDialog}
        />
      )}
    </li>
  );
}

function AddNodeModal({
  parent,
  owners,
  onClose,
}: {
  parent: SyllabusNode | null;
  owners: { value: string; label: string }[];
  onClose: () => void;
}) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const kinds = parent ? childKinds(parent.kind) : (["track"] as NodeKind[]);
  const [kind, setKind] = useState<NodeKind>(kinds[0]!);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [track, setTrack] = useState<Track>("custom");
  const [owner, setOwner] = useState(owners[0]?.value ?? "");
  const save = useMutation({
    mutationFn: () =>
      createNode({
        parent_id: parent?.id ?? null,
        institute_id: parent ? undefined : owner || null,
        track: parent ? undefined : track,
        kind,
        name: name.trim(),
        code: code.trim() || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      onClose();
    },
  });
  return (
    <Modal
      open
      onClose={onClose}
      title={
        parent ? `${t("library.manage.addChild")}: ${parent.name}` : t("library.manage.addTrack")
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!name.trim()} loading={save.isPending} onClick={() => save.mutate()}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {!parent && owners.length > 1 && (
          <SelectField
            label={t("library.manage.owner")}
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            options={owners}
          />
        )}
        {!parent && (
          <SelectField
            label={t("library.track")}
            value={track}
            onChange={(e) => setTrack(e.target.value as Track)}
            options={(["cbse", "neet", "jee", "upsc", "custom"] as const).map((v) => ({
              value: v,
              label: v === "custom" ? "Custom" : v.toUpperCase(),
            }))}
          />
        )}
        {kinds.length > 1 && (
          <SelectField
            label={t("library.manage.kindLabel")}
            value={kind}
            onChange={(e) => setKind(e.target.value as NodeKind)}
            options={kinds.map((k) => ({ value: k, label: t(`library.kindName.${k}`) }))}
          />
        )}
        <TextField
          label={t("library.manage.name")}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <TextField
          label={t("library.manage.code")}
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
      </div>
    </Modal>
  );
}

function RenameModal({ node, onClose }: { node: SyllabusNode; onClose: () => void }) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const [name, setName] = useState(node.name);
  const save = useMutation({
    mutationFn: () => updateNode(node.id, { name: name.trim() }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      onClose();
    },
  });
  return (
    <Modal
      open
      onClose={onClose}
      title={t("library.manage.rename")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!name.trim()} loading={save.isPending} onClick={() => save.mutate()}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <TextField
        label={t("library.manage.name")}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      {save.error instanceof ApiError && (
        <Alert tone="danger" className="mt-3">
          {save.error.message}
        </Alert>
      )}
    </Modal>
  );
}

function ArchiveDialog({ node, onClose }: { node: SyllabusNode; onClose: () => void }) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const archive = useMutation({
    mutationFn: () => archiveNode(node.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      onClose();
    },
  });
  return (
    <ConfirmDialog
      open
      onClose={onClose}
      onConfirm={() => archive.mutate()}
      title={t("library.manage.archive")}
      confirmLabel={t("library.manage.archive")}
      tone="danger"
      pending={archive.isPending}
      error={archive.error instanceof ApiError ? archive.error.message : null}
    >
      {t("library.manage.archiveConfirm", { name: node.name })}
    </ConfirmDialog>
  );
}

function ClassSyllabusCard() {
  const { t } = useT();
  const institutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
  });
  const active = (institutes.data?.items ?? []).filter((i) => i.status === "active");
  const [instituteId, setInstituteId] = useState("");
  const chosenInstitute = instituteId || active[0]?.id || "";
  const classes = useQuery({
    queryKey: instituteKeys.classes(chosenInstitute),
    queryFn: ({ signal }) => fetchClasses(chosenInstitute, undefined, signal),
    enabled: Boolean(chosenInstitute),
  });
  const [classId, setClassId] = useState("");

  return (
    <Card>
      <CardHeader
        title={t("library.classSyllabus.title")}
        description={t("library.classSyllabus.description")}
      />
      <CardBody className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField
            label={t("library.classSyllabus.institute")}
            value={chosenInstitute}
            onChange={(e) => {
              setInstituteId(e.target.value);
              setClassId("");
            }}
            options={active.map((i) => ({ value: i.id, label: i.name }))}
          />
          <SelectField
            label={t("library.classSyllabus.class")}
            value={classId}
            placeholder={t("library.classSyllabus.choose")}
            onChange={(e) => setClassId(e.target.value)}
            options={(classes.data?.items ?? []).map((c) => ({
              value: c.id,
              label: c.section ? `${c.name} – ${c.section}` : c.name,
            }))}
          />
        </div>
        {classId && <ClassSyllabusPicker key={classId} classId={classId} />}
      </CardBody>
    </Card>
  );
}
