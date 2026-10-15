import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "@/features/theme/ThemeToggle";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/features/auth/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  updatePreferences: vi.fn().mockResolvedValue({ theme: "dark", language: "en" }),
}));

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("offers light, dark and system", () => {
    renderWithProviders(<ThemeToggle />);
    expect(screen.getByRole("radio", { name: "Light" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Dark" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "System" })).toBeInTheDocument();
  });

  it("switches the document to dark mode", async () => {
    renderWithProviders(<ThemeToggle />);
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(document.documentElement).toHaveClass("dark");
  });

  it("remembers the choice locally so the page does not flash on reload", async () => {
    renderWithProviders(<ThemeToggle />);
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(localStorage.getItem("dhruv-theme")).toBe("dark");
  });

  it("saves the choice to the account so it follows the user", async () => {
    const { updatePreferences } = await import("@/features/auth/api");
    renderWithProviders(<ThemeToggle />);
    await userEvent.click(screen.getByRole("radio", { name: "Light" }));
    expect(updatePreferences).toHaveBeenCalledWith({ theme: "light" });
  });

  it("does not save when there is no session to save against", async () => {
    const { updatePreferences } = await import("@/features/auth/api");
    vi.mocked(updatePreferences).mockClear();
    renderWithProviders(<ThemeToggle persist={false} />);
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(updatePreferences).not.toHaveBeenCalled();
  });
});
