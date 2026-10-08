import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Badge, StatusBadge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { Icon } from "@/components/Icon";
import type { IconName } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import {
  fetchBranches,
  fetchClasses,
  fetchInstitutes,
  fetchSessions,
  instituteKeys,
} from "@/features/admin/api";
import type { Branch, ClassRow, Institute, Session } from "@/features/auth/types";
import { useCan } from "@/features/auth/useAuth";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";

/**
 * The organisation, as a tree: Platform → Institute → Branch → Session → Class.
 *
 * A tree rather than a table because the hierarchy *is* the information — it is what
 * decides who can see what, and a flat list of institutes next to a flat list of branches
 * never shows you that. Selecting a node shows its detail beside it.
 *
 * Read-only apart from "Add institute". Full branch, session and class management is a
 * later milestone (PRD §12), so this shows the structure that exists rather than
 * pretending to screens that do not.
 */

type NodeKind = "platform" | "institute" | "branch" | "session" | "class";

type TreeNode = {
  key: string;
  kind: NodeKind;
  label: string;
  sub?: string;
  depth: number;
  instituteId?: string;
  branchId?: string;
};

const LEVEL_WORD: Record<NodeKind, string> = {
  platform: "Platform",
  institute: "Institute",
  branch: "Branch",
  session: "Session",
  class: "Class",
};

const LEVEL_ICON: Record<NodeKind, IconName> = {
  platform: "org",
  institute: "building",
  branch: "org",
  session: "calendar",
  class: "class",
};

export function InstitutesPage() {
  const canCreate = useCan("institute:create");
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(null);

  const institutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
  });

  const rows = institutes.data?.items ?? [];

  // Branches, sessions and classes for every visible institute, fetched in parallel.
  // Usually one institute; for platform staff a handful. `useQueries` keeps each one
  // independently cached rather than refetching the lot when any single institute changes.
  const branchQueries = useQueries({
    queries: rows.map((institute) => ({
      queryKey: instituteKeys.branches(institute.id),
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchBranches(institute.id, signal),
    })),
  });
  const sessionQueries = useQueries({
    queries: rows.map((institute) => ({
      queryKey: instituteKeys.sessions(institute.id),
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchSessions(institute.id, signal),
    })),
  });
  const classQueries = useQueries({
    queries: rows.map((institute) => ({
      queryKey: instituteKeys.classes(institute.id),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        fetchClasses(institute.id, undefined, signal),
    })),
  });

  const byInstitute = new Map(
    rows.map((institute, index) => [
      institute.id,
      {
        institute,
        branches: branchQueries[index]?.data?.items ?? [],
        sessions: sessionQueries[index]?.data?.items ?? [],
        classes: classQueries[index]?.data?.items ?? [],
      },
    ]),
  );

  const nodes = buildTree(rows, byInstitute);

  // A link from search carries ?institute= / ?branch=; honour it once, then let clicks win.
  const wanted = params.get("branch")
    ? `branch:${params.get("branch")}`
    : params.get("institute")
      ? `institute:${params.get("institute")}`
      : null;
  const activeKey =
    selected ?? (wanted && nodes.some((n) => n.key === wanted) ? wanted : nodes[0]?.key) ?? null;
  const active = nodes.find((node) => node.key === activeKey) ?? null;

  if (institutes.error) {
    return (
      <Alert tone="danger">
        <p>{institutes.error.message}</p>
      </Alert>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Administration"
        title="Hierarchy"
        description="Platform → Institute → Branch → Academic session → Class. Each level only sees inside itself. Nothing is deleted; items are archived so history stays correct."
        actions={
          canCreate && (
            <Link
              to="/institutes/new"
              className="inline-flex h-9 items-center gap-1.5 rounded-sm bg-accent px-3.5 text-sm font-semibold text-accent-fg hover:bg-accent-hover"
            >
              <Icon name="plus" className="size-4" />
              New institute
            </Link>
          )
        }
      />

      {institutes.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
          <Card className="overflow-hidden">
            <div className="border-b border-line px-4 py-3">
              <h2 className="font-display text-base font-bold text-fg">Structure</h2>
            </div>
            <div
              role="tree"
              aria-label="Organisation structure"
              className="max-h-[32rem] overflow-y-auto py-1.5"
            >
              {nodes.map((node) => (
                <button
                  key={node.key}
                  type="button"
                  role="treeitem"
                  aria-selected={node.key === activeKey}
                  aria-level={node.depth + 1}
                  onClick={() => {
                    setSelected(node.key);
                    if (params.has("institute") || params.has("branch"))
                      setParams({}, { replace: true });
                  }}
                  style={{ paddingLeft: `${0.75 + node.depth * 0.9}rem` }}
                  className={cn(
                    "flex w-full items-center gap-2 py-1.5 pr-3 text-left text-sm",
                    node.key === activeKey
                      ? "bg-accent-soft font-semibold text-accent-ink"
                      : "text-fg-2 hover:bg-surface-2 hover:text-fg",
                  )}
                >
                  <Icon name={LEVEL_ICON[node.kind]} className="size-4 shrink-0 opacity-70" />
                  <span className="min-w-0 flex-1 truncate">{node.label}</span>
                  <span className="shrink-0 text-[0.65rem] font-semibold tracking-wide text-fg-3 uppercase">
                    {LEVEL_WORD[node.kind]}
                  </span>
                </button>
              ))}
            </div>
          </Card>

          <Card className="self-start">
            {active ? (
              <Detail node={active} data={byInstitute} />
            ) : (
              <div className="px-4 py-10 text-center text-sm text-fg-2">
                You do not belong to any institute yet.
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

type InstituteBundle = {
  institute: Institute;
  branches: Branch[];
  sessions: Session[];
  classes: ClassRow[];
};

function buildTree(institutes: Institute[], data: Map<string, InstituteBundle>): TreeNode[] {
  const nodes: TreeNode[] = [];
  // The platform row only earns its place when there is more than one institute to sit
  // under it; for a single-institute admin it is a row that says nothing.
  if (institutes.length > 1) {
    nodes.push({ key: "platform", kind: "platform", label: "Dhruv Online Academy", depth: 0 });
  }
  const base = institutes.length > 1 ? 1 : 0;

  for (const institute of institutes) {
    const bundle = data.get(institute.id);
    nodes.push({
      key: `institute:${institute.id}`,
      kind: "institute",
      label: institute.name,
      sub: institute.code,
      depth: base,
      instituteId: institute.id,
    });

    for (const branch of bundle?.branches ?? []) {
      nodes.push({
        key: `branch:${branch.id}`,
        kind: "branch",
        label: branch.name,
        sub: branch.code,
        depth: base + 1,
        instituteId: institute.id,
        branchId: branch.id,
      });

      // Only the current session is expanded. Showing every past year turns a readable
      // tree into a scroll, and the answer people want is "what is running now".
      for (const session of (bundle?.sessions ?? []).filter((s) => s.is_current)) {
        nodes.push({
          key: `session:${branch.id}:${session.id}`,
          kind: "session",
          label: session.name,
          depth: base + 2,
          instituteId: institute.id,
          branchId: branch.id,
        });

        for (const row of (bundle?.classes ?? []).filter(
          (c) => c.branch_id === branch.id && c.academic_session_id === session.id,
        )) {
          nodes.push({
            key: `class:${row.id}`,
            kind: "class",
            label: row.name,
            sub: row.code,
            depth: base + 3,
            instituteId: institute.id,
            branchId: branch.id,
          });
        }
      }
    }
  }
  return nodes;
}

function Detail({ node, data }: { node: TreeNode; data: Map<string, InstituteBundle> }) {
  const bundle = node.instituteId ? data.get(node.instituteId) : undefined;

  if (node.kind === "platform") {
    return (
      <>
        <Head title="Dhruv Online Academy" kind="platform" />
        <Facts
          rows={[
            ["Institutes", String(data.size)],
            ["Branches", String([...data.values()].reduce((n, b) => n + b.branches.length, 0))],
            ["Classes", String([...data.values()].reduce((n, b) => n + b.classes.length, 0))],
            ["Run by", "Super Admin and Platform Admin"],
          ]}
        />
      </>
    );
  }

  if (node.kind === "institute" && bundle) {
    const { institute, branches, sessions, classes } = bundle;
    return (
      <>
        <Head
          title={institute.name}
          kind="institute"
          path={institute.code}
          badge={<StatusBadge status={institute.status} />}
        />
        <Facts
          rows={[
            ["Type", institute.type],
            ["Code", institute.code],
            ["Contact", institute.contact_email ?? "—"],
            ["Branches", branches.map((b) => b.name).join(", ") || "None yet"],
            [
              "Sessions",
              sessions.map((s) => `${s.name}${s.is_current ? " (current)" : ""}`).join(", ") ||
                "None yet",
            ],
            ["Classes", String(classes.length)],
            ["Added", formatDate(institute.created_at)],
          ]}
        />
      </>
    );
  }

  if (node.kind === "branch" && bundle) {
    const branch = bundle.branches.find((b) => b.id === node.branchId);
    if (!branch) return null;
    const branchClasses = bundle.classes.filter((c) => c.branch_id === branch.id);
    return (
      <>
        <Head
          title={branch.name}
          kind="branch"
          path={`${bundle.institute.name} / ${branch.name}`}
          badge={<StatusBadge status={branch.status} />}
        />
        <Facts
          rows={[
            ["Code", branch.code],
            ["City", branch.city ?? "—"],
            ["Classes", String(branchClasses.length)],
          ]}
        />
      </>
    );
  }

  if (node.kind === "session" && bundle) {
    const session = bundle.sessions.find((s) => s.is_current);
    if (!session) return null;
    return (
      <>
        <Head
          title={session.name}
          kind="session"
          path={bundle.institute.name}
          badge={session.is_current ? <Badge tone="accent">Current</Badge> : undefined}
        />
        <Facts
          rows={[
            ["Starts", formatDate(session.start_date)],
            ["Ends", formatDate(session.end_date)],
          ]}
        />
      </>
    );
  }

  if (node.kind === "class" && bundle) {
    const row = bundle.classes.find((c) => `class:${c.id}` === node.key);
    if (!row) return null;
    const branch = bundle.branches.find((b) => b.id === row.branch_id);
    return (
      <>
        <Head
          title={row.name}
          kind="class"
          path={`${bundle.institute.name} / ${branch?.name ?? "—"}`}
          badge={<StatusBadge status={row.status} />}
        />
        <Facts
          rows={[
            ["Code", row.code],
            ["Branch", branch?.name ?? "—"],
          ]}
        />
      </>
    );
  }

  return null;
}

function Head({
  title,
  kind,
  path,
  badge,
}: {
  title: string;
  kind: NodeKind;
  path?: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2 border-b border-line p-4">
      <div className="min-w-0">
        <h2 className="font-display text-lg font-bold text-fg">{title}</h2>
        {path && <p className="mt-0.5 truncate text-sm text-fg-2">{path}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {badge}
        <Badge tone="neutral">{LEVEL_WORD[kind]}</Badge>
      </div>
    </div>
  );
}

function Facts({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="divide-y divide-line">
      {rows.map(([term, value]) => (
        <div key={term} className="flex flex-wrap gap-x-4 gap-y-0.5 px-4 py-2.5">
          <dt className="w-32 shrink-0 text-sm text-fg-3">{term}</dt>
          <dd className="min-w-0 flex-1 text-sm text-fg">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
