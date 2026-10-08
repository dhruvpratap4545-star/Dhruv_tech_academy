import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatRupees, humanise, initials } from "@/lib/format";

describe("formatDate", () => {
  it("uses DD-MM-YYYY, the Indian convention", () => {
    expect(formatDate("2026-10-07T12:00:00Z")).toBe("07-10-2026");
  });

  it("falls back for a missing value rather than printing Invalid Date", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("not a date")).toBe("—");
  });

  it("includes the time when asked", () => {
    expect(formatDateTime("2026-10-07T12:00:00Z")).toMatch(/^07-10-2026/);
  });
});

describe("formatRupees", () => {
  it("uses the rupee sign and Indian digit grouping", () => {
    const formatted = formatRupees(100000);
    expect(formatted).toContain("₹");
    // 1,00,000 — not 100,000.
    expect(formatted).toContain("1,00,000");
  });

  it("falls back for a missing amount", () => {
    expect(formatRupees(null)).toBe("—");
  });
});

describe("initials", () => {
  it("takes the first and last name", () => {
    expect(initials("Asha Rao")).toBe("AR");
    expect(initials("Dhruv Pratap Singh")).toBe("DS");
  });

  it("handles a single name and empty input", () => {
    expect(initials("Asha")).toBe("AS");
    expect(initials("   ")).toBe("?");
  });
});

describe("humanise", () => {
  it("turns a key into a label", () => {
    expect(humanise("branch_admin")).toBe("Branch Admin");
    expect(humanise("user:invite")).toBe("User Invite");
  });
});
