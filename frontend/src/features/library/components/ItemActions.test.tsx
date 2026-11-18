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
    created_by: makeUser().id,
    reviewed_by: null,
    review_note: null,
    published_at: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  };
}

describe("ItemActions", () => {
  it("lets the person who added material remove it, with no review step", () => {
    renderWithProviders(<ItemActions item={item("published")} onHistory={() => {}} />, {
      user: makeUser({ permissions: ["library:read", "library:contribute"] }),
    });
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send for review" })).not.toBeInTheDocument();
  });

  it("hides remove on a colleague's material unless the reader manages the library", () => {
    const other = { ...item("published"), created_by: "someone-else" };
    const { unmount } = renderWithProviders(<ItemActions item={other} />, {
      user: makeUser({ permissions: ["library:read", "library:contribute"] }),
    });
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    unmount();
    renderWithProviders(<ItemActions item={other} />, {
      user: makeUser({ permissions: ["library:read", "library:manage"] }),
    });
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("lets a reviewer publish a draft left from the old review flow", () => {
    renderWithProviders(<ItemActions item={item("in_review")} />, {
      user: makeUser({ permissions: ["library:read", "library:publish", "library:manage"] }),
    });
    expect(screen.getByRole("button", { name: "Publish" })).toBeInTheDocument();
  });

  it("shows the Hindi labels when Hindi is chosen", () => {
    renderWithProviders(<ItemActions item={item("published")} />, {
      user: makeUser({
        permissions: ["library:contribute"],
        preferences: { theme: "system", language: "hi" },
      }),
    });
    expect(screen.getByRole("button", { name: "हटाएँ" })).toBeInTheDocument();
  });
});
