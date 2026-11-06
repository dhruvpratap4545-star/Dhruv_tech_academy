/** Content Library API (`/library`). Shapes mirror backend/app/modules/library/schemas.py. */

import type { Page } from "@/lib/api";
import { apiDownload, apiFetch, query } from "@/lib/api";

export type Track = "cbse" | "neet" | "jee" | "upsc" | "custom";
export type NodeKind = "track" | "level" | "subject" | "unit" | "chapter" | "topic";
export type ItemKind = "pdf" | "image" | "video_link" | "link" | "text";
export type ItemStatus = "draft" | "in_review" | "published" | "archived";
export type Medium = "hi" | "en" | "both";

export type SyllabusNode = {
  id: string;
  institute_id: string | null;
  track: string;
  parent_id: string | null;
  kind: NodeKind;
  name: string;
  code: string;
  order: number;
  mediums: string[];
  difficulty: string | null;
  exam_tags: string[];
  status: string;
  child_count: number;
};

export type NodeCrumb = { id: string; name: string; kind: string };
export type NodeDetail = { node: SyllabusNode; breadcrumb: NodeCrumb[]; children: SyllabusNode[] };

export type ContentItem = {
  id: string;
  institute_id: string | null;
  title: string;
  kind: ItemKind;
  file_id: string | null;
  file: { id: string; original_name: string; content_type: string; size: number } | null;
  url: string | null;
  video_provider: string | null;
  video_id: string | null;
  body: string | null;
  node_ids: string[];
  medium: Medium;
  author: string | null;
  source: string | null;
  status: ItemStatus;
  version: number;
  created_by: string;
  reviewed_by: string | null;
  review_note: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ItemVersion = {
  id: string;
  item_id: string;
  version: number;
  fields: Record<string, unknown>;
  edited_by: string;
  created_at: string;
};

export type LinkedNode = { id: string; name: string; kind: string; track: string; path: string };

export type SearchResults = {
  query: string;
  nodes: LinkedNode[];
  items: {
    id: string;
    title: string;
    kind: string;
    medium: string;
    status: string;
    node_ids: string[];
  }[];
};

export type MySyllabus = {
  class_id: string;
  class_name: string;
  student_user_id: string | null;
  student_name: string | null;
  nodes: LinkedNode[];
};

export type ClassSyllabus = { class_id: string; class_name: string; nodes: LinkedNode[] };

export type ImportResult = {
  dry_run: boolean;
  rows_total: number;
  rows_valid: number;
  problems: { row: number; messages: string[] }[];
  created: number;
  updated: number;
  unchanged: number;
  by_kind: Record<string, number>;
};

export type NodeInput = {
  parent_id?: string | null;
  institute_id?: string | null;
  track?: Track | null;
  kind: NodeKind;
  name: string;
  code?: string | null;
  mediums?: ("hi" | "en")[];
};

export type ItemInput = {
  institute_id?: string | null;
  title: string;
  kind: "video_link" | "link" | "text";
  url?: string | null;
  body?: string | null;
  node_ids: string[];
  medium: Medium;
  author?: string | null;
  source?: string | null;
};

export type SearchFilters = { q: string; track?: string; kind?: string; medium?: string };

export const libraryKeys = {
  all: ["library"] as const,
  tracks: ["library", "tracks"] as const,
  node: (id: string) => ["library", "node", id] as const,
  children: (parentId: string | null, archived: boolean) =>
    ["library", "children", parentId ?? "root", archived] as const,
  items: (filters: Record<string, unknown>) => ["library", "items", filters] as const,
  versions: (itemId: string) => ["library", "versions", itemId] as const,
  search: (filters: SearchFilters) => ["library", "search", filters] as const,
  my: ["library", "my"] as const,
  classSyllabus: (classId: string) => ["library", "class", classId] as const,
};

export const fetchTracks = (signal?: AbortSignal) =>
  apiFetch<SyllabusNode[]>("/library/tracks", { signal });

export const fetchChildren = (
  parentId: string | null,
  includeArchived = false,
  signal?: AbortSignal,
) =>
  apiFetch<SyllabusNode[]>(
    `/library/nodes${query({ parent_id: parentId, include_archived: includeArchived || undefined })}`,
    { signal },
  );

export const fetchNode = (id: string, signal?: AbortSignal) =>
  apiFetch<NodeDetail>(`/library/nodes/${id}`, { signal });

export const createNode = (body: NodeInput) =>
  apiFetch<SyllabusNode>("/library/nodes", { method: "POST", body });
export const updateNode = (id: string, body: { name?: string }) =>
  apiFetch<SyllabusNode>(`/library/nodes/${id}`, { method: "PATCH", body });
export const archiveNode = (id: string) =>
  apiFetch<SyllabusNode>(`/library/nodes/${id}/archive`, { method: "POST" });
export const reorderNode = (id: string, position: number) =>
  apiFetch<SyllabusNode>(`/library/nodes/${id}/reorder`, { method: "POST", body: { position } });

export const downloadImportTemplate = () =>
  apiDownload("/library/import/template", "syllabus-import-template.xlsx");

export function importSyllabus(file: File, dryRun: boolean, instituteId?: string | null) {
  const form = new FormData();
  form.append("file", file);
  if (instituteId) form.append("institute_id", instituteId);
  return apiFetch<ImportResult>(`/library/import${query({ dry_run: dryRun })}`, {
    method: "POST",
    body: form,
  });
}

export const searchLibrary = (filters: SearchFilters, signal?: AbortSignal) =>
  apiFetch<SearchResults>(`/library/search${query(filters)}`, { signal });

export const fetchItems = (
  filters: {
    node_id?: string;
    status?: ItemStatus;
    mine?: boolean;
    cursor?: string;
    limit?: number;
  },
  signal?: AbortSignal,
) => apiFetch<Page<ContentItem>>(`/library/items${query(filters)}`, { signal });

export const createItem = (body: ItemInput) =>
  apiFetch<ContentItem>("/library/items", { method: "POST", body });

export function uploadItem(input: {
  file: File;
  title: string;
  node_ids: string[];
  medium: Medium;
  institute_id?: string | null;
  author?: string;
  source?: string;
}) {
  const form = new FormData();
  form.append("file", input.file);
  form.append("title", input.title);
  for (const id of input.node_ids) form.append("node_ids", id);
  form.append("medium", input.medium);
  if (input.institute_id) form.append("institute_id", input.institute_id);
  if (input.author) form.append("author", input.author);
  if (input.source) form.append("source", input.source);
  return apiFetch<ContentItem>("/library/items/upload", { method: "POST", body: form });
}

export const itemAction = (
  id: string,
  action: "submit" | "publish" | "reject" | "archive",
  note?: string,
) =>
  apiFetch<ContentItem>(`/library/items/${id}/${action}`, {
    method: "POST",
    body: action === "publish" || action === "reject" ? { note: note || null } : undefined,
  });

export const fetchVersions = (id: string, signal?: AbortSignal) =>
  apiFetch<ItemVersion[]>(`/library/items/${id}/versions`, { signal });

export const fetchMySyllabus = (signal?: AbortSignal) =>
  apiFetch<MySyllabus[]>("/library/my", { signal });

export const fetchClassSyllabus = (classId: string, signal?: AbortSignal) =>
  apiFetch<ClassSyllabus>(`/library/classes/${classId}/syllabus`, { signal });
export const setClassSyllabus = (classId: string, nodeIds: string[]) =>
  apiFetch<ClassSyllabus>(`/library/classes/${classId}/syllabus`, {
    method: "PUT",
    body: { node_ids: nodeIds },
  });
