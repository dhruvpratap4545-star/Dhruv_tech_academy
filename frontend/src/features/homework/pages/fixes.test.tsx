import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BoardRow, Homework } from "@/features/homework/api";
import { BoardList } from "@/features/homework/components/BoardList";
import { SubmitForm } from "@/features/homework/components/SubmitForm";
import { HomeworkDetailPage } from "@/features/homework/pages/HomeworkDetailPage";
import { HomeworkFormPage } from "@/features/homework/pages/HomeworkFormPage";
import { ReportsPage } from "@/features/homework/pages/ReportsPage";
import type { Permission } from "@/lib/permissions";
import { makeUser, renderWithProviders } from "@/test/utils";

vi.mock("@/features/homework/api", () => ({
  homeworkKeys: {
    all: ["homework"],
    detail: (id: string, s = "") => ["homework", "detail", id, s],
    tracker: (id: string) => ["homework", "tracker", id],
    report: (f: unknown) => ["homework", "report", f],
  },
  fetchHomework: vi.fn(),
  fetchTracker: vi.fn(),
  fetchReport: vi.fn(),
  duplicateHomework: vi.fn(),
  submitHomework: vi.fn(),
  fileUrl: (id: string) => `/files/${id}`,
}));
vi.mock("@/features/library/api", () => ({
  libraryKeys: { node: (id: string) => ["library", "node", id] },
  fetchNode: vi.fn(),
}));
vi.mock("@/features/homework/components/useClassOptions", () => ({
  useClassOptions: () => ({
    loading: false,
    options: [
      { value: "c1", label: "Class 10 A", instituteId: "i1" },
      { value: "c2", label: "Class 10 B", instituteId: "i1" },
      { value: "c9", label: "Elsewhere", instituteId: "i2" },
    ],
  }),
}));

const { fetchHomework, fetchTracker, fetchReport, duplicateHomework } =
  await import("@/features/homework/api");
const { fetchNode } = await import("@/features/library/api");

const future = new Date(Date.now() + 86_400_000).toISOString();

function homework(overrides: Partial<Homework> = {}): Homework {
  return {
    id: "h1",
    institute_id: "i1",
    branch_id: "b1",
    class_id: "c1",
    class_name: "Class 10 A",
    subject: "Science",
    node_id: null,
    title: "Photosynthesis",
    instructions: "",
    attachments: [],
    medium: null,
    total_marks: 10,
    publish_at: future,
    due_at: future,
    allow_late: true,
    allow_resubmit: true,
    status: "published",
    is_visible: true,
    created_by: "t1",
    created_at: future,
    ...overrides,
  };
}

const row = (hw: Homework, extra: Partial<BoardRow> = {}): BoardRow => ({
  homework: hw,
  student_status: "pending",
  submission: null,
  ...extra,
});

function renderDetail(permissions: Permission[], route = "/homework/h1") {
  return renderWithProviders(
    <Routes>
      <Route path="/homework/:id" element={<HomeworkDetailPage />} />
    </Routes>,
    { user: makeUser({ permissions }), route },
  );
}

beforeEach(() => {
  // HTMLDialogElement is not implemented in jsdom.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
  vi.mocked(fetchHomework).mockReset();
  vi.mocked(fetchTracker)
    .mockReset()
    .mockResolvedValue({
      homework_id: "h1",
      counts: { pending: 0, redo: 1 },
      late: 0,
      rows: [
        {
          student_user_id: "s1",
          full_name: "Ravi",
          roll_no: null,
          student_status: "redo",
          submission_id: "sub1",
          submitted_at: future,
          is_late: false,
          marks: null,
        },
      ],
    });
  vi.mocked(duplicateHomework).mockReset();
});

describe("ReportsPage", () => {
  it("shows the server's percentage as is", async () => {
    const totals = {
      key: null,
      label: "All",
      homework: 1,
      expected: 2,
      submitted: 2,
      late: 0,
      completion_rate: 100,
    };
    vi.mocked(fetchReport).mockResolvedValue({
      date_from: null,
      date_to: null,
      totals,
      by_class: [],
      by_subject: [],
      by_teacher: [],
    });
    renderWithProviders(<ReportsPage />, { user: makeUser() });
    expect(await screen.findByText("100%")).toBeInTheDocument();
  });
});

describe("BoardList", () => {
  it("shows the teacher's remark and keeps the chosen child on the link", () => {
    const hw = homework();
    renderWithProviders(
      <BoardList
        studentId="kid1"
        empty="none"
        rows={[
          row(hw, {
            student_status: "checked",
            submission: {
              id: "sub1",
              homework_id: "h1",
              student_user_id: "kid1",
              student_name: null,
              text: "",
              files: [],
              submitted_at: future,
              is_late: false,
              attempts: 1,
              status: "checked",
              marks: 8,
              grade: null,
              remark: "Good work",
              checked_at: future,
            },
          }),
        ]}
      />,
    );
    expect(screen.getByText(/Good work/)).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/homework/h1?student=kid1");
  });
});

describe("HomeworkDetailPage", () => {
  it("asks for the chosen child's work when a parent opens it", async () => {
    vi.mocked(fetchHomework).mockResolvedValue(row(homework()));
    renderDetail(["homework:read"], "/homework/h1?student=kid1");
    await waitFor(() =>
      expect(fetchHomework).toHaveBeenCalledWith("h1", expect.anything(), "kid1"),
    );
  });

  it("hides Remind and Share until students can see the homework", async () => {
    vi.mocked(fetchHomework).mockResolvedValue(row(homework({ is_visible: false })));
    renderDetail(["homework:manage"]);
    expect(await screen.findByText("Submissions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remind pending" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Share on WhatsApp" })).not.toBeInTheDocument();
  });

  it("offers Remind and Share once visible, but no Check on work sent back for redo", async () => {
    vi.mocked(fetchHomework).mockResolvedValue(row(homework()));
    renderDetail(["homework:manage"]);
    expect(await screen.findByRole("button", { name: "Remind pending" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share on WhatsApp" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check" })).not.toBeInTheDocument();
  });

  it("links the study material only for people who can read the library", async () => {
    vi.mocked(fetchHomework).mockResolvedValue(row(homework({ node_id: "n1" })));
    const view = renderDetail(["homework:read", "library:read"]);
    const link = await screen.findByRole("link", { name: "Open the linked study material" });
    expect(link).toHaveAttribute("href", "/library/node/n1");
    view.unmount();

    renderDetail(["homework:read"]);
    expect(await screen.findByText("Photosynthesis")).toBeInTheDocument();
    expect(screen.queryByText("Open the linked study material")).not.toBeInTheDocument();
  });

  it("copies into another class of the same institute", async () => {
    vi.mocked(fetchHomework).mockResolvedValue(row(homework()));
    vi.mocked(duplicateHomework).mockResolvedValue(homework({ id: "h2" }));
    renderDetail(["homework:manage"]);
    await userEvent.click(await screen.findByRole("button", { name: "Copy" }));
    const dialog = screen.getByRole("dialog");
    const select = within(dialog).getByLabelText("Copy into class");
    expect(within(select).queryByText("Elsewhere")).not.toBeInTheDocument();
    await userEvent.selectOptions(select, "c2");
    await userEvent.click(within(dialog).getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(duplicateHomework).toHaveBeenCalledWith("h1", "c2"));
  });
});

describe("HomeworkFormPage", () => {
  it("shows the linked topic by name, not by id", async () => {
    vi.mocked(fetchHomework).mockResolvedValue(row(homework({ node_id: "n1" })));
    vi.mocked(fetchNode).mockResolvedValue({
      node: { id: "n1", name: "Photosynthesis basics" },
      breadcrumb: [],
      children: [],
    } as never);
    renderWithProviders(
      <Routes>
        <Route path="/homework/:id/edit" element={<HomeworkFormPage />} />
      </Routes>,
      { user: makeUser({ permissions: ["homework:manage"] }), route: "/homework/h1/edit" },
    );
    expect(await screen.findByText("Photosynthesis basics")).toBeInTheDocument();
    expect(screen.queryByText("n1")).not.toBeInTheDocument();
  });
});

describe("SubmitForm", () => {
  it("says earlier files are kept when resubmitting", () => {
    renderWithProviders(
      <SubmitForm
        homeworkId="h1"
        existing={{
          id: "sub1",
          homework_id: "h1",
          student_user_id: "s1",
          student_name: null,
          text: "",
          files: [
            {
              id: "f1",
              original_name: "p.jpg",
              content_type: "image/jpeg",
              size: 1,
              created_at: future,
            },
          ],
          submitted_at: future,
          is_late: false,
          attempts: 1,
          status: "submitted",
          marks: null,
          grade: null,
          remark: null,
          checked_at: null,
        }}
      />,
    );
    expect(
      screen.getByText("Your earlier files are kept unless you attach new ones."),
    ).toBeInTheDocument();
  });
});
