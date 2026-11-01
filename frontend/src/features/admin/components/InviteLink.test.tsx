import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InviteLink } from "@/features/admin/components/InviteLink";
import { inviteWhatsAppUrl } from "@/lib/invites";
import { renderWithProviders } from "@/test/utils";

const LINK = "http://localhost:5173/set-password?email=ravi%40example.com#code=123456";

describe("InviteLink", () => {
  it("says the email went out and still offers the link", () => {
    renderWithProviders(
      <InviteLink
        result={{ name: "Ravi", email: "ravi@example.com", invitationSent: true, setupLink: LINK }}
      />,
    );
    expect(screen.getByText(/has been sent to ravi@example.com/)).toBeInTheDocument();
    expect(screen.getByLabelText("Setup link")).toHaveValue(LINK);
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  });

  it("tells the inviter to share the link when email is not set up", () => {
    renderWithProviders(
      <InviteLink
        result={{ name: "Ravi", email: "ravi@example.com", invitationSent: false, setupLink: LINK }}
      />,
    );
    expect(screen.getByText(/Email is not set up yet/)).toBeInTheDocument();
    const whatsapp = screen.getByRole("link", { name: "Share on WhatsApp" });
    expect(whatsapp).toHaveAttribute("rel", "noopener noreferrer");
    expect(decodeURIComponent(whatsapp.getAttribute("href")!)).toContain(LINK);
  });
});

describe("inviteWhatsAppUrl", () => {
  it("encodes the whole message, link included", () => {
    const url = inviteWhatsAppUrl("Ravi", LINK);
    expect(url.startsWith("https://wa.me/?text=")).toBe(true);
    expect(url).not.toContain("#code"); // the # is encoded, so it stays inside the text
    expect(decodeURIComponent(url.slice("https://wa.me/?text=".length))).toContain(LINK);
  });
});
