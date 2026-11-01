import { describe, expect, it } from "vitest";

import { asLanguage, translate } from "@/lib/i18n";

describe("translate", () => {
  it("returns English by default and fills placeholders", () => {
    expect(translate("en", "upload.tooMany", { max: 5 })).toBe("You can attach at most 5 files.");
  });

  it("returns Hindi when chosen", () => {
    expect(translate("hi", "common.save")).toBe("सहेजें");
    expect(translate("hi", "upload.tooMany", { max: 5 })).toContain("5");
  });

  it("leaves an unknown placeholder visible rather than dropping it", () => {
    expect(translate("en", "upload.tooBig", { name: "a.pdf" })).toBe(
      "a.pdf is larger than {mb} MB.",
    );
  });

  it("treats anything but hi as English", () => {
    expect(asLanguage("hi")).toBe("hi");
    expect(asLanguage("fr")).toBe("en");
    expect(asLanguage(undefined)).toBe("en");
  });
});
