import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BulkInviteReport } from "@/features/admin/api";
import { BulkInviteModal } from "@/features/admin/components/BulkInviteModal";
import { makeUser, renderWithProviders, roleAssignment } from "@/test/utils";

vi.mock("@/features/admin/api", () => ({
  userKeys: { all: ["users"], list: () => ["users", "list"] },
  instituteKeys: { all: ["institutes"], list: () => ["institutes", "list"] },
  fetchInstitutes: vi.fn(),
  bulkInvite: vi.fn(),
  downloadInviteTemplate: vi.fn(),
}));

const { bulkInvite, downloadInviteTemplate, fetchInstitutes } =
  await import("@/features/admin/api");

const INSTITUTE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

/** HTMLDialogElement is not implemented in jsdom. */
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
  vi.mocked(fetchInstitutes).mockResolvedValue({ items: [], next_cursor: null, total: 0 });
  vi.mocked(downloadInviteTemplate).mockResolvedValue(undefined);
  vi.mocked(bulkInvite).mockReset();
});

function report(overrides: Partial<BulkInviteReport> = {}): BulkInviteReport {
  return {
    dry_run: true,
    institute_id: INSTITUTE_ID,
    rows: [],
    invited: 0,
    parents: 0,
    skipped: 0,
    ...overrides,
  };
}

function row(overrides: Partial<BulkInviteReport["rows"][number]> = {}) {
  return {
    row: 2,
    full_name: "Riya Sharma",
    email: "riya@vidya.example",
    outcome: "ready" as const,
    reason: null,
    branch: null,
    class_name: null,
    parent_email: null,
    parent_outcome: null,
    parent_reason: null,
    ...overrides,
  };
}

function principal() {
  return makeUser({
    permissions: ["user:invite"],
    institute_ids: [INSTITUTE_ID],
    roles: [roleAssignment("institute_admin", INSTITUTE_ID)],
  });
}

function open() {
  return renderWithProviders(<BulkInviteModal open onClose={vi.fn()} />, { user: principal() });
}

async function choose(file = new File(["x"], "learners.xlsx")) {
  await userEvent.upload(screen.getByLabelText(/your filled-in file/i), file);
}

describe("BulkInviteModal", () => {
  it("will not check a file before one is chosen", () => {
    open();
    expect(screen.getByRole("button", { name: /check the file/i })).toBeDisabled();
  });

  it("does not ask a single-institute administrator which institute", () => {
    open();
    expect(screen.queryByLabelText(/institute/i)).not.toBeInTheDocument();
  });

  it("checks the file before anything is sent", async () => {
    vi.mocked(bulkInvite).mockResolvedValue(report({ rows: [row()] }));
    open();
    await choose();
    await userEvent.click(screen.getByRole("button", { name: /check the file/i }));

    await waitFor(() => expect(bulkInvite).toHaveBeenCalled());
    // The third argument is the preview flag, and it has to be true on this step.
    expect(vi.mocked(bulkInvite).mock.calls[0]![2]).toBe(true);
    expect(await screen.findByText(/1 learner ready to invite/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing has been sent yet/i)).toBeInTheDocument();
  });

  it("names the row and the reason for anything it cannot invite", async () => {
    vi.mocked(bulkInvite).mockResolvedValue(
      report({
        skipped: 1,
        rows: [row({ row: 7, outcome: "skipped", reason: "that is not an email address" })],
      }),
    );
    open();
    await choose();
    await userEvent.click(screen.getByRole("button", { name: /check the file/i }));

    expect(await screen.findByText("7")).toBeInTheDocument();
    expect(screen.getByText(/that is not an email address/i)).toBeInTheDocument();
  });

  it("offers to invite only the rows that are ready", async () => {
    vi.mocked(bulkInvite).mockResolvedValue(
      report({
        skipped: 1,
        rows: [row(), row({ row: 3, outcome: "skipped", reason: "no name" })],
      }),
    );
    open();
    await choose();
    await userEvent.click(screen.getByRole("button", { name: /check the file/i }));

    expect(await screen.findByRole("button", { name: /invite 1 learner/i })).toBeEnabled();
  });

  it("cannot be sent when every row is skipped", async () => {
    vi.mocked(bulkInvite).mockResolvedValue(
      report({ skipped: 1, rows: [row({ outcome: "skipped", reason: "no name" })] }),
    );
    open();
    await choose();
    await userEvent.click(screen.getByRole("button", { name: /check the file/i }));

    expect(await screen.findByText(/nothing in this file can be invited/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /invite 0 learners/i })).toBeDisabled();
  });

  it("sends the file for real on the second step and reports what happened", async () => {
    const onDone = vi.fn();
    vi.mocked(bulkInvite)
      .mockResolvedValueOnce(report({ rows: [row({ parent_email: "meera@parent.example" })] }))
      .mockResolvedValueOnce(
        report({
          dry_run: false,
          invited: 1,
          parents: 1,
          rows: [
            row({
              outcome: "invited",
              parent_email: "meera@parent.example",
              parent_outcome: "invited",
            }),
          ],
        }),
      );
    renderWithProviders(<BulkInviteModal open onClose={vi.fn()} onDone={onDone} />, {
      user: principal(),
    });
    await choose();
    await userEvent.click(screen.getByRole("button", { name: /check the file/i }));
    await userEvent.click(await screen.findByRole("button", { name: /invite 1 learner/i }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(vi.mocked(bulkInvite).mock.calls[1]![2]).toBe(false);
    expect(await screen.findByText(/1 learner invited/i)).toBeInTheDocument();
    expect(screen.getByText(/1 parent was linked/i)).toBeInTheDocument();
  });

  it("shows the server's own message when the file cannot be read", async () => {
    vi.mocked(bulkInvite).mockRejectedValue(
      new Error("That file could not be read as a spreadsheet. Save it as .xlsx and try again."),
    );
    open();
    await choose();
    await userEvent.click(screen.getByRole("button", { name: /check the file/i }));

    expect(await screen.findByText(/save it as .xlsx/i)).toBeInTheDocument();
  });

  it("makes somebody with several institutes say which one", async () => {
    vi.mocked(fetchInstitutes).mockResolvedValue({
      items: [],
      next_cursor: null,
      total: 0,
    });
    renderWithProviders(<BulkInviteModal open onClose={vi.fn()} />, {
      user: makeUser({
        permissions: ["user:invite"],
        institute_ids: [INSTITUTE_ID, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"],
        roles: [roleAssignment("institute_admin", INSTITUTE_ID)],
      }),
    });
    await choose();

    expect(screen.getByLabelText(/institute/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /check the file/i })).toBeDisabled();
  });
});
