import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ContentItem } from "@/features/library/api";
import { MaterialCard } from "@/features/library/components/MaterialCard";
import { makeUser, renderWithProviders } from "@/test/utils";

const base: ContentItem = {
  id: "i1",
  institute_id: null,
  title: "Laws of motion",
  kind: "text",
  file_id: null,
  file: null,
  url: null,
  video_provider: null,
  video_id: null,
  body: "<script>alert(1)</script> Newton",
  node_ids: ["n1"],
  medium: "en",
  author: null,
  source: null,
  status: "published",
  version: 1,
  created_by: "u1",
  reviewed_by: null,
  review_note: null,
  published_at: "2026-11-01T00:00:00Z",
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
};

describe("MaterialCard", () => {
  it("renders a note as text, never as HTML", () => {
    const { container } = renderWithProviders(<MaterialCard item={base} />, { user: makeUser() });
    expect(screen.getByText(/<script>alert\(1\)<\/script> Newton/)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });

  it("embeds a validated video and nothing else", () => {
    const { container } = renderWithProviders(
      <MaterialCard
        item={{
          ...base,
          kind: "video_link",
          body: null,
          video_provider: "youtube",
          video_id: "dQw4w9WgXcQ",
        }}
      />,
      { user: makeUser() },
    );
    expect(container.querySelector("iframe")?.getAttribute("src")).toBe(
      "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
    );
  });

  it("opens links safely", () => {
    renderWithProviders(
      <MaterialCard item={{ ...base, kind: "link", body: null, url: "https://ncert.nic.in" }} />,
      { user: makeUser() },
    );
    const link = screen.getByRole("link", { name: "Open link" });
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });
});
