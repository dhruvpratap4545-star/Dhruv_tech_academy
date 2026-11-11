import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AiExtractResult, ImportResult } from "@/features/library/api";
import { importRows, readSyllabusWithAi } from "@/features/library/api";
import { AiImport } from "@/features/library/components/AiImport";
import { makeUser, renderWithProviders } from "@/test/utils";

vi.mock("@/features/library/api", () => ({
  readSyllabusWithAi: vi.fn(),
  importRows: vi.fn(),
  downloadRowsAsExcel: vi.fn(),
  libraryKeys: { all: ["library"] },
}));

const row = (topic: string, subject = "Physics") => ({
  track: "custom",
  level: "Semester 1",
  subject,
  unit: "Unit 1",
  chapter: "",
  topic,
  medium: "English",
  difficulty: "",
  exam_tags: "",
  problems: [],
});

const READ: AiExtractResult = {
  file_name: "syllabus.pdf",
  model_id: "gemini-3.5-flash-lite",
  status: "ok",
  cost_paise: 229,
  input_tokens: 15000,
  output_tokens: 8000,
  missing_papers: ["Formal Writing in Hindi"],
  rows: [row("Reflection"), row("Refraction"), row("Ionic bonds", "Chemistry")],
};

const result = (overrides: Partial<ImportResult>): ImportResult => ({
  dry_run: true,
  rows_total: 2,
  rows_valid: 2,
  problems: [],
  created: 5,
  updated: 0,
  unchanged: 1,
  by_kind: {},
  ...overrides,
});

async function readFile() {
  renderWithProviders(<AiImport instituteId="inst-1" />, {
    user: makeUser({ permissions: ["library:read", "library:manage"] }),
  });
  const file = new File(["%PDF-1.7"], "syllabus.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Syllabus (PDF, JPG or PNG)"), {
    target: { files: [file] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Read with AI" }));
  await screen.findByDisplayValue("Reflection");
}

describe("AiImport", () => {
  beforeEach(() => {
    vi.mocked(readSyllabusWithAi).mockResolvedValue(READ);
    vi.mocked(importRows).mockReset();
  });

  it("shows the rows the AI read, its cost and the papers it missed", async () => {
    await readFile();

    expect(readSyllabusWithAi).toHaveBeenCalledWith(
      expect.any(File),
      expect.objectContaining({ track: "custom", instituteId: "inst-1" }),
    );
    expect(screen.getByText(/cost ₹2\.29/)).toBeInTheDocument();
    expect(screen.getByText(/Formal Writing in Hindi/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Ionic bonds")).toBeInTheDocument();
  });

  it("sends the reviewer's edits and removals to the dry run, then imports", async () => {
    vi.mocked(importRows)
      .mockResolvedValueOnce(result({}))
      .mockResolvedValueOnce(result({ dry_run: false }));
    await readFile();

    fireEvent.change(screen.getByDisplayValue("Reflection"), {
      target: { value: "Reflection of light" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Remove row 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Check rows" }));

    await waitFor(() => expect(importRows).toHaveBeenCalledTimes(1));
    const [sent, dryRun, instituteId] = vi.mocked(importRows).mock.calls[0]!;
    expect(sent.map((r: { topic: string }) => r.topic)).toEqual([
      "Reflection of light",
      "Ionic bonds",
    ]);
    expect([dryRun, instituteId]).toEqual([true, "inst-1"]);

    fireEvent.click(await screen.findByRole("button", { name: "Import 2 rows" }));
    expect(await screen.findByText(/Imported: 5 new/)).toBeInTheDocument();
  });

  it("highlights the rows the server refused", async () => {
    vi.mocked(importRows).mockResolvedValue(
      result({ rows_valid: 2, problems: [{ row: 3, messages: ["Subject needs English."] }] }),
    );
    await readFile();

    fireEvent.click(screen.getByRole("button", { name: "Check rows" }));

    expect(await screen.findByText(/1 rows need a fix/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Ionic bonds").closest("tr")).toHaveAttribute(
      "title",
      "Subject needs English.",
    );
  });
});
