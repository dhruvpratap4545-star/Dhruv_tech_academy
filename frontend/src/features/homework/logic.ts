/** Pure helpers for the homework screens. Kept apart from components so they can be tested. */

import type { BoardRow, StudentStatus, Tab } from "@/features/homework/api";
import type { MessageKey } from "@/lib/i18n";

/** Matches the backend limit on attachments and submission files. */
export const MAX_SUBMISSION_FILES = 5;

export type Tone = "neutral" | "primary" | "success" | "warning" | "danger" | "accent";

/** The same colour for a status on every screen. */
export const STATUS_TONE: Record<StudentStatus, Tone> = {
  pending: "primary",
  overdue: "danger",
  submitted: "accent",
  checked: "success",
  redo: "warning",
};

/**
 * The WhatsApp link, built only from the text the server composed.
 *
 * Nothing else is added here: the share text is written by the API so that it can never
 * contain a student's name or marks, and appending anything client-side would undo that.
 */
export function whatsappUrl(shareText: string): string {
  return `https://wa.me/?text=${encodeURIComponent(shareText)}`;
}

/** Soonest due first, as the student board is read. */
export function sortByDue(rows: BoardRow[]): BoardRow[] {
  return [...rows].sort(
    (a, b) => new Date(a.homework.due_at).getTime() - new Date(b.homework.due_at).getTime(),
  );
}

const IST_OFFSET_MS = 330 * 60 * 1000;

/**
 * An ISO time as the `YYYY-MM-DDTHH:mm` a `datetime-local` input holds, in Indian time.
 * The API reads a time with no zone as IST, so the round trip is exact.
 */
export function toIstInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() + IST_OFFSET_MS).toISOString().slice(0, 16);
}

/** Whether to offer the submit form. The server has the final word on late and repeats. */
export function canStillSubmit(
  { homework, student_status, submission }: BoardRow,
  now: number = Date.now(),
): boolean {
  if (homework.status !== "published" || student_status === "checked") return false;
  if (student_status === "redo" || !submission) {
    return student_status !== "overdue" || homework.allow_late;
  }
  return homework.allow_resubmit && new Date(homework.due_at).getTime() > now;
}

/** The student board's tabs, in reading order. Redo work shows under Pending. */
export const TABS: { value: Tab; label: MessageKey }[] = [
  { value: "pending", label: "homework.student.pending" },
  { value: "submitted", label: "homework.student.submitted" },
  { value: "checked", label: "homework.student.checked" },
  { value: "overdue", label: "homework.student.overdue" },
];
