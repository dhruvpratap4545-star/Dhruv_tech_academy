import { describe, expect, it } from "vitest";

import { embedUrl, fileUrl, safeHref, validateMaterial } from "@/features/library/material";
import { childKinds } from "@/features/library/tree";

describe("embedUrl", () => {
  it("builds privacy-friendly embeds from validated ids", () => {
    expect(embedUrl("youtube", "dQw4w9WgXcQ")).toBe(
      "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
    );
    expect(embedUrl("vimeo", "76979871")).toBe("https://player.vimeo.com/video/76979871");
  });

  it("refuses anything that is not a well-formed id", () => {
    expect(embedUrl("youtube", "javascript:alert(1)")).toBeNull();
    expect(embedUrl("youtube", "../../evil")).toBeNull();
    expect(embedUrl("vimeo", "abc")).toBeNull();
    expect(embedUrl("dailymotion", "x7tgad0")).toBeNull();
    expect(embedUrl(null, null)).toBeNull();
  });
});

describe("safeHref", () => {
  it("allows https only", () => {
    expect(safeHref("https://ncert.nic.in/textbook.php")).toBe("https://ncert.nic.in/textbook.php");
    expect(safeHref("http://example.com")).toBeNull();
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("not a url")).toBeNull();
  });
});

describe("fileUrl", () => {
  it("points at the access-checked download route", () => {
    expect(fileUrl("abc")).toMatch(/\/files\/abc$/);
  });
});

describe("validateMaterial", () => {
  const base = {
    kind: "link",
    title: "Notes",
    nodeIds: ["n1"],
    url: "https://a.in",
    body: "",
    files: [],
  };

  it("accepts a complete link", () => {
    expect(validateMaterial(base)).toBeNull();
  });

  it("names the first problem", () => {
    expect(validateMaterial({ ...base, title: "x" })).toBe("library.error.title");
    expect(validateMaterial({ ...base, nodeIds: [] })).toBe("library.error.topics");
    expect(validateMaterial({ ...base, url: "http://a.in" })).toBe("library.error.url");
    expect(validateMaterial({ ...base, kind: "pdf" })).toBe("library.error.file");
    expect(validateMaterial({ ...base, kind: "text" })).toBe("library.error.body");
  });

  it("needs exactly one file for a PDF", () => {
    const pdf = new File(["x"], "a.pdf", { type: "application/pdf" });
    expect(validateMaterial({ ...base, kind: "pdf", files: [pdf] })).toBeNull();
    expect(validateMaterial({ ...base, kind: "pdf", files: [pdf, pdf] })).toBe(
      "library.error.file",
    );
  });
});

describe("childKinds", () => {
  it("follows the syllabus levels, with units optional", () => {
    expect(childKinds("track")).toEqual(["level"]);
    expect(childKinds("subject")).toEqual(["unit", "chapter"]);
    expect(childKinds("chapter")).toEqual(["topic"]);
    expect(childKinds("topic")).toEqual([]);
  });
});
