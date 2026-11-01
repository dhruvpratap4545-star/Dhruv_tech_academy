import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SetupPasswordPage } from "@/features/auth/pages/SetupPasswordPage";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/features/auth/api", () => ({ setupPassword: vi.fn() }));

describe("SetupPasswordPage", () => {
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("fills the code from the link fragment and wipes it from the address bar", () => {
    window.history.replaceState(null, "", "/set-password?email=ravi%40example.com#code=123456");
    renderWithProviders(<SetupPasswordPage />, {
      route: "/set-password?email=ravi%40example.com",
      user: null,
    });
    expect(screen.getByLabelText(/6-digit code/)).toHaveValue("123456");
    expect(window.location.hash).toBe("");
  });

  it("ignores anything in the fragment that is not a code", () => {
    window.history.replaceState(null, "", "/set-password#code=<script>");
    renderWithProviders(<SetupPasswordPage />, { route: "/set-password", user: null });
    expect(screen.getByLabelText(/6-digit code/)).toHaveValue("");
  });
});
