import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ContentItem } from "@/features/library/api";
import { ItemActions } from "@/features/library/components/ItemActions";
import { makeUser, renderWithProviders } from "@/test/utils";

vi.mock("@/features/library/api", () => ({
  itemAction: vi.fn(),
  libraryKeys: { all: ["library"] },
}));

function item(status: ContentItem["status"]): ContentItem {
  return {
    id: "i1",
    institute_id: null,
    title: "Motion",
    kind: "link",
    file_id: null,
    file: null,
    url: "https://a.in",
    video_provider: null,
    video_id: null,
    body: null,
    node_ids: ["n1"],
    medium: "en",
    author: null,
    source: null,
    status,
    version: 1,
    created_by: "u1",
    reviewed_by: null,
    review_note: null,
    published_at: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  };
}

describe("ItemActions", () => {
  it("lets a contributor send a draft for review but not publish", () => {
    renderWithProviders(<ItemActions item={item("draft")} onHistory={() => {}} />, {
      user: makeUser({ permissions: ["library:read", "library:contribute"] }),
    });
    expect(screen.getByRole("button", { name: "Send for review" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  });

  it("hides publish from a faculty member looking at an item under review", () => {
    renderWithProviders(<ItemActions item={item("in_review")} onHistory={() => {}} />, {
      user: makeUser({ permissions: ["library:read", "library:contribute"] }),
    });
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send back" })).not.toBeInTheDocument();
  });

  it("offers publish and send back to a reviewer", () => {
    renderWithProviders(<ItemActions item={item("in_review")} onHistory={() => {}} />, {
      user: makeUser({ permissions: ["library:read", "library:publish", "library:manage"] }),
    });
    expect(screen.getByRole("button", { name: "Publish" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
  });

  it("shows the Hindi labels when Hindi is chosen", () => {
    renderWithProviders(<ItemActions item={item("draft")} onHistory={() => {}} />, {
      user: makeUser({
        permissions: ["library:contribute"],
        preferences: { theme: "system", language: "hi" },
      }),
    });
    expect(screen.getByRole("button", { name: "समीक्षा के लिए भेजें" })).toBeInTheDocument();
  });
});
