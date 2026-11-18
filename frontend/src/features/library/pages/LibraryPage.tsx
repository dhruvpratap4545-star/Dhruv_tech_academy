import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Card, CardHeader } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import { EmptyState } from "@/components/Table";
import type {
  ContentItem,
  Level,
  LinkedNode,
  NodeCrumb,
  NodeDetail,
  SearchFilters,
} from "@/features/library/api";
import {
  LEVELS,
  createNode,
  fetchChildren,
  fetchItems,
  fetchMySyllabus,
  fetchNode,
  fetchTracks,
  libraryKeys,
  searchLibrary,
} from "@/features/library/api";
import { AddMaterialModal } from "@/features/library/components/AddMaterialModal";
import { HistoryModal } from "@/features/library/components/HistoryModal";
import { ItemActions } from "@/features/library/components/ItemActions";
import { LibraryLayout } from "@/features/library/components/LibraryLayout";
import { MaterialCard } from "@/features/library/components/MaterialCard";
import { useOwnerOptions } from "@/features/library/useOwnerOptions";
import { useCan } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/**
 * Library: pick a section in four steps — Track › Level › Subject › Topic — and see every
 * document filed under it.
 *
 * The section bar is the whole navigation: each dropdown lists what sits inside the one
 * before it, so nobody has to guess where a topic lives. Teachers and admins can add a
 * missing level, subject or topic right there, and add material to whatever is open; it is
 * visible at once. The open section lives in the URL (`/library/node/:id`), so a link to it
 * can be shared.
 *
 * Students and parents see only the parts of the syllabus their classes are linked to; the
 * server decides that, the page only follows.
 */
export function LibraryPage() {
  const { t } = useT();
  const { nodeId } = useParams();
  const [filters, setFilters] = useState<SearchFilters>({ q: "" });
  const searching = filters.q.trim().length >= 2;
  const detail = useQuery({
    queryKey: libraryKeys.node(nodeId ?? ""),
    queryFn: ({ signal }) => fetchNode(nodeId!, signal),
    enabled: Boolean(nodeId),
  });

  return (
    <LibraryLayout title={t("library.title")} description={t("library.description")}>
      <SectionBar detail={nodeId ? detail.data : undefined} />
      <SearchBar filters={filters} onChange={setFilters} />
      {searching ? (
        <SearchResultsView
          filters={{ ...filters, q: filters.q.trim() }}
          onOpen={() => setFilters({ q: "" })}
        />
      ) : nodeId ? (
        detail.isLoading ? (
          <Spinner />
        ) : detail.error ? (
          <Alert tone="danger">{detail.error.message}</Alert>
        ) : detail.data ? (
          <SectionView detail={detail.data} />
        ) : null
      ) : (
        <StartView />
      )}
    </LibraryLayout>
  );
}

/** The open section and everything above it, outermost first. */
function pathOf(detail: NodeDetail | undefined): NodeCrumb[] {
  if (!detail) return [];
  const { node, breadcrumb } = detail;
  return breadcrumb.some((c) => c.id === node.id)
    ? breadcrumb
    : [...breadcrumb, { id: node.id, name: node.name, kind: node.kind }];
}

function SectionBar({ detail }: { detail: NodeDetail | undefined }) {
  const { t } = useT();
  const navigate = useNavigate();
  const canAdd = useCan("library:contribute");
  const [adding, setAdding] = useState<{ parent: NodeCrumb; level: Level } | null>(null);
  const path = pathOf(detail);

  function choose(index: number, id: string) {
    if (id) navigate(`/library/node/${id}`);
    else if (index > 0) navigate(`/library/node/${path[index - 1]!.id}`);
    else navigate("/library");
  }

  return (
    <Card className="p-4">
      <h2 className="mb-3 text-sm font-semibold text-fg">{t("library.sections.title")}</h2>
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {LEVELS.map((level, index) => {
          const parent = index === 0 ? null : path[index - 1];
          const reachable = index === 0 || Boolean(parent);
          return (
            <li key={level} className="min-w-0 space-y-1.5">
              <LevelSelect
                level={level}
                step={index + 1}
                parentId={parent?.id ?? null}
                enabled={reachable}
                value={path[index]?.id ?? ""}
                onChange={(id) => choose(index, id)}
              />
              {canAdd && parent && (
                <button
                  type="button"
                  onClick={() => setAdding({ parent, level })}
                  className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                >
                  <Icon name="plus" className="size-3" />
                  {t("library.sections.add", { level: t(`library.kindName.${level}`) })}
                </button>
              )}
            </li>
          );
        })}
      </ol>
      {adding && (
        <AddSectionModal
          parent={adding.parent}
          level={adding.level}
          onClose={() => setAdding(null)}
          onAdded={(id) => {
            setAdding(null);
            navigate(`/library/node/${id}`);
          }}
        />
      )}
    </Card>
  );
}

/** One step of the section bar: the sections inside the step before it. */
function LevelSelect({
  level,
  step,
  parentId,
  enabled,
  value,
  onChange,
}: {
  level: Level;
  step: number;
  parentId: string | null;
  enabled: boolean;
  value: string;
  onChange: (id: string) => void;
}) {
  const { t } = useT();
  const options = useQuery({
    queryKey: parentId ? libraryKeys.children(parentId, false) : libraryKeys.tracks,
    queryFn: ({ signal }) =>
      parentId ? fetchChildren(parentId, false, signal) : fetchTracks(signal),
    enabled,
  });
  const name = t(`library.kindName.${level}`);
  const rows = options.data ?? [];
  return (
    <SelectField
      label={`${step}. ${name}`}
      value={value}
      disabled={!enabled || options.isLoading}
      onChange={(e) => onChange(e.target.value)}
      placeholder={
        !enabled
          ? t("library.sections.pickAbove")
          : options.isSuccess && rows.length === 0
            ? t("library.sections.none", { level: name })
            : t("library.sections.choose", { level: name })
      }
      options={rows.map((n) => ({ value: n.id, label: n.name }))}
    />
  );
}

function AddSectionModal({
  parent,
  level,
  onClose,
  onAdded,
}: {
  parent: NodeCrumb;
  level: Level;
  onClose: () => void;
  onAdded: (id: string) => void;
}) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const owners = useOwnerOptions();
  const [owner, setOwner] = useState<string | null>(null);
  const [name, setName] = useState("");
  const levelName = t(`library.kindName.${level}`);
  const save = useMutation({
    mutationFn: () =>
      createNode({
        parent_id: parent.id,
        // Inside an institute's own section the server keeps it there; under the shared
        // syllabus it goes into the chosen library (a teacher's own institute).
        institute_id: (owner ?? owners[0]?.value ?? "") || null,
        kind: level,
        name: name.trim(),
      }),
    onSuccess: (node) => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      onAdded(node.id);
    },
  });
  return (
    <Modal
      open
      onClose={onClose}
      title={t("library.sections.addTitle", { level: levelName, parent: parent.name })}
      description={t("library.sections.addHint")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={name.trim().length < 1}
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {owners.length > 1 && (
          <SelectField
            label={t("library.manage.owner")}
            value={owner ?? owners[0]?.value ?? ""}
            onChange={(e) => setOwner(e.target.value)}
            options={owners}
          />
        )}
        <TextField
          label={t("library.sections.name", { level: levelName })}
          value={name}
          maxLength={200}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && name.trim()) save.mutate();
          }}
        />
        {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
      </div>
    </Modal>
  );
}

function SearchBar({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (f: SearchFilters) => void;
}) {
  const { t } = useT();
  const set = (key: keyof SearchFilters, value: string) =>
    onChange({ ...filters, [key]: value || undefined, q: key === "q" ? value : filters.q });
  return (
    <Card className="grid gap-3 p-4 sm:grid-cols-[2fr_1fr_1fr_1fr] sm:items-end">
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-fg">{t("library.search")}</span>
        <input
          type="search"
          value={filters.q}
          onChange={(e) => set("q", e.target.value)}
          placeholder={t("library.searchPlaceholder")}
          className="h-11 w-full rounded-lg border border-line bg-surface px-3 text-sm text-fg"
        />
      </label>
      <SelectField
        label={t("library.track")}
        value={filters.track ?? ""}
        onChange={(e) => set("track", e.target.value)}
        options={[
          { value: "", label: t("library.allTracks") },
          ...["cbse", "neet", "jee", "upsc"].map((v) => ({ value: v, label: v.toUpperCase() })),
        ]}
      />
      <SelectField
        label={t("library.kind")}
        value={filters.kind ?? ""}
        onChange={(e) => set("kind", e.target.value)}
        options={[
          { value: "", label: t("library.allKinds") },
          ...(["pdf", "image", "video_link", "link", "text"] as const).map((v) => ({
            value: v,
            label: t(`library.kind.${v}`),
          })),
        ]}
      />
      <SelectField
        label={t("library.medium")}
        value={filters.medium ?? ""}
        onChange={(e) => set("medium", e.target.value)}
        options={[
          { value: "", label: t("library.allMediums") },
          { value: "hi", label: t("library.medium.hi") },
          { value: "en", label: t("library.medium.en") },
          { value: "both", label: t("library.medium.both") },
        ]}
      />
    </Card>
  );
}

function SearchResultsView({ filters, onOpen }: { filters: SearchFilters; onOpen: () => void }) {
  const { t } = useT();
  const results = useQuery({
    queryKey: libraryKeys.search(filters),
    queryFn: ({ signal }) => searchLibrary(filters, signal),
  });
  if (results.isLoading) return <Spinner />;
  if (results.error) return <Alert tone="danger">{results.error.message}</Alert>;
  const data = results.data;
  if (!data || (data.nodes.length === 0 && data.items.length === 0)) {
    return <EmptyState title={t("library.noResults")} />;
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title={t("library.searchTopics")} />
        <ul className="divide-y divide-line">
          {data.nodes.map((node) => (
            <li key={node.id}>
              <Link
                to={`/library/node/${node.id}`}
                onClick={onOpen}
                className="block px-4 py-3 hover:bg-surface-2"
              >
                <span className="block text-sm font-medium text-fg">{node.name}</span>
                <span className="block truncate text-xs text-fg-3">{node.path}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title={t("library.searchItems")} />
        <ul className="divide-y divide-line">
          {data.items.map((item) => (
            <li key={item.id}>
              <Link
                to={`/library/node/${item.node_ids[0]}`}
                onClick={onOpen}
                className="block px-4 py-3 hover:bg-surface-2"
              >
                <span className="block text-sm font-medium text-fg">{item.title}</span>
                <span className="text-xs text-fg-3">{t(`library.kind.${item.kind as "pdf"}`)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function NodeList({ nodes }: { nodes: { id: string; name: string; sub?: string }[] }) {
  return (
    <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {nodes.map((node) => (
        <li key={node.id}>
          <Link
            to={`/library/node/${node.id}`}
            className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface p-4 hover:bg-surface-2"
          >
            <span className="min-w-0">
              <span className="block font-medium text-fg">{node.name}</span>
              {node.sub && <span className="block truncate text-xs text-fg-3">{node.sub}</span>}
            </span>
            <Icon name="chevron" className="-rotate-90 text-fg-3" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function StartView() {
  const { t } = useT();
  // Staff hold `library:contribute`; learners and parents do not, and start from /my.
  const isStaff = useCan("library:contribute");
  const tracks = useQuery({
    queryKey: libraryKeys.tracks,
    queryFn: ({ signal }) => fetchTracks(signal),
    enabled: isStaff,
  });
  const mine = useQuery({
    queryKey: libraryKeys.my,
    queryFn: ({ signal }) => fetchMySyllabus(signal),
    enabled: !isStaff,
  });

  if (isStaff) {
    if (tracks.isLoading) return <Spinner />;
    if (tracks.error) return <Alert tone="danger">{tracks.error.message}</Alert>;
    return (
      <section className="space-y-3">
        <h2 className="font-display text-lg font-bold text-fg">{t("library.tracks")}</h2>
        <NodeList nodes={(tracks.data ?? []).map((n) => ({ id: n.id, name: n.name }))} />
      </section>
    );
  }
  if (mine.isLoading) return <Spinner />;
  if (mine.error) return <Alert tone="danger">{mine.error.message}</Alert>;
  const classes = (mine.data ?? []).filter((c) => c.nodes.length > 0);
  if (classes.length === 0) return <EmptyState title={t("library.noSyllabus")} />;
  return (
    <div className="space-y-5">
      {classes.map((entry) => (
        <section key={`${entry.class_id}-${entry.student_user_id ?? ""}`} className="space-y-3">
          <h2 className="font-display text-lg font-bold text-fg">
            {entry.class_name}
            {entry.student_name && (
              <span className="ml-2 text-sm font-normal text-fg-2">
                {t("library.forChild", { name: entry.student_name })}
              </span>
            )}
          </h2>
          <NodeList nodes={entry.nodes.map((n) => ({ id: n.id, name: n.name, sub: n.path }))} />
        </section>
      ))}
    </div>
  );
}

function SectionView({ detail }: { detail: NodeDetail }) {
  const { t } = useT();
  const canAdd = useCan("library:contribute");
  const [adding, setAdding] = useState(false);
  const [history, setHistory] = useState<ContentItem | null>(null);
  const { node, children } = detail;
  const path = pathOf(detail);
  // Material on this section *and everything inside it*: a subject lists all its topics'.
  const items = useQuery({
    queryKey: libraryKeys.items({ node_id: node.id }),
    queryFn: ({ signal }) => fetchItems({ node_id: node.id, limit: 100 }, signal),
  });
  const here: LinkedNode = {
    id: node.id,
    name: node.name,
    kind: node.kind,
    track: node.track,
    path: path.map((c) => c.name).join(" › "),
  };
  const list = items.data?.items ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">{t(`library.kindName.${node.kind}`)}</p>
          <h2 className="font-display text-xl font-bold text-fg">{node.name}</h2>
          <p className="truncate text-xs text-fg-3">{here.path}</p>
        </div>
        {canAdd && (
          <Button icon={<Icon name="plus" />} onClick={() => setAdding(true)}>
            {t("library.review.add")}
          </Button>
        )}
      </div>

      {children.length > 0 && (
        <NodeList
          nodes={children.map((c) => ({
            id: c.id,
            name: c.name,
            sub: t(`library.kindName.${c.kind}`),
          }))}
        />
      )}

      <section className="space-y-3">
        <h3 className="font-semibold text-fg">
          {t("library.sections.materialIn", { name: node.name })}
          {items.data && (
            <span className="ml-2 text-sm font-normal text-fg-3">({list.length})</span>
          )}
        </h3>
        {children.length > 0 && (
          <p className="text-xs text-fg-2">{t("library.sections.includesBelow")}</p>
        )}
        {items.isLoading && <Spinner />}
        {items.error && <Alert tone="danger">{items.error.message}</Alert>}
        {items.data && list.length === 0 && (
          <p className="text-sm text-fg-2">{t("library.noMaterial")}</p>
        )}
        <div className="grid gap-3 lg:grid-cols-2">
          {list.map((item) => (
            <MaterialCard
              key={item.id}
              item={item}
              showStatus={item.status !== "published"}
              actions={
                canAdd ? <ItemActions item={item} onHistory={() => setHistory(item)} /> : undefined
              }
            />
          ))}
        </div>
      </section>

      {adding && <AddMaterialModal topics={[here]} onClose={() => setAdding(false)} />}
      {history && <HistoryModal item={history} onClose={() => setHistory(null)} />}
    </div>
  );
}
