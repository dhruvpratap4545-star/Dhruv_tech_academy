import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OfflineBanner } from "@/components/OfflineBanner";
import { ApiError } from "@/lib/api";

function setOnline(value: boolean) {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(value);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OfflineBanner", () => {
  it("says nothing while the connection is there", () => {
    setOnline(true);
    render(<OfflineBanner />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("warns, and says work can continue", () => {
    setOnline(false);
    render(<OfflineBanner />);

    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent(/you are offline/i);
    expect(banner).toHaveTextContent(/keep working/i);
  });

  it("appears and disappears with the connection", () => {
    setOnline(true);
    render(<OfflineBanner />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    setOnline(false);
    act(() => window.dispatchEvent(new Event("offline")));
    expect(screen.getByRole("status")).toBeInTheDocument();

    setOnline(true);
    act(() => window.dispatchEvent(new Event("online")));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("disables nothing — a button beside it stays usable", () => {
    setOnline(false);
    render(
      <>
        <OfflineBanner />
        <button type="button">Save</button>
      </>,
    );
    // The decision the user made: warn, and let them try. `navigator.onLine` is a guess,
    // and refusing to let somebody save on the strength of a guess is the worse failure.
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });
});

describe("a request that never reaches the server", () => {
  it("is reported as being offline rather than as 'Failed to fetch'", async () => {
    setOnline(false);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const { apiFetch } = await import("@/lib/api");

    const error = await apiFetch("/users").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).isOffline).toBe(true);
    expect((error as ApiError).message).toMatch(/you are offline/i);
    expect((error as ApiError).message).toMatch(/nothing has been lost/i);
  });

  it("says the server could not be reached when the browser thinks it is online", async () => {
    setOnline(true);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const { apiFetch } = await import("@/lib/api");

    const error = await apiFetch("/users").catch((caught: unknown) => caught);
    expect((error as ApiError).message).toMatch(/could not reach the server/i);
  });

  it("lets a cancelled request stay cancelled", async () => {
    const abort = new DOMException("The operation was aborted.", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort));
    const { apiFetch } = await import("@/lib/api");

    // A component unmounting mid-request must not be reported to the person as a network
    // failure — nothing failed, they simply left the page.
    const error = await apiFetch("/users").catch((caught: unknown) => caught);
    expect(error).toBe(abort);
  });
});
