import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudentStatusBadge } from "@/features/homework/components/StatusBadges";
import { SubmitForm } from "@/features/homework/components/SubmitForm";
import { StudentBoardPage } from "@/features/homework/pages/StudentBoardPage";
import { makeUser, renderWithProviders } from "@/test/utils";

vi.mock("@/features/homework/api", () => ({
  homeworkKeys: {
    all: ["homework"],
    mine: (tab: string) => ["homework", "mine", tab],
  },
  submitHomework: vi.fn(),
  fetchMyBoard: vi.fn(),
  fileUrl: (id: string) => `/files/${id}`,
}));

const { fetchMyBoard, submitHomework } = await import("@/features/homework/api");

function file(name: string, type = "image/jpeg"): File {
  return new File(["x"], name, { type });
}

beforeEach(() => {
  vi.mocked(fetchMyBoard).mockReset().mockResolvedValue([]);
  vi.mocked(submitHomework).mockReset();
});

describe("StudentStatusBadge", () => {
  it("labels the status and flags late work", () => {
    renderWithProviders(<StudentStatusBadge status="submitted" late />);
    expect(screen.getByText("Submitted")).toBeInTheDocument();
    expect(screen.getByText("Late")).toBeInTheDocument();
  });

  it("speaks Hindi when the person chose it", () => {
    const user = makeUser({ preferences: { theme: "system", language: "hi" } });
    renderWithProviders(<StudentStatusBadge status="checked" />, { user });
    expect(screen.getByText("जाँचा गया")).toBeInTheDocument();
  });
});

describe("SubmitForm", () => {
  it("refuses an empty submission without calling the server", async () => {
    renderWithProviders(<SubmitForm homeworkId="h1" existing={null} />);
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(screen.getByText("Type an answer or attach at least one file.")).toBeInTheDocument();
    expect(submitHomework).not.toHaveBeenCalled();
  });

  it("keeps at most five files", () => {
    renderWithProviders(<SubmitForm homeworkId="h1" existing={null} />);
    fireEvent.change(screen.getByTestId("file-input"), {
      target: { files: Array.from({ length: 6 }, (_, i) => file(`page-${i}.jpg`)) },
    });
    expect(screen.getAllByRole("button", { name: /^Remove page-/ })).toHaveLength(5);
    expect(screen.getByText("You can attach at most 5 files.")).toBeInTheDocument();
  });

  it("sends the typed answer and the files", async () => {
    vi.mocked(submitHomework).mockResolvedValue({} as never);
    renderWithProviders(<SubmitForm homeworkId="h1" existing={null} />);
    await userEvent.type(screen.getByLabelText("Typed answer"), "x = 4");
    fireEvent.change(screen.getByTestId("file-input"), { target: { files: [file("p1.jpg")] } });
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(submitHomework).toHaveBeenCalled());
    const [id, text, files] = vi.mocked(submitHomework).mock.calls[0]!;
    expect(id).toBe("h1");
    expect(text).toBe("x = 4");
    expect((files as File[]).map((f) => f.name)).toEqual(["p1.jpg"]);
  });
});

describe("StudentBoardPage", () => {
  it("loads the pending tab first and switches tabs", async () => {
    renderWithProviders(<StudentBoardPage />, { user: makeUser() });
    await waitFor(() => expect(fetchMyBoard).toHaveBeenCalledWith("pending", expect.anything()));
    expect(screen.getByRole("tab", { name: "Pending" })).toHaveAttribute("aria-selected", "true");

    await userEvent.click(screen.getByRole("tab", { name: "Overdue" }));
    await waitFor(() => expect(fetchMyBoard).toHaveBeenCalledWith("overdue", expect.anything()));
    expect(screen.getByRole("tab", { name: "Overdue" })).toHaveAttribute("aria-selected", "true");
  });
});
