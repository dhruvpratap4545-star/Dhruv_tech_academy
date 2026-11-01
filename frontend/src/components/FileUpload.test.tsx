import { fireEvent, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { FileUpload } from "@/components/FileUpload";
import { screenFiles } from "@/lib/uploads";
import { translate } from "@/lib/i18n";
import { renderWithProviders } from "@/test/utils";

const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) =>
  translate("en", key, vars);

function file(name: string, type: string, size = 100): File {
  const f = new File(["x"], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
}

describe("screenFiles", () => {
  it("keeps PDFs and images and refuses everything else", () => {
    const result = screenFiles(
      [],
      [file("a.pdf", "application/pdf"), file("b.exe", "application/x-msdownload")],
      5,
      t,
    );
    expect(result.files.map((f) => f.name)).toEqual(["a.pdf"]);
    expect(result.errors).toEqual(["b.exe is not a PDF, JPG or PNG."]);
  });

  it("refuses files over the size limit", () => {
    const result = screenFiles([], [file("big.jpg", "image/jpeg", 11 * 1024 * 1024)], 5, t);
    expect(result.files).toHaveLength(0);
    expect(result.errors[0]).toContain("larger than 10 MB");
  });

  it("stops at the maximum number of files", () => {
    const current = [file("1.png", "image/png"), file("2.png", "image/png")];
    const result = screenFiles(current, [file("3.png", "image/png")], 2, t);
    expect(result.files).toHaveLength(2);
    expect(result.errors).toEqual(["You can attach at most 2 files."]);
  });

  it("accepts a camera photo with no reported type", () => {
    expect(screenFiles([], [file("photo", "")], 5, t).files).toHaveLength(1);
  });
});

function Harness() {
  const [files, setFiles] = useState<File[]>([]);
  return <FileUpload label="Attachments" files={files} onChange={setFiles} max={5} />;
}

describe("FileUpload", () => {
  it("lists picked files and removes them", () => {
    renderWithProviders(<Harness />);
    fireEvent.change(screen.getByTestId("file-input"), {
      target: { files: [file("notes.pdf", "application/pdf")] },
    });
    expect(screen.getByText("notes.pdf")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove notes.pdf" }));
    expect(screen.queryByText("notes.pdf")).not.toBeInTheDocument();
  });
});
