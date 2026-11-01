import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Breadcrumb } from "@/components/Breadcrumb";
import { Card, CardHeader } from "@/components/Card";
import { SelectField } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { Spinner } from "@/components/Spinner";
import { EmptyState } from "@/components/Table";
import type { SearchFilters, SyllabusNode } from "@/features/library/api";
import {
  fetchItems,
  fetchMySyllabus,
  fetchNode,
  fetchTracks,
  libraryKeys,
  searchLibrary,
} from "@/features/library/api";
import { LibraryLayout } from "@/features/library/components/LibraryLayout";
import { MaterialCard } from "@/features/library/components/MaterialCard";
import { useCan } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";

/**
 * Library: browse the syllabus level by level and read the material on each topic.
 *
 * Staff start from every track; students and parents start from the parts of the
 * syllabus their classes are linked to (`GET /library/my`). The server decides what
 * each person may see either way — this only chooses the starting point.
 */
export function LibraryPage() {
  const { t } = useT();
  const { nodeId } = useParams();
  const [filters, setFilters] = useState<SearchFilters>({ q: "" });
  const searching = filters.q.trim().length >= 2;

  return (
    <LibraryLayout title={t("library.title")} description={t("library.description")}>
      <SearchBar filters={filters} onChange={setFilters} />
      {searching ? (
        <SearchResultsView filters={{ ...filters, q: filters.q.trim() }} />
      ) : nodeId ? (
        <NodeView nodeId={nodeId} />
      ) : (
        <StartView />
      )}
    </LibraryLayout>
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
        ]}
      />
    </Card>
  );
}

function SearchResultsView({ filters }: { filters: SearchFilters }) {
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
              <Link to={`/library/node/${node.id}`} className="block px-4 py-3 hover:bg-surface-2">
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
            <li key={item.id} className="px-4 py-3">
              <span className="block text-sm font-medium text-fg">{item.title}</span>
              <span className="text-xs text-fg-3">{t(`library.kind.${item.kind as "pdf"}`)}</span>
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

function NodeView({ nodeId }: { nodeId: string }) {
  const { t } = useT();
  const navigate = useNavigate();
  const detail = useQuery({
    queryKey: libraryKeys.node(nodeId),
    queryFn: ({ signal }) => fetchNode(nodeId, signal),
  });
  const items = useQuery({
    queryKey: libraryKeys.items({ node_id: nodeId, status: "published" }),
    queryFn: ({ signal }) =>
      fetchItems({ node_id: nodeId, status: "published", limit: 50 }, signal),
  });

  if (detail.isLoading) return <Spinner />;
  if (detail.error) return <Alert tone="danger">{detail.error.message}</Alert>;
  if (!detail.data) return null;
  const { node, breadcrumb, children } = detail.data;
  const trail = [
    { label: t("library.title"), onSelect: () => navigate("/library") },
    ...breadcrumb.map((crumb) => ({
      label: crumb.name,
      onSelect: crumb.id === node.id ? undefined : () => navigate(`/library/node/${crumb.id}`),
    })),
  ];
  if (!breadcrumb.some((c) => c.id === node.id))
    trail.push({ label: node.name, onSelect: undefined });

  return (
    <div className="space-y-5">
      <Breadcrumb items={trail} />
      <div>
        <p className="eyebrow">{t(`library.kindName.${node.kind}`)}</p>
        <h2 className="font-display text-xl font-bold text-fg">{node.name}</h2>
      </div>
      {children.length > 0 && (
        <NodeList
          nodes={children.map((c: SyllabusNode) => ({
            id: c.id,
            name: c.name,
            sub: t(`library.kindName.${c.kind}`),
          }))}
        />
      )}
      <section className="space-y-3">
        <h3 className="font-semibold text-fg">{t("library.material")}</h3>
        {items.isLoading && <Spinner />}
        {items.data && items.data.items.length === 0 && (
          <p className="text-sm text-fg-2">{t("library.noMaterial")}</p>
        )}
        <div className="grid gap-3 lg:grid-cols-2">
          {(items.data?.items ?? []).map((item) => (
            <MaterialCard key={item.id} item={item} />
          ))}
        </div>
      </section>
    </div>
  );
}
