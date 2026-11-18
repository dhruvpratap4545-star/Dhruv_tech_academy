import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as LibraryApi from "@/features/library/api";
import type { NodeDetail, SyllabusNode } from "@/features/library/api";
import { LibraryPage } from "@/features/library/pages/LibraryPage";
import { makeUser, renderWithProviders } from "@/test/utils";

vi.mock("@/features/library/api", async (importOriginal) => ({
  ...(await importOriginal<typeof LibraryApi>()),
  fetchTracks: vi.fn(),
  fetchChildren: vi.fn(),
  fetchNode: vi.fn(),
  fetchItems: vi.fn(),
  fetchMySyllabus: vi.fn(),
  createNode: vi.fn(),
}));
vi.mock("@/features/library/useOwnerOptions", () => ({
  useOwnerOptions: () => [{ value: "inst1", label: "ABC School" }],
}));

const api = await import("@/features/library/api");

function node(id: string, kind: SyllabusNode["kind"], name: string, parent: string | null) {
  return {
    id,
    institute_id: null,
    track: "neet",
    parent_id: parent,
    kind,
    name,
    code: id,
    order: 0,
    mediums: ["hi", "en"],
    difficulty: null,
    exam_tags: [],
    status: "active",
    created_by: null,
    child_count: 1,
  } satisfies SyllabusNode;
}

const neet = node("neet", "track", "NEET", null);
const c11 = node("c11", "level", "Class 11", "neet");
const physics = node("phy", "subject", "Physics", "c11");

const physicsDetail: NodeDetail = {
  node: physics,
  breadcrumb: [
    { id: "neet", name: "NEET", kind: "track" },
    { id: "c11", name: "Class 11", kind: "level" },
  ],
  children: [],
};

function renderAt(route: string, permissions: string[]) {
  return renderWithProviders(
    <Routes>
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/library/node/:nodeId" element={<LibraryPage />} />
    </Routes>,
    { route, user: makeUser({ permissions: permissions as never }) },
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
  vi.mocked(api.fetchTracks).mockResolvedValue([neet]);
  vi.mocked(api.fetchChildren).mockImplementation(async (parentId) =>
    parentId === "neet" ? [c11] : parentId === "c11" ? [physics] : [],
  );
  vi.mocked(api.fetchNode).mockResolvedValue(physicsDetail);
  vi.mocked(api.fetchItems).mockResolvedValue({ items: [], next_cursor: null, total: 0 } as never);
  vi.mocked(api.fetchMySyllabus).mockResolvedValue([]);
  vi.mocked(api.createNode).mockReset();
});

describe("LibraryPage section bar", () => {
  it("shows the open section's path as four steps, each listing what is inside the last", async () => {
    renderAt("/library/node/phy", ["library:read"]);

    // Each select shows its value once its own options have loaded.
    await waitFor(() => {
      expect(screen.getByLabelText("1. Track")).toHaveValue("neet");
      expect(screen.getByLabelText("2. Level")).toHaveValue("c11");
      expect(screen.getByLabelText("3. Subject")).toHaveValue("phy");
    });
    expect(screen.getByLabelText("4. Topic")).toHaveValue("");
    expect(api.fetchChildren).toHaveBeenCalledWith("phy", false, expect.anything());
    expect(await screen.findByRole("heading", { name: "Physics" })).toBeInTheDocument();
    // A reader cannot add sections or material.
    expect(screen.queryByRole("button", { name: /Add a/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add material" })).not.toBeInTheDocument();
  });

  it("lets a teacher add the next level in place and opens it", async () => {
    vi.mocked(api.createNode).mockResolvedValue(node("t1", "topic", "Laws of Motion", "phy"));
    renderAt("/library/node/phy", ["library:read", "library:contribute"]);

    await userEvent.click(await screen.findByRole("button", { name: "Add a Topic" }));
    await userEvent.type(screen.getByLabelText("Topic name"), "Laws of Motion");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.createNode).toHaveBeenCalledWith({
        parent_id: "phy",
        institute_id: "inst1",
        kind: "topic",
        name: "Laws of Motion",
      }),
    );
    await waitFor(() => expect(api.fetchNode).toHaveBeenCalledWith("t1", expect.anything()));
    expect(await screen.findByRole("button", { name: "Add material" })).toBeInTheDocument();
  });

  it("asks for the step before before a later one can be chosen", async () => {
    renderAt("/library", ["library:read", "library:contribute"]);
    await waitFor(() => expect(screen.getByLabelText("1. Track")).toBeEnabled());
    expect(screen.getByLabelText("2. Level")).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Add a/ })).not.toBeInTheDocument();
  });
});
