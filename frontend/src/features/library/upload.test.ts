import type * as LibApi from "@/lib/api";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof LibApi>()),
  apiFetch: vi.fn(),
}));

const { apiFetch } = await import("@/lib/api");
const { uploadDocument } = await import("@/features/library/api");

const file = new File(["%PDF-1.7"], "ohm.pdf", { type: "application/pdf" });
const input = { file, title: "Ohm's Law notes", node_ids: ["n1"], medium: "en" as const };
const put = vi.fn();

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
  put.mockReset();
  vi.stubGlobal("fetch", put);
});
afterEach(() => vi.unstubAllGlobals());

describe("uploadDocument", () => {
  it("puts the file straight into storage, then files it under its topic", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({
        file_id: "f1",
        upload_url: "https://storage.googleapis.com/bucket/key?sig",
        headers: { "Content-Type": "application/pdf", "x-goog-content-length-range": "0,10" },
        max_bytes: 10,
      })
      .mockResolvedValueOnce({ id: "item1" });
    put.mockResolvedValue(new Response(null, { status: 200 }));

    await expect(uploadDocument(input)).resolves.toEqual({ id: "item1" });

    expect(put).toHaveBeenCalledWith("https://storage.googleapis.com/bucket/key?sig", {
      method: "PUT",
      headers: { "Content-Type": "application/pdf", "x-goog-content-length-range": "0,10" },
      body: file,
      credentials: "omit",
    });
    expect(vi.mocked(apiFetch).mock.calls[1]![0]).toBe("/library/items/from-upload");
  });

  it("falls back to uploading through the API when storage cannot sign", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ file_id: null, upload_url: null, headers: {}, max_bytes: 10 })
      .mockResolvedValueOnce({ id: "item2" });

    await expect(uploadDocument(input)).resolves.toEqual({ id: "item2" });

    expect(put).not.toHaveBeenCalled();
    expect(vi.mocked(apiFetch).mock.calls[1]![0]).toBe("/library/items/upload");
  });

  it("stops if storage refuses the file, so nothing half-uploaded is filed", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      file_id: "f1",
      upload_url: "https://storage.googleapis.com/bucket/key?sig",
      headers: {},
      max_bytes: 10,
    });
    put.mockResolvedValue(new Response(null, { status: 403 }));

    await expect(uploadDocument(input)).rejects.toThrow("could not be uploaded");
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });
});
