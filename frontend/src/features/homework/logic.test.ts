import { describe, expect, it } from "vitest";

import type { BoardRow, Homework, Submission } from "@/features/homework/api";
import {
  STATUS_TONE,
  TABS,
  canStillSubmit,
  sortByDue,
  toIstInput,
  whatsappUrl,
} from "@/features/homework/logic";

function homework(overrides: Partial<Homework> = {}): Homework {
  return {
    id: "h1",
    institute_id: "i",
    branch_id: "b",
    class_id: "c",
    class_name: "Class 10-A",
    subject: "Maths",
    node_id: null,
    title: "Algebra",
    instructions: "",
    attachments: [],
    medium: null,
    total_marks: 10,
    publish_at: "2026-11-01T00:00:00Z",
    due_at: "2026-11-10T12:00:00Z",
    allow_late: true,
    allow_resubmit: true,
    status: "published",
    is_visible: true,
    created_by: "t",
    created_at: "2026-11-01T00:00:00Z",
    ...overrides,
  };
}

function submission(status: Submission["status"]): Submission {
  return {
    id: "s1",
    homework_id: "h1",
    student_user_id: "u",
    student_name: null,
    text: "",
    files: [],
    submitted_at: "2026-11-05T00:00:00Z",
    is_late: false,
    attempts: 1,
    status,
    marks: null,
    grade: null,
    remark: null,
    checked_at: null,
  };
}

const row = (
  student_status: BoardRow["student_status"],
  sub: Submission | null,
  hw: Partial<Homework> = {},
): BoardRow => ({ homework: homework(hw), student_status, submission: sub });

const BEFORE_DUE = Date.parse("2026-11-05T00:00:00Z");
const AFTER_DUE = Date.parse("2026-11-12T00:00:00Z");

describe("status badges", () => {
  it("gives every student status its own fixed tone", () => {
    expect(STATUS_TONE).toEqual({
      pending: "primary",
      overdue: "danger",
      submitted: "accent",
      checked: "success",
      redo: "warning",
    });
  });

  it("offers the four board tabs in reading order", () => {
    expect(TABS.map((tab) => tab.value)).toEqual(["pending", "submitted", "checked", "overdue"]);
  });
});

describe("whatsappUrl", () => {
  it("encodes exactly the server's share text and adds nothing", () => {
    const text = "Homework: Algebra\nClass 10-A · due 10-11-2026\nhttps://x.test/homework/h1";
    const url = whatsappUrl(text);
    expect(url.startsWith("https://wa.me/?text=")).toBe(true);
    expect(decodeURIComponent(url.slice("https://wa.me/?text=".length))).toBe(text);
  });
});

describe("sortByDue", () => {
  it("puts the soonest due first without mutating the input", () => {
    const later = row("pending", null, { id: "late", due_at: "2026-12-01T00:00:00Z" });
    const sooner = row("pending", null, { id: "soon", due_at: "2026-11-02T00:00:00Z" });
    const input = [later, sooner];
    expect(sortByDue(input).map((r) => r.homework.id)).toEqual(["soon", "late"]);
    expect(input[0]).toBe(later);
  });
});

describe("toIstInput", () => {
  it("shows a UTC time as Indian time for a datetime-local input", () => {
    expect(toIstInput("2026-11-10T12:00:00Z")).toBe("2026-11-10T17:30");
    expect(toIstInput(null)).toBe("");
    expect(toIstInput("not a date")).toBe("");
  });
});

describe("canStillSubmit", () => {
  it("allows a first submission before the due time", () => {
    expect(canStillSubmit(row("pending", null), BEFORE_DUE)).toBe(true);
  });

  it("allows an overdue first submission only when late work is accepted", () => {
    expect(canStillSubmit(row("overdue", null), AFTER_DUE)).toBe(true);
    expect(canStillSubmit(row("overdue", null, { allow_late: false }), AFTER_DUE)).toBe(false);
  });

  it("allows resubmitting only before the due time and when the teacher allows it", () => {
    expect(canStillSubmit(row("submitted", submission("submitted")), BEFORE_DUE)).toBe(true);
    expect(canStillSubmit(row("submitted", submission("submitted")), AFTER_DUE)).toBe(false);
    expect(
      canStillSubmit(
        row("submitted", submission("submitted"), { allow_resubmit: false }),
        BEFORE_DUE,
      ),
    ).toBe(false);
  });

  it("always reopens redo work and never reopens checked work", () => {
    expect(canStillSubmit(row("redo", submission("redo")), AFTER_DUE)).toBe(true);
    expect(canStillSubmit(row("checked", submission("checked")), BEFORE_DUE)).toBe(false);
  });

  it("refuses archived homework", () => {
    expect(canStillSubmit(row("pending", null, { status: "archived" }), BEFORE_DUE)).toBe(false);
  });
});
