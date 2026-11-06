/** Homework Board API (`/homework`). Shapes mirror backend/app/modules/homework/schemas.py. */

import type { Page } from "@/lib/api";
import { apiDownload, apiFetch, query } from "@/lib/api";

export type FileInfo = {
  id: string;
  original_name: string;
  content_type: string;
  size: number;
  created_at: string;
};

export type Medium = "en" | "hi" | "bilingual";
export type HomeworkStatus = "draft" | "published" | "archived";
export type StudentStatus = "pending" | "overdue" | "submitted" | "checked" | "redo";
export type Tab = "pending" | "submitted" | "checked" | "overdue";

export type Homework = {
  id: string;
  institute_id: string;
  branch_id: string;
  class_id: string;
  class_name: string;
  subject: string;
  node_id: string | null;
  title: string;
  instructions: string;
  attachments: FileInfo[];
  medium: Medium | null;
  total_marks: number | null;
  publish_at: string | null;
  due_at: string;
  allow_late: boolean;
  allow_resubmit: boolean;
  status: HomeworkStatus;
  is_visible: boolean;
  created_by: string;
  created_at: string;
};

export type Submission = {
  id: string;
  homework_id: string;
  student_user_id: string;
  student_name: string | null;
  text: string;
  files: FileInfo[];
  submitted_at: string;
  is_late: boolean;
  attempts: number;
  status: "submitted" | "checked" | "redo";
  marks: number | null;
  grade: string | null;
  remark: string | null;
  checked_at: string | null;
};

export type BoardRow = {
  homework: Homework;
  student_status: StudentStatus;
  submission: Submission | null;
};

export type TrackerRow = {
  student_user_id: string;
  full_name: string;
  roll_no: string | null;
  student_status: StudentStatus;
  submission_id: string | null;
  submitted_at: string | null;
  is_late: boolean;
  marks: number | null;
};

export type Tracker = {
  homework_id: string;
  counts: Record<string, number>;
  late: number;
  rows: TrackerRow[];
};

export type ShareText = { text: string; url: string; whatsapp_url: string };

export type ReportRow = {
  key: string | null;
  label: string;
  homework: number;
  expected: number;
  submitted: number;
  late: number;
  completion_rate: number;
};

export type Report = {
  date_from: string | null;
  date_to: string | null;
  totals: ReportRow;
  by_class: ReportRow[];
  by_subject: ReportRow[];
  by_teacher: ReportRow[];
};

export type HomeworkPayload = {
  class_id: string;
  subject: string;
  node_id?: string | null;
  title: string;
  instructions: string;
  medium?: Medium | null;
  total_marks?: number | null;
  publish: "draft" | "now" | "schedule";
  publish_at?: string | null;
  due_at: string;
  allow_late: boolean;
  allow_resubmit: boolean;
};

export type HomeworkFilters = {
  class_id?: string;
  status?: HomeworkStatus;
  cursor?: string;
  limit?: number;
};

export type ReportFilters = { class_id?: string; branch_id?: string; from?: string; to?: string };

export type TopicHit = { id: string; name: string; kind: string; track: string; path: string };

export const homeworkKeys = {
  all: ["homework"] as const,
  list: (filters: HomeworkFilters) => ["homework", "list", filters] as const,
  detail: (id: string, studentId = "") => ["homework", "detail", id, studentId] as const,
  tracker: (id: string) => ["homework", "tracker", id] as const,
  submission: (id: string, sid: string) => ["homework", "submission", id, sid] as const,
  mine: (tab: Tab) => ["homework", "mine", tab] as const,
  child: (studentId: string) => ["homework", "child", studentId] as const,
  report: (filters: ReportFilters) => ["homework", "report", filters] as const,
};

export const fetchHomeworkList = (filters: HomeworkFilters, signal?: AbortSignal) =>
  apiFetch<Page<Homework>>(`/homework${query(filters)}`, { signal });

/** `studentId` picks which linked child a parent is looking at; the server checks the link. */
export const fetchHomework = (id: string, signal?: AbortSignal, studentId?: string) =>
  apiFetch<BoardRow>(`/homework/${id}${query({ student_id: studentId })}`, { signal });

export const createHomework = (body: HomeworkPayload) =>
  apiFetch<Homework>("/homework", { method: "POST", body });

export const updateHomework = (
  id: string,
  body: Partial<HomeworkPayload> & { attachment_ids?: string[] },
) => {
  // `class_id` and `publish` are fixed once created; publishing has its own endpoint.
  const { class_id: _class, publish: _publish, ...rest } = body;
  void _class;
  void _publish;
  return apiFetch<Homework>(`/homework/${id}`, { method: "PATCH", body: rest });
};

export const publishHomework = (id: string, publishAt?: string | null) =>
  apiFetch<Homework>(`/homework/${id}/publish`, {
    method: "POST",
    body: publishAt ? { publish_at: publishAt } : {},
  });

export const archiveHomework = (id: string) =>
  apiFetch<Homework>(`/homework/${id}/archive`, { method: "POST" });

export const duplicateHomework = (id: string, classId?: string) =>
  apiFetch<Homework>(`/homework/${id}/duplicate`, {
    method: "POST",
    body: classId ? { class_id: classId } : {},
  });

export function uploadAttachments(id: string, files: File[]) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return apiFetch<Homework>(`/homework/${id}/attachments`, { method: "POST", body: form });
}

export const fetchTracker = (id: string, signal?: AbortSignal) =>
  apiFetch<Tracker>(`/homework/${id}/tracker`, { signal });

export const remindPending = (id: string) =>
  apiFetch<{ sent: number }>(`/homework/${id}/remind`, { method: "POST" });

export const fetchShareText = (id: string) => apiFetch<ShareText>(`/homework/${id}/share-text`);

export const fetchSubmission = (id: string, sid: string, signal?: AbortSignal) =>
  apiFetch<Submission>(`/homework/${id}/submissions/${sid}`, { signal });

export const checkSubmission = (
  id: string,
  sid: string,
  body: { marks?: number | null; grade?: string | null; remark?: string | null; redo?: boolean },
) => apiFetch<Submission>(`/homework/${id}/submissions/${sid}/check`, { method: "POST", body });

export const fetchMyBoard = (tab: Tab, signal?: AbortSignal) =>
  apiFetch<BoardRow[]>(`/homework/mine${query({ tab })}`, { signal });

export const fetchChildBoard = (studentId: string, signal?: AbortSignal) =>
  apiFetch<BoardRow[]>(`/homework/children/${studentId}`, { signal });

export function submitHomework(id: string, text: string, files: File[]) {
  const form = new FormData();
  form.append("text", text);
  for (const file of files) form.append("files", file);
  return apiFetch<Submission>(`/homework/${id}/submission`, { method: "PUT", body: form });
}

export const fetchReport = (filters: ReportFilters, signal?: AbortSignal) =>
  apiFetch<Report>(`/homework/reports/summary${query(filters)}`, { signal });

export const downloadReport = (filters: ReportFilters) =>
  apiDownload(`/homework/reports/export${query(filters)}`, "homework-report.xlsx");

export async function searchTopics(q: string, signal?: AbortSignal): Promise<TopicHit[]> {
  const result = await apiFetch<{ nodes: TopicHit[] }>(`/library/search${query({ q })}`, {
    signal,
  });
  return result.nodes;
}

/** Where a file is downloaded from. The API decides access and redirects to a signed link. */
export function fileUrl(fileId: string): string {
  const base = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
  return `${base}/files/${fileId}`;
}
